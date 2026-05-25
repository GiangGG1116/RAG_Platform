"""Pydantic schemas for Document endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    """Schema for creating a new document."""

    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content: str = Field(..., min_length=1, description="Document text content")
    doc_type: str = Field(default="text", description="Document type: text, pdf, docx")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    tenant_id: str = Field(default="default", description="Tenant identifier")

    model_config = {"json_schema_extra": {
        "example": {
            "title": "Sample Document",
            "content": "This is a sample document for RAG processing.",
            "doc_type": "text",
            "metadata": {"author": "John Doe"},
            "tenant_id": "default",
        }
    }}


class ChunkResponse(BaseModel):
    """Schema for a chunk in responses."""

    id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    metadata: dict = Field(default_factory=dict)
    has_embedding: bool = False


class DocumentResponse(BaseModel):
    """Schema for document in responses."""

    id: uuid.UUID
    title: str
    doc_type: str
    status: str
    metadata: dict = Field(default_factory=dict)
    tenant_id: str
    chunk_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    """Schema for document status check."""

    id: uuid.UUID
    status: str
    chunk_count: int
    error_message: str | None = None


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int
