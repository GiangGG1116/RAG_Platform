"""
LangGraph RAG Pipeline.

StateGraph: analyze_query → retrieve → rerank → generate → cite
Full RAG pipeline with hybrid retrieval, reranking, and citation verification.
Supports both blocking (ainvoke) and streaming (SSE) execution modes.
"""
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from app.graphs.nodes import (
    analyze_query_node,
    cite_node,
    generate_node,
    generate_stream_node,
    rerank_node,
    retrieve_node,
)

logger = logging.getLogger(__name__)


class RAGState(TypedDict):
    """State passed through the RAG pipeline."""

    question: str
    tenant_id: str
    top_k: int
    rerank: bool
    http_client: Any  # httpx.AsyncClient
    # Populated during pipeline
    query_analysis: dict
    retrieved_chunks: list[dict]
    reranked_chunks: list[dict]
    answer: str
    citations: list[dict]
    model: str
    query_id: str
    error: str | None


def _build_retrieval_graph() -> StateGraph:
    """Build a partial graph for analyze → retrieve → rerank (no generation)."""
    workflow = StateGraph(RAGState)

    workflow.add_node("analyze_query", analyze_query_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("rerank", rerank_node)

    workflow.set_entry_point("analyze_query")
    workflow.add_edge("analyze_query", "retrieve")
    workflow.add_conditional_edges(
        "retrieve",
        lambda state: "rerank" if state.get("rerank") and state.get("retrieved_chunks") else END,
        {"rerank": "rerank", END: END},
    )
    workflow.add_edge("rerank", END)

    return workflow


def build_rag_graph() -> StateGraph:
    """Build the full LangGraph RAG pipeline."""
    workflow = StateGraph(RAGState)

    # Add nodes
    workflow.add_node("analyze_query", analyze_query_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("rerank", rerank_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("cite", cite_node)

    # Define edges
    workflow.set_entry_point("analyze_query")
    workflow.add_edge("analyze_query", "retrieve")
    workflow.add_conditional_edges(
        "retrieve",
        lambda state: "rerank" if state.get("rerank") and state.get("retrieved_chunks") else "generate",
    )
    workflow.add_edge("rerank", "generate")
    workflow.add_edge("generate", "cite")
    workflow.add_edge("cite", END)

    return workflow


# Compile once at module level
rag_graph = build_rag_graph().compile()
retrieval_graph = _build_retrieval_graph().compile()


async def run_rag_pipeline(
    question: str,
    tenant_id: str,
    top_k: int,
    rerank: bool,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Execute the full RAG pipeline (blocking mode)."""
    initial_state: RAGState = {
        "question": question,
        "tenant_id": tenant_id,
        "top_k": top_k,
        "rerank": rerank,
        "http_client": http_client,
        "query_analysis": {},
        "retrieved_chunks": [],
        "reranked_chunks": [],
        "answer": "",
        "citations": [],
        "model": "",
        "query_id": str(uuid.uuid4()),
        "error": None,
    }

    logger.info("Starting RAG pipeline for query: '%s'", question[:100])
    result = await rag_graph.ainvoke(initial_state)

    return {
        "query_id": result["query_id"],
        "question": result["question"],
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "retrieved_chunks": result.get("reranked_chunks") or result.get("retrieved_chunks", []),
        "model": result.get("model", ""),
    }


async def stream_rag_pipeline(
    question: str,
    tenant_id: str,
    top_k: int,
    rerank: bool,
    http_client: httpx.AsyncClient,
) -> AsyncIterator[str]:
    """Execute the RAG pipeline with streaming LLM generation.

    Runs retrieval stages synchronously, then streams the LLM answer
    token-by-token as Server-Sent Events (SSE).

    SSE event types:
        status   — pipeline progress updates
        chunk    — a generated token
        citations — citation list after generation completes
        done     — final metadata (query_id, model, latency_ms)
        error    — error details
    """
    query_id = str(uuid.uuid4())
    start = time.perf_counter()

    initial_state: RAGState = {
        "question": question,
        "tenant_id": tenant_id,
        "top_k": top_k,
        "rerank": rerank,
        "http_client": http_client,
        "query_analysis": {},
        "retrieved_chunks": [],
        "reranked_chunks": [],
        "answer": "",
        "citations": [],
        "model": "",
        "query_id": query_id,
        "error": None,
    }

    def _sse(event: str, data: Any) -> str:
        """Format a single SSE event."""
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        # ── Phase 1: Retrieval (blocking — fast) ────────────────
        yield _sse("status", {"message": "Đang phân tích câu hỏi..."})

        retrieval_result = await retrieval_graph.ainvoke(initial_state)

        chunks = retrieval_result.get("reranked_chunks") or retrieval_result.get("retrieved_chunks", [])
        n_chunks = len(chunks)
        yield _sse("status", {"message": f"Đã tìm thấy {n_chunks} đoạn tài liệu liên quan"})

        # ── Phase 2: Streaming LLM Generation ───────────────────
        yield _sse("status", {"message": "Đang tạo câu trả lời..."})

        full_answer = ""
        model_name = ""

        async for event in generate_stream_node(question, chunks, http_client):
            if "token" in event:
                full_answer += event["token"]
                yield _sse("chunk", {"token": event["token"]})
            if event.get("done"):
                model_name = event.get("model", "unknown")

        # ── Phase 3: Citation Extraction (blocking — fast) ──────
        cite_state = {
            "answer": full_answer,
            "reranked_chunks": chunks,
            "retrieved_chunks": retrieval_result.get("retrieved_chunks", []),
        }
        cite_result = await cite_node(cite_state)
        citations = cite_result.get("citations", [])

        yield _sse("citations", {"citations": citations})

        # ── Done ────────────────────────────────────────────────
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        yield _sse("done", {
            "query_id": query_id,
            "question": question,
            "model": model_name,
            "latency_ms": latency_ms,
        })

        logger.info(
            "Streaming RAG query completed in %.2fms: '%s' → %d citations",
            latency_ms, question[:50], len(citations),
        )

    except Exception as e:
        logger.exception("Streaming RAG pipeline failed")
        yield _sse("error", {"detail": str(e)})
