"""Pydantic schemas for Query / RAG endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RetrievalFilters(BaseModel):
    """Optional filters applied during the retrieval stage."""

    document_ids: list[str] | None = Field(
        default=None,
        description="Only search within these specific document IDs.",
    )
    doc_types: list[str] | None = Field(
        default=None,
        description="Filter by document type (e.g. 'pdf', 'text', 'md', 'html').",
    )
    date_from: datetime | None = Field(
        default=None,
        description="Only include documents created on or after this date (ISO-8601).",
    )
    date_to: datetime | None = Field(
        default=None,
        description="Only include documents created on or before this date (ISO-8601).",
    )
    metadata_filters: dict[str, str | int | float | bool | list] | None = Field(
        default=None,
        description=(
            "Key-value pairs to match against the document/chunk JSONB metadata column. "
            "Example: {'source': 'frontend-file-upload', 'page_count': 5}"
        ),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "doc_types": ["pdf"],
                "date_from": "2025-01-01T00:00:00Z",
                "metadata_filters": {"source": "frontend-file-upload"},
            }
        }
    }


class QueryRequest(BaseModel):
    """Schema for a RAG query request."""

    question: str = Field(
        ..., min_length=1, max_length=2000, description="User question"
    )
    tenant_id: str = Field(default="default", description="Tenant identifier")
    top_k: int = Field(
        default=5, ge=1, le=50, description="Number of chunks to retrieve"
    )
    rerank: bool = Field(default=True, description="Whether to apply reranking")
    stream: bool = Field(default=False, description="Whether to stream the response")
    filters: RetrievalFilters | None = Field(
        default=None,
        description="Optional advanced filters to narrow the retrieval scope.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Conversation ID for multi-turn memory. Omit for stateless queries.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "question": "What is the main purpose of the system?",
                "tenant_id": "default",
                "top_k": 5,
                "rerank": True,
                "filters": {
                    "doc_types": ["pdf"],
                    "metadata_filters": {"source": "frontend-file-upload"},
                },
                "conversation_id": "conv-abc-123",
            }
        }
    }


class RetrievedChunk(BaseModel):
    """A chunk retrieved during the RAG process."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    score: float = Field(ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class Citation(BaseModel):
    """Citation reference in the generated answer."""

    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID
    relevance_score: float
    excerpt: str


class QueryResponse(BaseModel):
    """Schema for a RAG query response."""

    query_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    model: str = ""
    latency_ms: float = 0.0
    conversation_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
