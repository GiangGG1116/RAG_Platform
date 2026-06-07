"""Query/RAG endpoints - proxy to Retrieval service."""
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

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
    """Submit a RAG query.

    If ``stream=true`` in the request body, returns a streaming
    ``text/event-stream`` response with token-by-token generation.
    Otherwise returns the complete JSON answer.
    """
    settings = request.app.state.settings
    client = request.app.state.http_client

    # ── Streaming mode ──────────────────────────────────────────
    if query.stream:
        return await _proxy_stream(client, settings, query)

    # ── Blocking mode (original) ────────────────────────────────
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


async def _proxy_stream(
    client: Any,
    settings: Any,
    query: QueryRequest,
) -> StreamingResponse:
    """Proxy SSE stream from the Retrieval service to the client."""

    async def _forward_events() -> AsyncIterator[str]:
        try:
            async with client.stream(
                "POST",
                f"{settings.retrieval_service_url}/api/v1/query/stream",
                json=query.model_dump(),
                timeout=120.0,
            ) as upstream:
                upstream.raise_for_status()
                async for line in upstream.aiter_lines():
                    # Forward SSE lines as-is, preserving event/data structure
                    yield f"{line}\n"
        except Exception as e:
            logger.error("Streaming proxy failed: %s", e)
            import json
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(
        _forward_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
