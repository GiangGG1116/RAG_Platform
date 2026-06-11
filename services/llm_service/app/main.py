"""
LLM Service - Main FastAPI Application.

Provides text generation, embedding, and reranking endpoints.
Supports OpenAI and local LLM providers.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.providers import get_llm_provider
from app.routers import generate
from shared.observability import instrument_fastapi, setup_observability

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan hooks."""
    setup_observability("llm-service")
    logger.info("LLM service starting up...")

    # Initialize LLM provider
    provider = get_llm_provider()
    app.state.llm_provider = provider
    logger.info("LLM provider initialized: %s", type(provider).__name__)

    yield

    logger.info("LLM service shut down.")


def create_app() -> FastAPI:
    """Create the LLM service FastAPI app."""
    app = FastAPI(
        title="RAG Platform - LLM Service",
        description="LLM orchestration with OpenAI and local model support",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )

    app.include_router(generate.router, prefix="/api/v1", tags=["LLM"])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy", "service": "llm-service"}

    instrument_fastapi(app)
    return app


app = create_app()
