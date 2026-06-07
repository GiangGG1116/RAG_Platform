"""Query endpoint - triggers the LangGraph RAG pipeline."""
import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from shared.schemas.query import QueryRequest, QueryResponse

from app.graphs.rag_graph import run_rag_pipeline, stream_rag_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse, 
    summary="Execute RAG query",
)
async def execute_query(
    query: QueryRequest,
    request: Request,
) -> Any:
    """Execute a RAG query through the LangGraph pipeline."""
    start = time.perf_counter()

    result = await run_rag_pipeline(
        question=query.question,
        tenant_id=query.tenant_id,
        top_k=query.top_k,
        rerank=query.rerank,
        http_client=request.app.state.http_client,
    )

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    result["latency_ms"] = latency_ms

    logger.info(
        "RAG query completed in %.2fms: '%s' → %d citations",
        latency_ms,
        query.question[:50],
        len(result.get("citations", [])),
    )
    return result


@router.post(
    "/query/stream",
    summary="Execute RAG query with streaming response (SSE)",
)
async def execute_query_stream(
    query: QueryRequest,
    request: Request,
) -> StreamingResponse:
    """Execute a RAG query and stream the answer token-by-token.

    Returns Server-Sent Events with the following event types:
      - ``status`` — pipeline progress updates
      - ``chunk`` — a generated token ({"token": "..."})
      - ``citations`` — citation list after generation completes
      - ``done`` — final metadata (query_id, model, latency_ms)
      - ``error`` — error details
    """
    return StreamingResponse(
        stream_rag_pipeline(
            question=query.question,
            tenant_id=query.tenant_id,
            top_k=query.top_k,
            rerank=query.rerank,
            http_client=request.app.state.http_client,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
