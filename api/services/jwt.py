"""
JWT Token Service.

Handles creation and validation of JWT access and refresh tokens.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from jose import JWTError, jwt
from pydantic import BaseModel

from api.core.config import get_settings


class TokenPayload(BaseModel):
    """JWT token payload structure."""

    sub: str  # Subject (user_id)
    type: Literal["access", "refresh"]
    exp: datetime
    iat: datetime


class TokenError(Exception):
    """Exception raised for token-related errors."""

    pass


def create_access_token(user_id: UUID) -> str:
    """
    Create a short-lived access token.

    Args:
        user_id: The user's UUID.

    Returns:
        Encoded JWT access token.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.jwt_expire_hours)

    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    """
    Create a long-lived refresh token.

    Args:
        user_id: The user's UUID.

    Returns:
        Encoded JWT refresh token.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_expire_days)

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token_pair(user_id: UUID) -> tuple[str, str]:
    """
    Create both access and refresh tokens.

    Args:
        user_id: The user's UUID.

    Returns:
        Tuple of (access_token, refresh_token).
    """
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    return access_token, refresh_token


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT token.

    Args:
        token: The encoded JWT token.

    Returns:
        TokenPayload with decoded data.

    Raises:
        TokenError: If token is invalid or expired.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(
            sub=payload["sub"],
            type=payload["type"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        )
    except JWTError as e:
        raise TokenError(f"Invalid token: {e}") from e
    except KeyError as e:
        raise TokenError(f"Missing token field: {e}") from e


def verify_token_type(token: str, expected_type: Literal["access", "refresh"]) -> TokenPayload:
    """
    Decode token and verify its type.

    Args:
        token: The encoded JWT token.
        expected_type: The expected token type ("access" or "refresh").

    Returns:
        TokenPayload if valid.

    Raises:
        TokenError: If token is invalid or wrong type.
    """
    payload = decode_token(token)

    if payload.type != expected_type:
        raise TokenError(f"Expected {expected_type} token, got {payload.type}")

    return payload
