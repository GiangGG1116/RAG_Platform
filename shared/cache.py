"""
Redis caching layer with TTL support and cache invalidation.

Provides async Redis client wrapper for the RAG platform.
"""

import json
import logging
from typing import Any

import redis.asyncio as redis

from shared.config import get_settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache with JSON serialization and TTL management."""

    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Initialize Redis connection pool."""
        settings = get_settings()
        self._client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info("Redis cache connected")

    @property
    def client(self) -> redis.Redis:
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

    async def get(self, key: str) -> Any | None:
        """Get a cached value by key."""
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            logger.warning("Cache GET failed for key: %s", key, exc_info=True)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 3600,
    ) -> bool:
        """Set a cached value with TTL."""
        try:
            serialized = json.dumps(value, default=str)
            await self.client.set(key, serialized, ex=ttl_seconds)
            return True
        except Exception:
            logger.warning("Cache SET failed for key: %s", key, exc_info=True)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a cached key."""
        try:
            await self.client.delete(key)
            return True
        except Exception:
            logger.warning("Cache DELETE failed for key: %s", key, exc_info=True)
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern."""
        try:
            count = 0
            async for key in self.client.scan_iter(match=pattern, count=100):
                await self.client.delete(key)
                count += 1
            return count
        except Exception:
            logger.warning(
                "Cache DELETE_PATTERN failed for: %s", pattern, exc_info=True
            )
            return 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        try:
            return bool(await self.client.exists(key))
        except Exception:
            return False

    async def incr(self, key: str, ttl_seconds: int | None = None) -> int:
        """Increment a counter. Optionally set TTL on first increment."""
        try:
            value = await self.client.incr(key)
            if value == 1 and ttl_seconds:
                await self.client.expire(key, ttl_seconds)
            return value
        except Exception:
            logger.warning("Cache INCR failed for key: %s", key, exc_info=True)
            return 0

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            return await self.client.ping()
        except Exception:
            return False

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._client:
            await self._client.close()
            logger.info("Redis cache disconnected")


# ── Singleton Cache ──────────────────────────────────────
_cache: RedisCache | None = None


async def get_cache() -> RedisCache:
    """Get or create a singleton Redis cache."""
    global _cache
    if _cache is None:
        _cache = RedisCache()
        await _cache.connect()
    return _cache


async def close_cache() -> None:
    """Close the singleton cache."""
    global _cache
    if _cache:
        await _cache.close()
        _cache = None
