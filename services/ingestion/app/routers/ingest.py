"""Ingestion endpoints - document upload and management."""

import logging
import math
from typing import Any
from uuid import UUID

from app.graphs.ingestion_graph import run_ingestion_pipeline
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from shared.database import get_db_session
from shared.models.document import Document, DocumentStatus
from shared.schemas.document import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/ingest",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a new document",
)
async def ingest_document(payload: DocumentCreate) -> Any:
    """Create a document record and trigger the LangGraph ingestion pipeline."""
    async with get_db_session() as session:
        document = Document(
            title=payload.title,
            content=payload.content,
            doc_type=payload.doc_type,
            metadata_=payload.metadata,
            tenant_id=payload.tenant_id,
            status=DocumentStatus.PENDING,
        )
        session.add(document)
        await session.flush()

        doc_id = document.id
        logger.info("Document created: %s (%s)", doc_id, payload.title)

    # Trigger async ingestion pipeline (non-blocking)
    import asyncio

    asyncio.create_task(
        _run_pipeline_safe(
            str(doc_id), payload.content, payload.title, payload.tenant_id
        )
    )

    async with get_db_session() as session:
        result = await session.get(Document, doc_id)
        return _to_response(result)


async def _run_pipeline_safe(
    doc_id: str, content: str, title: str, tenant_id: str
) -> None:
    """Run ingestion pipeline with error handling."""
    try:
        await run_ingestion_pipeline(
            document_id=doc_id,
            content=content,
            title=title,
            tenant_id=tenant_id,
        )
    except BaseException as e:
        import asyncio

        is_cancelled = isinstance(e, asyncio.CancelledError)
        error_msg = (
            "Ingestion pipeline cancelled (system shutdown)"
            if is_cancelled
            else str(e) or "Ingestion pipeline failed"
        )

        logger.exception(
            "Ingestion pipeline error for document %s: %s", doc_id, error_msg
        )

        # Update document status to FAILED
        try:
            async with get_db_session() as session:
                doc = await session.get(Document, doc_id)
                if doc:
                    doc.status = DocumentStatus.FAILED
                    doc.error_message = error_msg
        except Exception as db_err:
            logger.error("Could not update document status to failed: %s", db_err)

        if is_cancelled:
            raise


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List documents",
)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    tenant_id: str = "default",
) -> Any:
    """List documents with pagination."""
    async with get_db_session() as session:
        # Count
        count_query = select(func.count(Document.id)).where(
            Document.tenant_id == tenant_id
        )
        total = (await session.execute(count_query)).scalar() or 0

        # Items
        offset = (page - 1) * page_size
        items_query = (
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(items_query)
        documents = result.scalars().all()

        return DocumentListResponse(
            items=[_to_response(doc) for doc in documents],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total > 0 else 0,
        )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document by ID",
)
async def get_document(document_id: UUID) -> Any:
    """Get a document by ID."""
    async with get_db_session() as session:
        doc = await session.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return _to_response(doc)


@router.get(
    "/documents/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Check document status",
)
async def get_document_status(document_id: UUID) -> Any:
    """Check document processing status."""
    async with get_db_session() as session:
        doc = await session.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentStatusResponse(
            id=doc.id,
            status=doc.status.value,
            chunk_count=doc.chunk_count,
            error_message=doc.error_message,
        )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(document_id: UUID) -> None:
    """Delete a document and its chunks."""
    async with get_db_session() as session:
        doc = await session.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        await session.delete(doc)


def _to_response(doc: Document) -> DocumentResponse:
    """Convert a Document model to response schema."""
    return DocumentResponse(
        id=doc.id,
        title=doc.title,
        doc_type=doc.doc_type,
        status=doc.status.value,
        metadata=doc.metadata_,
        tenant_id=doc.tenant_id,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )
