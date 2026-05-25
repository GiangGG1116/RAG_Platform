"""
LLM Service - Main FastAPI Application.

Provides text generation, embedding, and reranking endpoints.
Supports OpenAI and local LLM providers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from shared.observability import instrument_fastapi, setup_observability

from app.providers import get_llm_provider
from app.routers import generate

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
