"""Pydantic schemas for Conversation / Chat History endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── Request schemas ──────────────────────────────────────────


class ConversationCreate(BaseModel):
    """Create a new conversation."""

    tenant_id: str = Field(default="default")
    title: str = Field(default="New Conversation", max_length=500)
    memory_id: str | None = Field(default=None, description="Redis conversation_id if any")


class ConversationUpdate(BaseModel):
    """Update conversation title or memory_id."""

    title: str | None = Field(default=None, max_length=500)
    memory_id: str | None = Field(default=None)


class MessageCreate(BaseModel):
    """Append a message to a conversation."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)
    meta: dict[str, Any] = Field(default_factory=dict, description="citations, model, latency_ms …")


class BulkMessageCreate(BaseModel):
    """Append multiple messages at once (used for syncing from frontend)."""

    messages: list[MessageCreate]


# ── Response schemas ─────────────────────────────────────────


class ChatMessageResponse(BaseModel):
    """Single message response."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    meta: dict[str, Any]
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """Full conversation with its messages."""

    id: uuid.UUID
    tenant_id: str
    title: str
    memory_id: str | None
    messages: list[ChatMessageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    """Lightweight summary — no messages — for list views."""

    id: uuid.UUID
    tenant_id: str
    title: str
    memory_id: str | None
    message_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    """Paginated list of conversation summaries."""

    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int
    pages: int
