"""
Telegram webhook and linking routes.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import Bot, ExchangeCredential, User
from api.services.bot_event_service import record_bot_event
from api.services.bot_service import BotService
from api.services.credential_service import CredentialService
from api.services.telegram_link import (
    TelegramLinkTokenError,
    create_telegram_link_token,
    decode_telegram_link_token,
)
from api.services.telegram_service import send_message
from bot.exchange.connector import CCXTConnector
from bot.tasks import stop_trading_bot

router = APIRouter()


class TelegramLinkResponse(BaseModel):
    """Telegram link token response."""

    token: str
    expires_at: datetime
    start_command: str
    deep_link: str | None = None


class TelegramWebhookResponse(BaseModel):
    """Telegram webhook response."""

    ok: bool = True


_pending_stop: dict[str, dict[str, Any]] = {}
_pending_stop_ttl = timedelta(minutes=2)


def _parse_command(text: str) -> tuple[str, str | None]:
    """Extract command name and argument from a message."""
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "", None
    command = parts[0].split("@", 1)[0]
    argument = parts[1] if len(parts) > 1 else None
    return command.lower(), argument


async def _get_user_by_chat_id(chat_id: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    return result.scalar_one_or_none()


async def _link_chat_id(chat_id: str, user_id: UUID, db: AsyncSession) -> None:
    existing = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
    existing_user = existing.scalar_one_or_none()
    if existing_user and existing_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat already linked to another account",
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.telegram_chat_id = chat_id
    await db.flush()


async def _select_primary_credential(user_id: UUID, db: AsyncSession) -> ExchangeCredential | None:
    running_bot = await db.execute(
        select(Bot)
        .where(Bot.user_id == user_id, Bot.status == "running")
        .order_by(Bot.updated_at.desc())
        .limit(1)
    )
    bot = running_bot.scalar_one_or_none()
    if bot and bot.credential_id:
        credential = await db.get(ExchangeCredential, bot.credential_id)
        if credential:
            return credential

    latest = await db.execute(
        select(ExchangeCredential)
        .where(ExchangeCredential.user_id == user_id)
        .order_by(ExchangeCredential.created_at.desc())
        .limit(1)
    )
    return latest.scalar_one_or_none()


async def _handle_status(chat_id: str, db: AsyncSession) -> None:
    user = await _get_user_by_chat_id(chat_id, db)
    if not user:
        await send_message(chat_id, "Account not linked. Use /start <token> to connect.")
        return

    result = await db.execute(select(Bot).where(Bot.user_id == user.id))
    bots = list(result.scalars().all())
    if not bots:
        await send_message(chat_id, "Nenhum bot encontrado.")
        return

    counts = {
        "running": 0,
        "paused": 0,
        "stopped": 0,
        "error": 0,
        "starting": 0,
        "stopping": 0,
    }
    for bot in bots:
        counts[bot.status] = counts.get(bot.status, 0) + 1

    lines = [
        "<b>Bot Status</b>",
        "",
        f"Running: {counts.get('running', 0)}",
        f"Paused: {counts.get('paused', 0)}",
        f"Stopped: {counts.get('stopped', 0)}",
        f"Error: {counts.get('error', 0)}",
        f"Starting: {counts.get('starting', 0)}",
        f"Stopping: {counts.get('stopping', 0)}",
        "",
        "<b>Recent bots:</b>",
    ]
    for bot in bots[:5]:
        lines.append(f"- {bot.name} ({bot.symbol}) — {bot.status}")

    await send_message(chat_id, "\n".join(lines))


async def _handle_balance(chat_id: str, db: AsyncSession) -> None:
    user = await _get_user_by_chat_id(chat_id, db)
    if not user:
        await send_message(chat_id, "Account not linked. Use /start <token> to connect.")
        return

    credential = await _select_primary_credential(user.id, db)
    if not credential:
        await send_message(chat_id, "Nenhuma credencial encontrada para consultar saldo.")
        return

    service = CredentialService(db)
    api_key, api_secret = service.get_decrypted_keys(credential)

    connector = CCXTConnector(
        exchange_id=credential.exchange,
        api_key=api_key,
        api_secret=api_secret,
        testnet=credential.is_testnet,
    )

    try:
        await connector.connect()
        balance = await connector.fetch_balance()
    except Exception as exc:
        await send_message(chat_id, f"Falha ao buscar saldo: {exc}")
        return
    finally:
        try:
            await connector.disconnect()
        except Exception:
            pass

    totals = balance.get("total", {}) if isinstance(balance, dict) else {}
    filtered = {k: v for k, v in totals.items() if v}

    if not filtered:
        await send_message(chat_id, "Saldo retornou vazio.")
        return

    lines = ["<b>Balance</b>", f"Exchange: {credential.exchange}", ""]
    for asset, amount in list(filtered.items())[:10]:
        lines.append(f"{asset}: {amount}")

    await send_message(chat_id, "\n".join(lines))


async def _handle_stop(chat_id: str, arg: str | None, db: AsyncSession) -> None:
    user = await _get_user_by_chat_id(chat_id, db)
    if not user:
        await send_message(chat_id, "Account not linked. Use /start <token> to connect.")
        return

    result = await db.execute(
        select(Bot)
        .where(Bot.user_id == user.id, Bot.status.in_(["running", "paused", "starting"]))
        .order_by(Bot.updated_at.desc())
    )
    bots = list(result.scalars().all())

    if not bots:
        await send_message(chat_id, "Nenhum bot ativo para parar.")
        return

    selected = None
    if arg:
        for bot in bots:
            if str(bot.id).startswith(arg) or bot.name.lower() == arg.lower():
                selected = bot
                break
        if not selected:
            await send_message(chat_id, "Bot not found. Use /stop <bot_id>.")
            return
    elif len(bots) == 1:
        selected = bots[0]
    else:
        lines = ["Select a bot to stop:", ""]
        for bot in bots[:5]:
            lines.append(f"- {bot.name} ({bot.symbol}) - {bot.id}")
        lines.append("")
        lines.append("Use /stop <bot_id> and confirm with /confirm_stop.")
        await send_message(chat_id, "\n".join(lines))
        return

    _pending_stop[chat_id] = {
        "bot_id": str(selected.id),
        "expires_at": datetime.now(timezone.utc) + _pending_stop_ttl,
    }

    await send_message(
        chat_id,
        (
            "Confirm stopping the bot:\n"
            f"{selected.name} ({selected.symbol})\n\n"
            "Send /confirm_stop to proceed."
        ),
    )


async def _handle_confirm_stop(chat_id: str, db: AsyncSession) -> None:
    pending = _pending_stop.get(chat_id)
    if not pending:
        await send_message(chat_id, "No pending stop.")
        return

    if pending["expires_at"] < datetime.now(timezone.utc):
        _pending_stop.pop(chat_id, None)
        await send_message(chat_id, "Confirmation expired. Use /stop again.")
        return

    user = await _get_user_by_chat_id(chat_id, db)
    if not user:
        await send_message(chat_id, "Account not linked. Use /start <token> to connect.")
        return

    bot_service = BotService(db)
    bot = await bot_service.get_by_id_for_user(UUID(pending["bot_id"]), user.id)
    if not bot:
        await send_message(chat_id, "Bot not found.")
        return

    if bot.status == "stopped":
        await send_message(chat_id, "Bot is already stopped.")
        return

    if bot.status == "stopping":
        await send_message(chat_id, "Bot is already stopping.")
        return

    await bot_service.update_status(bot.id, "stopping")
    await record_bot_event(
        db=db,
        bot_id=bot.id,
        user_id=user.id,
        event_type="stop_requested",
        source="telegram",
        reason="user_request",
        metadata={"chat_id": chat_id, "command": "/confirm_stop"},
    )
    task = stop_trading_bot.delay(
        str(bot.id),
        source="telegram",
        reason="user_request",
        metadata={"chat_id": chat_id, "command": "/confirm_stop"},
    )

    _pending_stop.pop(chat_id, None)
    await send_message(
        chat_id,
        f"Stop iniciado. Task: {task.id}",
    )


@router.post("/link", response_model=TelegramLinkResponse)
async def create_telegram_link(
    current_user: User = Depends(get_current_user),
) -> TelegramLinkResponse:
    token, expires_at = create_telegram_link_token(current_user.id)
    settings = get_settings()
    start_command = f"/start {token}"
    deep_link = None
    if settings.telegram_bot_username:
        deep_link = f"https://t.me/{settings.telegram_bot_username}?start={token}"

    return TelegramLinkResponse(
        token=token,
        expires_at=expires_at,
        start_command=start_command,
        deep_link=deep_link,
    )


@router.post("/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    current_user.telegram_chat_id = None
    await db.flush()
    return None


@router.post("/webhook", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TelegramWebhookResponse:
    settings = get_settings()
    if settings.telegram_webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message or not message.get("text"):
        return TelegramWebhookResponse(ok=True)

    chat_id = str(message["chat"]["id"])
    command, arg = _parse_command(message["text"])

    if command == "/start":
        if not arg:
            await send_message(chat_id, "Use /start <token> para conectar sua conta.")
            return TelegramWebhookResponse(ok=True)

        try:
            user_id = decode_telegram_link_token(arg)
            await _link_chat_id(chat_id, user_id, db)
            await send_message(chat_id, "Telegram conectado com sucesso.")
        except TelegramLinkTokenError:
            await send_message(chat_id, "Invalid or expired token. Generate a new link in the dashboard.")
        except HTTPException as exc:
            await send_message(chat_id, f"Falha ao conectar: {exc.detail}")
        return TelegramWebhookResponse(ok=True)

    if command == "/status":
        await _handle_status(chat_id, db)
    elif command == "/balance":
        await _handle_balance(chat_id, db)
    elif command == "/stop":
        await _handle_stop(chat_id, arg, db)
    elif command == "/confirm_stop":
        await _handle_confirm_stop(chat_id, db)
    else:
        await send_message(chat_id, "Unknown command. Use /status, /balance, or /stop.")

    return TelegramWebhookResponse(ok=True)
