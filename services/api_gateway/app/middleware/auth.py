"""API Key authentication middleware."""

from __future__ import annotations

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from shared.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> str:
    """Verify the API key from the request header.

    Skips auth for health check endpoints.
    """
    # Skip auth for health endpoints
    if request.url.path in ("/health", "/ready", "/docs", "/redoc", "/openapi.json"):
        return "anonymous"

    settings = get_settings()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide it via X-API-Key header.",
        )

    if api_key not in settings.api_keys_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key
