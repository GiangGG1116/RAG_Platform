"""
LangGraph RAG Pipeline.

StateGraph: analyze_query → retrieve → rerank → generate → cite
Full RAG pipeline with hybrid retrieval, reranking, and citation verification.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, TypedDict

import httpx
from langgraph.graph import END, StateGraph

from app.graphs.nodes import (
    analyze_query_node,
    cite_node,
    generate_node,
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


def build_rag_graph() -> StateGraph:
    """Build the LangGraph RAG pipeline."""
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


async def run_rag_pipeline(
    question: str,
    tenant_id: str,
    top_k: int,
    rerank: bool,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """Execute the RAG pipeline."""
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
