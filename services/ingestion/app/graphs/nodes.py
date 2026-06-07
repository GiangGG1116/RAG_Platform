"""
LangGraph node implementations for the Ingestion pipeline.

Each node receives the pipeline state, performs its work, and returns
updated state fields.
"""
import logging
from typing import Any

from shared.cache import get_cache
from shared.config import get_settings
from shared.database import get_db_session
from shared.messaging import ROUTING_KEY_EMBEDDING, get_publisher
from shared.models.document import Document, DocumentStatus
from shared.utils import hash_content

logger = logging.getLogger(__name__)

# ── Supported document types ────────────────────────────
SUPPORTED_TYPES = {"text", "pdf", "docx", "txt", "md", "html"}
MAX_CONTENT_LENGTH = 10_000_000  # 10MB


async def validate_document_node(state: dict[str, Any]) -> dict[str, Any]:
    """Validate document content and format."""
    content = state.get("content", "")

    if not content or not content.strip():
        return {
            "is_valid": False,
            "error": "Document content is empty",
            "status": "failed",
        }

    if len(content) > MAX_CONTENT_LENGTH:
        return {
            "is_valid": False,
            "error": f"Content exceeds max length of {MAX_CONTENT_LENGTH} characters",
            "status": "failed",
        }

    # Check for duplicate content
    content_hash = hash_content(content)
    cache = await get_cache()
    existing = await cache.get(f"doc_hash:{content_hash}")
    if existing:
        return {
            "is_valid": False,
            "error": f"Duplicate content detected (matches document {existing})",
            "status": "failed",
        }

    # Store hash for dedup
    await cache.set(f"doc_hash:{content_hash}", state["document_id"], ttl_seconds=86400)

    logger.info("Document %s validated successfully", state["document_id"])
    return {"is_valid": True}


async def extract_text_node(state: dict[str, Any]) -> dict[str, Any]:
    """Extract and clean text from document content.

    For now, handles plain text. Can be extended for PDF/DOCX extraction.
    """
    content = state.get("content", "")

    # Basic text cleaning
    extracted = content.strip()
    # Remove excessive whitespace
    import re
    extracted = re.sub(r"\n{3,}", "\n\n", extracted)
    extracted = re.sub(r" {2,}", " ", extracted)

    # Update document status to processing
    async with get_db_session() as session:
        doc = await session.get(Document, state["document_id"])
        if doc:
            doc.status = DocumentStatus.PROCESSING

    logger.info("Text extracted for document %s: %d chars", state["document_id"], len(extracted))
    return {"extracted_text": extracted}


async def chunk_text_node(state: dict[str, Any]) -> dict[str, Any]:
    """Split extracted text into overlapping chunks."""
    settings = get_settings()
    text = state.get("extracted_text", "")
    chunk_size = settings.chunk_size
    chunk_overlap = settings.chunk_overlap

    if not text:
        return {"chunks": [], "chunk_count": 0}

    chunks: list[dict] = []
    # Sentence-aware chunking
    sentences = _split_into_sentences(text)
    current_chunk = ""
    chunk_index = 0

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append({
                "content": current_chunk.strip(),
                "chunk_index": chunk_index,
                "token_count": len(current_chunk.split()),
                "metadata": {
                    "document_id": state["document_id"],
                    "title": state["title"],
                },
            })
            chunk_index += 1

            # Keep overlap
            words = current_chunk.split()
            overlap_words = words[-chunk_overlap:] if len(words) > chunk_overlap else words
            current_chunk = " ".join(overlap_words) + " " + sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence

    # Add last chunk
    if current_chunk.strip():
        chunks.append({
            "content": current_chunk.strip(),
            "chunk_index": chunk_index,
            "token_count": len(current_chunk.split()),
            "metadata": {
                "document_id": state["document_id"],
                "title": state["title"],
            },
        })

    logger.info(
        "Document %s chunked into %d chunks (size=%d, overlap=%d)",
        state["document_id"],
        len(chunks),
        chunk_size,
        chunk_overlap,
    )
    return {"chunks": chunks, "chunk_count": len(chunks)}


async def publish_to_queue_node(state: dict[str, Any]) -> dict[str, Any]:
    """Publish chunks to RabbitMQ for embedding generation."""
    chunks = state.get("chunks", [])
    if not chunks:
        return {"status": "completed"}

    publisher = await get_publisher()

    for chunk in chunks:
        await publisher.publish(
            routing_key=ROUTING_KEY_EMBEDDING,
            body={
                "document_id": state["document_id"],
                "tenant_id": state["tenant_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "token_count": chunk["token_count"],
                "metadata": chunk["metadata"],
            },
        )

    logger.info(
        "Published %d chunks for document %s to embedding queue",
        len(chunks),
        state["document_id"],
    )
    return {"status": "processing"}


async def update_status_node(state: dict[str, Any]) -> dict[str, Any]:
    """Update document status in the database."""
    doc_id = state["document_id"]
    error = state.get("error")
    chunk_count = state.get("chunk_count", 0)

    async with get_db_session() as session:
        doc = await session.get(Document, doc_id)
        if doc:
            if error:
                doc.status = DocumentStatus.FAILED
                doc.error_message = error
            elif chunk_count > 0:
                doc.status = DocumentStatus.PROCESSING  # Will become COMPLETED after embeddings
                doc.chunk_count = chunk_count
            else:
                doc.status = DocumentStatus.COMPLETED
                doc.chunk_count = 0

    final_status = "failed" if error else "processing"
    logger.info("Document %s status updated to %s", doc_id, final_status)
    return {"status": final_status}


def _split_into_sentences(text: str) -> list[str]:
    """Simple sentence splitting."""
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]
