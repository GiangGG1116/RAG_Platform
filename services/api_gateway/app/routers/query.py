"""Query/RAG endpoints - proxy to Retrieval service."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.middleware.auth import verify_api_key
from shared.schemas.query import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a question using RAG",
)
async def ask_question(
    query: QueryRequest,
    request: Request,
) -> Any:
    """Submit a RAG query. Returns generated answer with citations."""
    settings = request.app.state.settings
    client = request.app.state.http_client

    try:
        response = await client.post(
            f"{settings.retrieval_service_url}/api/v1/query",
            json=query.model_dump(),
            timeout=60.0,  # LLM calls can be slow
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Failed to proxy to retrieval service: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval service unavailable",
        ) from e
