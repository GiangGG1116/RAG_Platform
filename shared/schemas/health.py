"""Pydantic schemas for health check endpoints."""
from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    """Health status of a single dependency."""

    name: str
    status: str = "healthy"
    latency_ms: float | None = None
    details: str = ""


class HealthResponse(BaseModel):
    """Aggregate health response."""

    status: str = "healthy"
    version: str = "1.0.0"
    services: list[ServiceHealth] = Field(default_factory=list)
