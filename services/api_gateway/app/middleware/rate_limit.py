"""Redis-based sliding window rate limiting middleware.

Rate limits by authenticated user identity (API Key / JWT subject),
falling back to client IP for unauthenticated requests.
"""

import logging

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

        # Identify client: prefer API Key / JWT user, fallback to IP
        client_identity = self._get_client_identity(request)
        cache_key = f"rate_limit:{client_identity}"

        try:
            cache = await get_cache()
            current_count = await cache.incr(
                cache_key, ttl_seconds=settings.rate_limit_window_seconds
            )

            if current_count > settings.rate_limit_requests:
                logger.warning(
                    "Rate limit exceeded for %s: %d requests",
                    client_identity,
                    current_count,
                )
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
            logger.warning(
                "Rate limiter failed, allowing request through", exc_info=True
            )
            return await call_next(request)

    @staticmethod
    def _get_client_identity(request: Request) -> str:
        """Extract client identity for rate limiting.

        Priority: X-API-Key header > Authorization Bearer sub > Client IP.
        This ensures corporate users behind a shared NAT/proxy are rate-limited
        individually instead of collectively.
        """
        # Check API Key header
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{api_key[:16]}"

        # Check JWT from Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Use first 32 chars of token as identity (avoid decoding overhead)
            return f"jwt:{token[:32]}"

        # Fallback to IP
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"
