"""Redis-based sliding window rate limiting middleware."""

import logging
import time

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from shared.cache import get_cache
from shared.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding window rate limiter backed by Redis."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # Skip rate limiting for health endpoints
        if request.url.path in ("/health", "/ready"):
            return await call_next(request)

        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
        cache_key = f"rate_limit:{client_ip}"

        try:
            cache = await get_cache()
            current_count = await cache.incr(cache_key, ttl_seconds=settings.rate_limit_window_seconds)

            if current_count > settings.rate_limit_requests:
                logger.warning("Rate limit exceeded for %s: %d requests", client_ip, current_count)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded. Try again later."},
                    headers={
                        "Retry-After": str(settings.rate_limit_window_seconds),
                        "X-RateLimit-Limit": str(settings.rate_limit_requests),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            remaining = max(0, settings.rate_limit_requests - current_count)
            response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        except Exception:
            # If Redis is down, allow the request through (fail-open)
            logger.warning("Rate limiter failed, allowing request through", exc_info=True)
            return await call_next(request)
