"""
API Gateway - Main FastAPI Application.

Central entry point that proxies requests to internal microservices,
handles authentication, rate limiting, CORS, and observability.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.cache import close_cache, get_cache
from shared.config import get_settings
from shared.observability import instrument_fastapi, setup_observability

from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import admin, documents, health, query

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()

    # Startup
    setup_observability("api-gateway")
    logger.info("API Gateway starting up...")

    # Initialize Redis cache for rate limiting
    cache = await get_cache()
    logger.info("Redis cache connected")

    # Create shared HTTP client for proxying
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.settings = settings

    yield

    # Shutdown
    await app.state.http_client.aclose()
    await close_cache()
    logger.info("API Gateway shut down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="RAG Microservice Platform - API Gateway",
        description="Production-grade RAG platform with microservice architecture",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )
    app.add_middleware(RateLimitMiddleware)

    # ── Routers ──────────────────────────────────────────
    app.include_router(health.router, tags=["Health"])
    app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])
    app.include_router(query.router, prefix="/api/v1", tags=["Query"])
    app.include_router(admin.router, prefix="/api/v1", tags=["Admin"])

    # ── OTel Instrumentation ─────────────────────────────
    instrument_fastapi(app)

    return app


app = create_app()
