"""
Retrieval Service - Main FastAPI Application.

Handles RAG queries using LangGraph pipeline: query analysis,
hybrid retrieval, reranking, LLM generation, and citation.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI

from shared.cache import close_cache, get_cache
from shared.database import dispose_engine
from shared.observability import instrument_fastapi, setup_observability

from app.routers import query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan hooks."""
    setup_observability("retrieval-service")
    logger.info("Retrieval service starting up...")

    await get_cache()

    # HTTP client for calling LLM service
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0),
        limits=httpx.Limits(max_connections=50),
    )

    yield

    await app.state.http_client.aclose()
    await close_cache()
    await dispose_engine()
    logger.info("Retrieval service shut down.")


def create_app() -> FastAPI:
    """Create the Retrieval service FastAPI app."""
    app = FastAPI(
        title="RAG Platform - Retrieval Service",
        description="Hybrid retrieval and RAG generation with LangGraph",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    app.include_router(query.router, prefix="/api/v1", tags=["Query"])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy", "service": "retrieval"}

    instrument_fastapi(app)
    return app


app = create_app()
