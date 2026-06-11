"""
LangGraph Ingestion Pipeline.

StateGraph: validate → extract → chunk → publish
Orchestrates the document ingestion process with state tracking.
"""

import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.graphs.nodes import (
    chunk_text_node,
    extract_text_node,
    publish_to_queue_node,
    update_status_node,
    validate_document_node,
)

logger = logging.getLogger(__name__)


class IngestionState(TypedDict):
    """State passed through the ingestion pipeline."""

    document_id: str
    title: str
    content: str
    tenant_id: str
    # Populated during pipeline
    is_valid: bool
    extracted_text: str
    chunks: list[dict]
    chunk_count: int
    error: str | None
    status: str


def build_ingestion_graph() -> StateGraph:
    """Build the LangGraph ingestion pipeline."""
    workflow = StateGraph(IngestionState)

    # Add nodes
    workflow.add_node("validate", validate_document_node)
    workflow.add_node("extract", extract_text_node)
    workflow.add_node("chunk", chunk_text_node)
    workflow.add_node("publish", publish_to_queue_node)
    workflow.add_node("update_status", update_status_node)

    # Define edges
    workflow.set_entry_point("validate")
    workflow.add_conditional_edges(
        "validate",
        lambda state: "extract" if state.get("is_valid") else "update_status",
    )
    workflow.add_edge("extract", "chunk")
    workflow.add_edge("chunk", "publish")
    workflow.add_edge("publish", "update_status")
    workflow.add_edge("update_status", END)

    return workflow


# Compile the graph once at module level
ingestion_graph = build_ingestion_graph().compile()


async def run_ingestion_pipeline(
    document_id: str,
    content: str,
    title: str,
    tenant_id: str,
) -> IngestionState:
    """Execute the ingestion pipeline for a document."""
    initial_state: IngestionState = {
        "document_id": document_id,
        "title": title,
        "content": content,
        "tenant_id": tenant_id,
        "is_valid": False,
        "extracted_text": "",
        "chunks": [],
        "chunk_count": 0,
        "error": None,
        "status": "processing",
    }

    logger.info("Starting ingestion pipeline for document %s", document_id)
    result = await ingestion_graph.ainvoke(initial_state)
    logger.info(
        "Ingestion pipeline completed for document %s: status=%s, chunks=%d",
        document_id,
        result.get("status"),
        result.get("chunk_count", 0),
    )
    return result
