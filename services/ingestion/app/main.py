"""
Ingestion Service - Main FastAPI Application.

Handles document upload, text extraction, chunking, and publishing
chunks to RabbitMQ for async embedding generation.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from shared.cache import close_cache, get_cache
from shared.database import dispose_engine
from shared.messaging import close_publisher, get_publisher
from shared.observability import instrument_fastapi, setup_observability

from app.routers import ingest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan hooks."""
    setup_observability("ingestion-service")
    logger.info("Ingestion service starting up...")

    # Initialize connections
    await get_cache()
    await get_publisher()
    logger.info("All connections established")

    yield

    # Cleanup
    await close_publisher()
    await close_cache()
    await dispose_engine()
    logger.info("Ingestion service shut down.")


def create_app() -> FastAPI:
    """Create the Ingestion service FastAPI app."""
    app = FastAPI(
        title="RAG Platform - Ingestion Service",
        description="Document ingestion with LangGraph pipeline",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    app.include_router(ingest.router, prefix="/api/v1", tags=["Ingestion"])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy", "service": "ingestion"}

    instrument_fastapi(app)
    return app


app = create_app()
