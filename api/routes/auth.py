"""
Authentication Routes.

Handles user registration, login, token refresh, and user info.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.core.rate_limiter import RateLimitAuth
from api.models.orm import User
from api.models.schemas import UserResponse
from api.services.jwt import TokenError, create_token_pair, verify_token_type
from api.services.user_service import UserService

router = APIRouter()


# ===========================================
# Request/Response Models
# ===========================================


class UserRegister(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")


class UserLogin(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response."""

    user_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


# ===========================================
# Endpoints
# ===========================================


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    responses={
        201: {"description": "User registered successfully"},
        409: {"description": "Email already registered"},
        429: {"description": "Too many requests"},
    },
)
async def register(
    user: UserRegister,
    db: AsyncSession = Depends(get_db),
    _rate_limit: RateLimitAuth,
) -> TokenResponse:
    """
    Register a new user.

    - Validates email format
    - Hashes password with bcrypt
    - Creates user in database
    - Returns JWT tokens
    """
    user_service = UserService(db)

    # Check if email already exists
    if await user_service.email_exists(user.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    new_user = await user_service.create(user.email, user.password)

    # Generate tokens
    access_token, refresh_token = create_token_pair(new_user.id)

    return TokenResponse(
        user_id=str(new_user.id),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user",
    responses={
        200: {"description": "Login successful"},
        401: {"description": "Invalid credentials"},
        429: {"description": "Too many requests"},
    },
)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
    _rate_limit: RateLimitAuth,
) -> TokenResponse:
    """
    Authenticate user and return tokens.

    - Validates credentials
    - Returns access and refresh tokens
    """
    user_service = UserService(db)

    # Authenticate user
    user = await user_service.authenticate(credentials.email, credentials.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate tokens
    access_token, refresh_token = create_token_pair(user.id)

    return TokenResponse(
        user_id=str(user.id),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Refresh access token using refresh token.

    - Validates refresh token
    - Verifies user still exists and is active
    - Returns new access and refresh tokens
    """
    try:
        payload = verify_token_type(request.refresh_token, "refresh")
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

    # Generate new tokens
    access_token, new_refresh_token = create_token_pair(user.id)

    return TokenResponse(
        user_id=str(user.id),
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    responses={
        200: {"description": "Current user info"},
        401: {"description": "Not authenticated"},
    },
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get current authenticated user info.

    Requires valid access token in Authorization header.
    """
    return UserResponse.model_validate(current_user)
