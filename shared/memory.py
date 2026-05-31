"""
Conversation Memory — Redis-backed sliding window.

Stores chat history per conversation as a Redis list, with
configurable max turns and TTL for automatic expiration.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.cache import get_cache
from shared.config import get_settings

logger = logging.getLogger(__name__)

# Redis key prefix for conversation memory
_KEY_PREFIX = "memory"


def _memory_key(tenant_id: str, conversation_id: str) -> str:
    """Build the Redis key for a conversation."""
    return f"{_KEY_PREFIX}:{tenant_id}:{conversation_id}"


class ConversationMemory:
    """Redis-backed conversation memory with sliding window.

    Each conversation is stored as a Redis list of JSON-encoded messages.
    Messages follow the OpenAI chat format::

        {"role": "user", "content": "What is RAG?"}
        {"role": "assistant", "content": "RAG is..."}

    The sliding window keeps only the most recent ``max_turns`` pairs
    (i.e. ``max_turns * 2`` messages) to prevent prompt overflow.
    """

    async def get_history(
        self,
        tenant_id: str,
        conversation_id: str,
    ) -> list[dict[str, str]]:
        """Retrieve the conversation history.

        Returns:
            List of message dicts with ``role`` and ``content`` keys,
            ordered chronologically (oldest first).
        """
        if not conversation_id:
            return []

        settings = get_settings()
        cache = await get_cache()
        key = _memory_key(tenant_id, conversation_id)

        try:
            # Get all messages from the Redis list
            raw_messages = await cache.client.lrange(key, 0, -1)
            if not raw_messages:
                return []

            messages: list[dict[str, str]] = []
            for raw in raw_messages:
                try:
                    messages.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    continue

            # Return only the last N turns (sliding window)
            max_messages = settings.memory_max_turns * 2
            if len(messages) > max_messages:
                messages = messages[-max_messages:]

            logger.debug(
                "Loaded %d messages for conversation %s",
                len(messages),
                conversation_id,
            )
            return messages

        except Exception:
            logger.warning(
                "Failed to load conversation history for %s",
                conversation_id,
                exc_info=True,
            )
            return []

    async def add_turn(
        self,
        tenant_id: str,
        conversation_id: str,
        question: str,
        answer: str,
    ) -> None:
        """Append a Q&A turn to the conversation history.

        Pushes two messages (user + assistant) and trims the list
        to the configured sliding window size. Refreshes TTL on
        every write so active conversations stay alive.
        """
        if not conversation_id:
            return

        settings = get_settings()
        cache = await get_cache()
        key = _memory_key(tenant_id, conversation_id)
        max_messages = settings.memory_max_turns * 2

        try:
            pipe = cache.client.pipeline()

            # Push user and assistant messages
            user_msg = json.dumps({"role": "user", "content": question})
            assistant_msg = json.dumps({"role": "assistant", "content": answer})
            pipe.rpush(key, user_msg, assistant_msg)

            # Trim to sliding window (keep only the last N messages)
            pipe.ltrim(key, -max_messages, -1)

            # Refresh TTL
            pipe.expire(key, settings.memory_ttl_seconds)

            await pipe.execute()

            logger.debug(
                "Saved turn to conversation %s (window=%d)",
                conversation_id,
                settings.memory_max_turns,
            )

        except Exception:
            logger.warning(
                "Failed to save conversation turn for %s",
                conversation_id,
                exc_info=True,
            )

    async def clear(self, tenant_id: str, conversation_id: str) -> None:
        """Delete a conversation's history."""
        if not conversation_id:
            return

        cache = await get_cache()
        key = _memory_key(tenant_id, conversation_id)

        try:
            await cache.client.delete(key)
            logger.info("Cleared conversation %s", conversation_id)
        except Exception:
            logger.warning(
                "Failed to clear conversation %s",
                conversation_id,
                exc_info=True,
            )


# ── Singleton ────────────────────────────────────────────────
_memory: ConversationMemory | None = None


def get_memory() -> ConversationMemory:
    """Get or create a singleton ConversationMemory instance."""
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
