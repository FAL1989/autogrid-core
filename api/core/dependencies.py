"""
FastAPI Dependencies.

Shared dependencies for authentication and authorization.
"""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.orm import User
from api.services.jwt import TokenError, verify_token_type
from api.services.user_service import UserService

# Security scheme for Bearer token authentication
security = HTTPBearer(
    scheme_name="Bearer",
    description="JWT access token",
    auto_error=True,
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get the current authenticated user from JWT token.

    Extracts the Bearer token from Authorization header,
    validates it, and returns the corresponding user.

    Args:
        credentials: HTTP Authorization credentials with Bearer token.
        db: Database session.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found.
    """
    token = credentials.credentials

    try:
        payload = verify_token_type(token, "access")
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user_service = UserService(db)
    user = await user_service.get_by_id(UUID(payload.sub))

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get current user and verify they are active.

    This is an alias for get_current_user since it already
    checks for active status, but provides semantic clarity.

    Args:
        current_user: The authenticated user.

    Returns:
        The active User object.
    """
    return current_user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Get current user if authenticated, None otherwise.

    Use this for endpoints that work for both authenticated
    and unauthenticated users but may provide enhanced
    functionality for authenticated users.

    Args:
        credentials: Optional HTTP Authorization credentials.
        db: Database session.

    Returns:
        User if authenticated, None otherwise.
    """
    if credentials is None:
        return None

    try:
        payload = verify_token_type(credentials.credentials, "access")
    except TokenError:
        return None

    user_service = UserService(db)
    user = await user_service.get_by_id(UUID(payload.sub))

    if user is None or not user.is_active:
        return None

    return user
