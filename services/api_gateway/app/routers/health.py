"""Health check endpoints for liveness and readiness probes."""

import time

from fastapi import APIRouter, Request

from shared.cache import get_cache
from shared.schemas.health import HealthResponse, ServiceHealth

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe - always returns OK if the service is running."""
    return HealthResponse(status="healthy", version="1.0.0")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(request: Request) -> HealthResponse:
    """Readiness probe - checks all downstream dependencies."""
    services: list[ServiceHealth] = []
    overall_status = "healthy"

    # Check Redis
    try:
        start = time.perf_counter()
        cache = await get_cache()
        is_healthy = await cache.health_check()
        latency = round((time.perf_counter() - start) * 1000, 2)
        services.append(
            ServiceHealth(
                name="redis",
                status="healthy" if is_healthy else "unhealthy",
                latency_ms=latency,
            )
        )
        if not is_healthy:
            overall_status = "degraded"
    except Exception as e:
        services.append(ServiceHealth(name="redis", status="unhealthy", details=str(e)))
        overall_status = "degraded"

    # Check downstream services via HTTP
    http_client = request.app.state.http_client
    settings = request.app.state.settings

    for name, url in [
        ("ingestion", settings.ingestion_service_url),
        ("retrieval", settings.retrieval_service_url),
        ("llm-service", settings.llm_service_url),
    ]:
        try:
            start = time.perf_counter()
            resp = await http_client.get(f"{url}/health", timeout=5.0)
            latency = round((time.perf_counter() - start) * 1000, 2)
            services.append(
                ServiceHealth(
                    name=name,
                    status="healthy" if resp.status_code == 200 else "unhealthy",
                    latency_ms=latency,
                )
            )
        except Exception:
            services.append(ServiceHealth(name=name, status="unhealthy"))
            overall_status = "degraded"

    return HealthResponse(status=overall_status, version="1.0.0", services=services)
