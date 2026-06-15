"""
Embedding consumer - processes chunks from RabbitMQ and generates embeddings.

Receives chunk messages, calls the LLM service for embeddings,
and stores the results in PostgreSQL + Qdrant.
"""

import logging
import uuid
from typing import Any

import httpx
from qdrant_client import models as qdrant_models

from shared.config import get_settings
from shared.database import get_db_session
from shared.models.chunk import Chunk
from shared.models.document import Document, DocumentStatus
from shared.qdrant import ensure_collection, upsert_vectors

logger = logging.getLogger(__name__)

# Shared HTTP client for calling LLM service
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20),
        )
    return _http_client


async def handle_embedding_message(message: dict[str, Any]) -> None:
    """
    Process a single embedding message from RabbitMQ.

    Message format:
    {
        "document_id": "uuid",
        "tenant_id": "str",
        "chunk_index": int,
        "content": "str",
        "token_count": int,
        "metadata": dict
    }
    """
    document_id = message["document_id"]
    tenant_id = message.get("tenant_id", "default")
    chunk_index = message["chunk_index"]
    content = message["content"]

    logger.info(
        "Processing embedding for document %s, chunk %d",
        document_id,
        chunk_index,
    )

    try:
        # Generate embedding via LLM service
        settings = get_settings()
        client = await _get_http_client()

        response = await client.post(
            f"{settings.llm_service_url}/api/v1/embeddings",
            json={"text": content},
        )
        response.raise_for_status()
        embedding_data = response.json()
        embedding = embedding_data["embedding"]

        # Ensure Qdrant collection exists
        await ensure_collection()

        # Store chunk in PostgreSQL (without embedding)
        point_id = uuid.uuid4()
        async with get_db_session() as session:
            # Fetch document title for Qdrant payload
            doc = await session.get(Document, document_id)
            doc_title = doc.title if doc else "Unknown"
            doc_type = doc.doc_type if doc else "text"
            doc_created_at = doc.created_at.isoformat() if doc and doc.created_at else None

            chunk = Chunk(
                document_id=document_id,
                content=content,
                chunk_index=chunk_index,
                qdrant_point_id=point_id,
                token_count=message.get("token_count", 0),
                metadata_=message.get("metadata", {}),
            )
            session.add(chunk)
            await session.flush()

            # Upsert vector + full payload into Qdrant
            await upsert_vectors(
                [
                    qdrant_models.PointStruct(
                        id=str(point_id),
                        vector=embedding,
                        payload={
                            "chunk_id": str(chunk.id),
                            "document_id": str(document_id),
                            "document_title": doc_title,
                            "tenant_id": tenant_id,
                            "chunk_index": chunk_index,
                            "content": content,
                            "token_count": message.get("token_count", 0),
                            "metadata": message.get("metadata", {}),
                            "doc_type": doc_type,
                            "created_at": doc_created_at,
                        },
                    )
                ]
            )

            # Check if all chunks for this document are processed
            await _check_document_completion(session, document_id)

        logger.info(
            "Embedding stored for document %s, chunk %d (qdrant_point=%s)",
            document_id,
            chunk_index,
            point_id,
        )

    except Exception:
        logger.exception(
            "Failed to process embedding for document %s, chunk %d",
            document_id,
            chunk_index,
        )
        # Update document status to FAILED
        await _mark_document_failed(document_id)
        raise


async def _check_document_completion(session: Any, document_id: str) -> None:
    """Check if all chunks for a document have been processed."""
    from sqlalchemy import func, select

    doc = await session.get(Document, document_id)
    if not doc:
        return

    # Count chunks with Qdrant point IDs (i.e. embedding was stored)
    chunk_count_query = select(func.count(Chunk.id)).where(
        Chunk.document_id == document_id,
        Chunk.qdrant_point_id.isnot(None),
    )
    processed_count = (await session.execute(chunk_count_query)).scalar() or 0

    if processed_count >= doc.chunk_count and doc.chunk_count > 0:
        doc.status = DocumentStatus.COMPLETED
        logger.info(
            "Document %s completed: %d/%d chunks processed",
            document_id,
            processed_count,
            doc.chunk_count,
        )


async def _mark_document_failed(document_id: str) -> None:
    """Mark a document as failed."""
    try:
        async with get_db_session() as session:
            doc = await session.get(Document, document_id)
            if doc and doc.status != DocumentStatus.COMPLETED:
                doc.status = DocumentStatus.FAILED
                doc.error_message = "Embedding generation failed"
    except Exception:
        logger.exception("Failed to update document status for %s", document_id)
