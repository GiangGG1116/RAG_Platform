"""
Async SQLAlchemy database engine and session management.

Provides connection pooling with health checks for production use.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from shared.config import get_settings


def create_engine(pool_size: int = 20, max_overflow: int = 10, use_null_pool: bool = False):
    """Create an async SQLAlchemy engine with connection pooling."""
    settings = get_settings()
    kwargs = {
        "echo": settings.log_level == "DEBUG",
        "future": True,
    }
    if use_null_pool:
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update({
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
        })
    return create_async_engine(settings.database_url, **kwargs)


# Default engine and session factory
engine = create_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session with automatic rollback on error."""
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def check_db_health() -> bool:
    """Check database connectivity."""
    try:
        async with get_db_session() as session:
            await session.execute("SELECT 1")  # type: ignore[arg-type]
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """Dispose the engine connection pool. Call during app shutdown."""
    await engine.dispose()
