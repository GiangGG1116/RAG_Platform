"""API Authentication middleware — supports both JWT Bearer and legacy API Key."""

import logging

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from shared.auth import TokenData, UserRole, check_permission, verify_token
from shared.config import get_settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# Paths that skip auth entirely
SKIP_AUTH_PATHS = frozenset({"/health", "/ready", "/docs", "/redoc", "/openapi.json"})


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),  # noqa: B008
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),  # noqa: B008
) -> TokenData:
    """Verify authentication via JWT Bearer token or legacy API Key.

    Priority: JWT Bearer > API Key.
    Skips auth for health check endpoints.
    """
    # Skip auth for health endpoints
    if request.url.path in SKIP_AUTH_PATHS:
        return TokenData(sub="anonymous", role=UserRole.VIEWER)

    settings = get_settings()

    # ── Try JWT Bearer token first ────────────────────
    if bearer and bearer.credentials:
        try:
            token_data = verify_token(bearer.credentials)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

        # RBAC permission check
        if not check_permission(token_data.role, request.method, request.url.path):
            detail_msg = f"Role '{token_data.role.value}' does not have permission for {request.method} {request.url.path}"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail_msg,
            )

        # Store user info on request state for downstream use
        request.state.user = token_data
        return token_data

    # ── Fallback to legacy API Key ────────────────────
    if api_key:
        if api_key not in settings.api_keys_list:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key.",
            )
        # API Key users get editor role by default
        token_data = TokenData(sub=f"apikey:{api_key[:8]}...", role=UserRole.EDITOR)
        request.state.user = token_data
        return token_data

    # ── No credentials provided ───────────────────────
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )
