"""Admin endpoints — token management and system administration."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.middleware.auth import verify_api_key
from shared.auth import TokenData, TokenResponse, UserRole, create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class CreateTokenRequest(BaseModel):
    """Request body for creating a new JWT token."""

    username: str = Field(..., min_length=1, max_length=100)
    role: UserRole = UserRole.VIEWER
    tenant_id: str = "default"


@router.post(
    "/admin/tokens",
    response_model=TokenResponse,
    summary="Create a JWT access token",
)
async def create_token(
    body: CreateTokenRequest,
    request: Request,
) -> Any:
    """Create a new JWT token for a user. Requires ADMIN role."""
    user: TokenData = request.state.user

    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create tokens.",
        )

    token = create_access_token(
        subject=body.username,
        role=body.role,
        tenant_id=body.tenant_id,
    )

    logger.info(
        "Token created for user '%s' with role '%s' by admin '%s'",
        body.username,
        body.role.value,
        user.sub,
    )
    return token
