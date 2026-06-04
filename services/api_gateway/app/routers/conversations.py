"""Conversation history endpoints — persisted in PostgreSQL.

This router handles all CRUD for persistent chat history:
  GET  /conversations              — list conversations (paginated)
  POST /conversations              — create a conversation
  GET  /conversations/{id}         — get conversation with all messages
  PATCH /conversations/{id}        — rename / update memory_id
  DELETE /conversations/{id}       — delete conversation + messages
  POST /conversations/{id}/messages — append message(s)
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import verify_api_key
from shared.database import get_db_session
from shared.models.conversation import ChatMessage, Conversation
from shared.schemas.conversation import (
    BulkMessageCreate,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationSummary,
    ConversationUpdate,
    MessageCreate,
    ChatMessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


# ── Helpers ──────────────────────────────────────────────────


async def _get_or_404(session: AsyncSession, conv_id: uuid.UUID) -> Conversation:
    """Fetch conversation or raise 404."""
    result = await session.execute(
        select(Conversation).where(Conversation.id == conv_id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _to_summary(conv: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conv.id,
        tenant_id=conv.tenant_id,
        title=conv.title,
        memory_id=conv.memory_id,
        message_count=len(conv.messages),
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def _to_response(conv: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conv.id,
        tenant_id=conv.tenant_id,
        title=conv.title,
        memory_id=conv.memory_id,
        messages=[
            ChatMessageResponse(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                meta=m.meta,
                position=m.position,
                created_at=m.created_at,
            )
            for m in sorted(conv.messages, key=lambda x: x.position)
        ],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


# ── Endpoints ────────────────────────────────────────────────


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations (paginated)",
)
async def list_conversations(
    tenant_id: str = Query(default="default"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Any:
    async with get_db_session() as session:
        # Total count
        count_result = await session.execute(
            select(func.count(Conversation.id)).where(
                Conversation.tenant_id == tenant_id
            )
        )
        total = count_result.scalar_one()

        # Paginated rows (newest first), eager-load messages for count
        offset = (page - 1) * page_size
        result = await session.execute(
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        convs = result.scalars().all()

        return ConversationListResponse(
            items=[_to_summary(c) for c in convs],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, math.ceil(total / page_size)),
        )


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
async def create_conversation(body: ConversationCreate) -> Any:
    async with get_db_session() as session:
        conv = Conversation(
            tenant_id=body.tenant_id,
            title=body.title,
            memory_id=body.memory_id,
        )
        session.add(conv)
        await session.flush()
        await session.refresh(conv)
        return _to_response(conv)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get conversation with all messages",
)
async def get_conversation(conversation_id: uuid.UUID) -> Any:
    async with get_db_session() as session:
        conv = await _get_or_404(session, conversation_id)
        return _to_response(conv)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update conversation title / memory_id",
)
async def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
) -> Any:
    async with get_db_session() as session:
        conv = await _get_or_404(session, conversation_id)
        if body.title is not None:
            conv.title = body.title
        if body.memory_id is not None:
            conv.memory_id = body.memory_id
        await session.flush()
        await session.refresh(conv)
        return _to_response(conv)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and all its messages",
)
async def delete_conversation(conversation_id: uuid.UUID) -> None:
    async with get_db_session() as session:
        conv = await _get_or_404(session, conversation_id)
        await session.delete(conv)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append one or multiple messages to a conversation",
)
async def add_messages(
    conversation_id: uuid.UUID,
    body: BulkMessageCreate,
) -> Any:
    async with get_db_session() as session:
        conv = await _get_or_404(session, conversation_id)

        # Determine next position index
        next_pos = len(conv.messages)

        for i, msg_in in enumerate(body.messages):
            msg = ChatMessage(
                conversation_id=conv.id,
                role=msg_in.role,
                content=msg_in.content,
                meta=msg_in.meta,
                position=next_pos + i,
            )
            session.add(msg)

        await session.flush()
        await session.refresh(conv)
        return _to_response(conv)
