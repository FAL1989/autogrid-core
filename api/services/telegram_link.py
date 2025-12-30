"""
Telegram link token service.

Generates short-lived tokens to link Telegram chat IDs to users.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt

from api.core.config import get_settings


class TelegramLinkTokenError(Exception):
    """Raised when a Telegram link token is invalid or expired."""


def create_telegram_link_token(user_id: UUID) -> tuple[str, datetime]:
    """
    Create a short-lived link token for Telegram /start.

    Returns:
        Tuple of (token, expires_at).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.telegram_link_token_exp_minutes)

    payload = {
        "sub": str(user_id),
        "type": "telegram_link",
        "exp": expires_at,
        "iat": now,
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_telegram_link_token(token: str) -> UUID:
    """
    Decode and validate a Telegram link token.

    Raises:
        TelegramLinkTokenError if token is invalid or expired.
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "telegram_link":
            raise TelegramLinkTokenError("Invalid token type")
        return UUID(payload["sub"])
    except JWTError as exc:
        raise TelegramLinkTokenError("Invalid or expired token") from exc
    except KeyError as exc:
        raise TelegramLinkTokenError("Invalid token payload") from exc
