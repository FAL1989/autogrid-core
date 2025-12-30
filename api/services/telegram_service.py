"""
Telegram service helpers.

Provides message delivery and notification helpers using Telegram Bot API.
"""

import logging
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.database import async_session_factory
from api.models.orm import User

logger = logging.getLogger(__name__)


async def send_message(chat_id: str, text: str, parse_mode: str | None = "HTML") -> None:
    """Send a message to a Telegram chat."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return

    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            if response.is_error:
                logger.warning("Telegram sendMessage failed: %s", response.text)
    except Exception as exc:
        logger.warning("Telegram sendMessage error: %s", exc)


async def set_webhook(url: str) -> None:
    """Configure Telegram webhook endpoint."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return

    payload = {"url": url}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(api_url, json=payload)
            if response.is_error:
                logger.warning("Telegram setWebhook failed: %s", response.text)
    except Exception as exc:
        logger.warning("Telegram setWebhook error: %s", exc)


async def get_user_chat_id(
    user_id: UUID, db: AsyncSession | None = None
) -> str | None:
    """Lookup a user's Telegram chat ID."""
    if db is None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User.telegram_chat_id).where(User.id == user_id)
            )
            return result.scalar_one_or_none()

    result = await db.execute(select(User.telegram_chat_id).where(User.id == user_id))
    return result.scalar_one_or_none()


async def notify_order_filled(
    user_id: UUID,
    symbol: str,
    side: str,
    quantity: Decimal | float,
    price: Decimal | float,
) -> None:
    """Notify user about a filled order."""
    chat_id = await get_user_chat_id(user_id)
    if not chat_id:
        return

    message = (
        "<b>Order Filled</b>\n\n"
        f"Symbol: {symbol}\n"
        f"Side: {side.upper()}\n"
        f"Quantity: {float(quantity):,.6f}\n"
        f"Price: ${float(price):,.2f}"
    )
    await send_message(chat_id, message)


async def notify_error(user_id: UUID, error: str) -> None:
    """Notify user about a bot error."""
    chat_id = await get_user_chat_id(user_id)
    if not chat_id:
        return

    message = f"<b>Error</b>\n\n{error}"
    await send_message(chat_id, message)
