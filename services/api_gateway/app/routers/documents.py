"""Document management endpoints - proxy to Ingestion service."""
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.middleware.auth import verify_api_key
from shared.schemas.document import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a new document",
)
async def create_document(
    document: DocumentCreate,
    request: Request,
) -> Any:
    """Submit a document for ingestion. Returns immediately with a tracking ID."""
    settings = request.app.state.settings
    client = request.app.state.http_client

    try:
        response = await client.post(
            f"{settings.ingestion_service_url}/api/v1/ingest",
            json=document.model_dump(),
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Failed to proxy to ingestion service: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion service unavailable",
        ) from e


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List all documents",
)
async def list_documents(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    tenant_id: str = "default",
) -> Any:
    """List documents with pagination."""
    settings = request.app.state.settings
    client = request.app.state.http_client

    try:
        response = await client.get(
            f"{settings.ingestion_service_url}/api/v1/documents",
            params={"page": page, "page_size": page_size, "tenant_id": tenant_id},
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Failed to proxy to ingestion service: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion service unavailable",
        ) from e


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
async def get_document(document_id: UUID, request: Request) -> Any:
    """Get a specific document by ID."""
    settings = request.app.state.settings
    client = request.app.state.http_client

    try:
        response = await client.get(
            f"{settings.ingestion_service_url}/api/v1/documents/{document_id}"
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to proxy to ingestion service: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion service unavailable",
        ) from e


@router.get(
    "/documents/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Check document processing status",
)
async def get_document_status(document_id: UUID, request: Request) -> Any:
    """Check the processing status of a document."""
    settings = request.app.state.settings
    client = request.app.state.http_client

    try:
        response = await client.get(
            f"{settings.ingestion_service_url}/api/v1/documents/{document_id}/status"
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to proxy: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion service unavailable",
        ) from e


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(document_id: UUID, request: Request) -> None:
    """Delete a document and all its chunks."""
    settings = request.app.state.settings
    client = request.app.state.http_client

    try:
        response = await client.delete(
            f"{settings.ingestion_service_url}/api/v1/documents/{document_id}"
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Document not found")
        response.raise_for_status()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to proxy: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion service unavailable",
        ) from e
