"""Conversation and ChatMessage SQLAlchemy models."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base


class Conversation(Base):
    """A chat conversation session belonging to a tenant."""

    __tablename__ = "conversations"

    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True, default="default")
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="New Conversation")
    # The Redis-side conversation_id used for LLM memory (may differ from PK)
    memory_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    # Relationships
    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_conversations_tenant_updated", "tenant_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title='{self.title}')>"


class ChatMessage(Base):
    """A single message within a conversation."""

    __tablename__ = "chat_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional rich metadata: citations, model, latency_ms, etc.
    meta: Mapped[dict] = mapped_column("meta", JSONB, nullable=False, default=dict)
    # Ordering position within the conversation
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationship back to conversation
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("idx_chat_messages_conversation_position", "conversation_id", "position"),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role='{self.role}', conv={self.conversation_id})>"
