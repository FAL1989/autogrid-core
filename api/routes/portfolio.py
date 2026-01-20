"""
Portfolio Routes.

Aggregate portfolio value using exchange balances and bot performance.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import Bot, Trade, User
from api.services.credential_service import CredentialService
from bot.exchange.connector import CCXTConnector

logger = logging.getLogger(__name__)

router = APIRouter()

STABLECOINS = {
    "USD",
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "USDP",
    "FDUSD",
}
QUOTE_PRIORITY = ["USDT", "USDC", "USD", "BUSD", "DAI", "TUSD", "USDP", "FDUSD"]
MAX_CREDENTIALS = 200


class PortfolioSummary(BaseModel):
    total_value_usd: float
    total_pnl: float
    total_investment: float
    roi_percent: float
    active_bots: int
    total_trades: int
    by_exchange: dict[str, float]
    missing_prices: list[str]


async def _resolve_asset_price(
    connector: CCXTConnector,
    asset: str,
    price_cache: dict[str, Decimal | None],
) -> Decimal | None:
    """Resolve asset price in USD using common stablecoin pairs."""
    if asset in price_cache:
        return price_cache[asset]

    if asset in STABLECOINS:
        price_cache[asset] = Decimal("1")
        return price_cache[asset]

    for quote in QUOTE_PRIORITY:
        if asset == quote:
            price_cache[asset] = Decimal("1")
            return price_cache[asset]

        symbol = f"{asset}/{quote}"
        try:
            ticker = await connector.fetch_ticker(symbol)
        except Exception:
            continue

        last = (
            ticker.get("last")
            or ticker.get("close")
            or ticker.get("bid")
            or ticker.get("ask")
        )
        if last is None:
            continue

        price_cache[asset] = Decimal(str(last))
        return price_cache[asset]

    price_cache[asset] = None
    return None


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioSummary:
    """Return aggregated portfolio value using exchange balances."""
    credential_service = CredentialService(db)

    credentials, _ = await credential_service.list_by_user(
        current_user.id, limit=MAX_CREDENTIALS
    )

    total_value = Decimal("0")
    by_exchange: dict[str, Decimal] = {}
    missing_prices: set[str] = set()

    for credential in credentials:
        api_key, api_secret = credential_service.get_decrypted_keys(credential)
        connector = CCXTConnector(
            exchange_id=credential.exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=credential.is_testnet,
        )

        price_cache: dict[str, Decimal | None] = {}
        exchange_total = Decimal("0")

        try:
            await connector.connect()
            balance = await connector.fetch_balance()
            totals = balance.get("total") or {}

            for asset, amount in totals.items():
                if amount is None:
                    continue
                amount_decimal = Decimal(str(amount))
                if amount_decimal <= 0:
                    continue

                asset_symbol = str(asset).upper()
                price = await _resolve_asset_price(connector, asset_symbol, price_cache)
                if price is None:
                    missing_prices.add(asset_symbol)
                    continue

                exchange_total += amount_decimal * price
        except Exception as exc:
            logger.warning(
                "Portfolio summary failed for credential %s (%s): %s",
                credential.id,
                credential.exchange,
                exc,
            )
            continue
        finally:
            await connector.disconnect()

        by_exchange[credential.exchange] = (
            by_exchange.get(credential.exchange, Decimal("0")) + exchange_total
        )
        total_value += exchange_total

    bots_result = await db.execute(select(Bot).where(Bot.user_id == current_user.id))
    bots = list(bots_result.scalars().all())

    total_pnl = sum(
        (Decimal(str(bot.realized_pnl or 0)) + Decimal(str(bot.unrealized_pnl or 0)))
        for bot in bots
    )
    total_investment = sum(
        Decimal(str(bot.config.get("investment", 0) or 0)) for bot in bots
    )
    active_bots = sum(1 for bot in bots if bot.status == "running")

    total_trades = await db.scalar(
        select(func.count(Trade.id))
        .select_from(Trade)
        .join(Bot, Bot.id == Trade.bot_id)
        .where(Bot.user_id == current_user.id)
    )

    roi_percent = (
        (total_pnl / total_investment * Decimal("100"))
        if total_investment > 0
        else Decimal("0")
    )

    return PortfolioSummary(
        total_value_usd=float(total_value),
        total_pnl=float(total_pnl),
        total_investment=float(total_investment),
        roi_percent=float(roi_percent),
        active_bots=active_bots,
        total_trades=int(total_trades or 0),
        by_exchange={key: float(value) for key, value in by_exchange.items()},
        missing_prices=sorted(missing_prices),
    )
