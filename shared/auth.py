"""
JWT Authentication with Role-Based Access Control (RBAC).

Provides token creation, verification, and role-based authorization
for the API Gateway. Supports both JWT Bearer tokens and legacy API Keys.
"""

import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from pydantic import BaseModel

from shared.config import get_settings

logger = logging.getLogger(__name__)


# ── Roles ────────────────────────────────────────────────
class UserRole(StrEnum):
    """Available user roles for RBAC."""

    ADMIN = "admin"  # Full access: CRUD + manage users
    EDITOR = "editor"  # Can ingest, query, and delete own documents
    VIEWER = "viewer"  # Can only query (read-only)


# ── Token Models ─────────────────────────────────────────
class TokenData(BaseModel):
    """Data extracted from a verified JWT token."""

    sub: str  # User ID or username
    role: UserRole = UserRole.VIEWER
    tenant_id: str = "default"
    exp: datetime | None = None


class TokenResponse(BaseModel):
    """Response returned when creating a token."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    role: str


# ── Token Operations ─────────────────────────────────────
def create_access_token(
    subject: str,
    role: UserRole = UserRole.VIEWER,
    tenant_id: str = "default",
    extra_claims: dict[str, Any] | None = None,
) -> TokenResponse:
    """Create a signed JWT access token."""
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload = {
        "sub": subject,
        "role": role.value,
        "tenant_id": tenant_id,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        role=role.value,
    )


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token. Raises ValueError on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenData(
            sub=payload["sub"],
            role=UserRole(payload.get("role", "viewer")),
            tenant_id=payload.get("tenant_id", "default"),
            exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except jwt.ExpiredSignatureError as e:
        raise ValueError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}") from e


# ── RBAC Permission Check ────────────────────────────────
# Maps endpoint patterns to minimum required role
ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.VIEWER: 1,
    UserRole.EDITOR: 2,
    UserRole.ADMIN: 3,
}

ENDPOINT_PERMISSIONS: dict[str, UserRole] = {
    # Query endpoints — viewer can access
    "POST:/api/v1/query": UserRole.VIEWER,
    # Document read endpoints — viewer can access
    "GET:/api/v1/documents": UserRole.VIEWER,
    # Document write endpoints — editor required
    "POST:/api/v1/documents": UserRole.EDITOR,
    "DELETE:/api/v1/documents": UserRole.EDITOR,
    # Admin endpoints
    "POST:/api/v1/admin/tokens": UserRole.ADMIN,
}


def check_permission(role: UserRole, method: str, path: str) -> bool:
    """Check if a role has permission for a given endpoint."""
    # Admin can do everything
    if role == UserRole.ADMIN:
        return True

    # Find the most specific matching endpoint
    endpoint_key = f"{method}:{path}"

    # Check exact match first
    if endpoint_key in ENDPOINT_PERMISSIONS:
        required_role = ENDPOINT_PERMISSIONS[endpoint_key]
        return ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[required_role]

    # Check prefix match (e.g., DELETE:/api/v1/documents/uuid)
    for pattern, required_role in ENDPOINT_PERMISSIONS.items():
        pattern_method, pattern_path = pattern.split(":", 1)
        if method == pattern_method and path.startswith(pattern_path):
            return ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[required_role]

    # Default: allow (for unregistered endpoints like health)
    return True
