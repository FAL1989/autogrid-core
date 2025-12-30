"""
Reporting Routes.

Provides analytics endpoints for bot performance and trade exports.
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import Bot, Trade, User

router = APIRouter()


class BotPerformance(BaseModel):
    bot_id: UUID
    name: str
    strategy: str
    symbol: str
    status: str
    realized_pnl: float
    unrealized_pnl: float
    total_trades: int
    win_rate: float
    total_volume: float


class BotPerformanceResponse(BaseModel):
    bots: list[BotPerformance]


class StrategyComparison(BaseModel):
    strategy: Literal["grid", "dca"]
    total_bots: int
    total_trades: int
    win_rate: float
    total_pnl: float
    total_volume: float


class StrategyComparisonResponse(BaseModel):
    strategies: list[StrategyComparison]


@router.get("/bots", response_model=BotPerformanceResponse)
async def bot_performance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotPerformanceResponse:
    """Return performance metrics per bot."""
    trades_stmt = (
        select(
            Trade.bot_id.label("bot_id"),
            func.count().label("total_trades"),
            func.sum(
                case((Trade.realized_pnl > 0, 1), else_=0)
            ).label("winning_trades"),
            func.sum(Trade.price * Trade.quantity).label("total_volume"),
        )
        .join(Bot, Bot.id == Trade.bot_id)
        .where(Bot.user_id == current_user.id)
        .group_by(Trade.bot_id)
    )
    trades_result = await db.execute(trades_stmt)
    trade_stats = {
        row.bot_id: row for row in trades_result.mappings().all()
    }

    bots_stmt = select(Bot).where(Bot.user_id == current_user.id)
    bots_result = await db.execute(bots_stmt)

    performance = []
    for bot in bots_result.scalars().all():
        stats = trade_stats.get(bot.id)
        total_trades = int(stats.total_trades) if stats else 0
        winning_trades = int(stats.winning_trades) if stats else 0
        win_rate = winning_trades / total_trades if total_trades else 0.0
        total_volume = float(stats.total_volume or 0) if stats else 0.0

        performance.append(
            BotPerformance(
                bot_id=bot.id,
                name=bot.name,
                strategy=bot.strategy,
                symbol=bot.symbol,
                status=bot.status,
                realized_pnl=float(bot.realized_pnl),
                unrealized_pnl=float(bot.unrealized_pnl),
                total_trades=total_trades,
                win_rate=win_rate,
                total_volume=total_volume,
            )
        )

    return BotPerformanceResponse(bots=performance)


@router.get("/strategies", response_model=StrategyComparisonResponse)
async def strategy_comparison(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StrategyComparisonResponse:
    """Compare performance between strategies."""
    bots_stmt = select(Bot).where(Bot.user_id == current_user.id)
    bots_result = await db.execute(bots_stmt)
    bots = bots_result.scalars().all()

    trade_stmt = (
        select(
            Bot.strategy.label("strategy"),
            func.count(Trade.id).label("total_trades"),
            func.sum(
                case((Trade.realized_pnl > 0, 1), else_=0)
            ).label("winning_trades"),
            func.sum(Trade.price * Trade.quantity).label("total_volume"),
        )
        .join(Bot, Bot.id == Trade.bot_id)
        .where(Bot.user_id == current_user.id)
        .group_by(Bot.strategy)
    )
    trade_result = await db.execute(trade_stmt)
    trade_stats = {
        row.strategy: row for row in trade_result.mappings().all()
    }

    strategies = []
    for strategy in ["grid", "dca"]:
        strategy_bots = [bot for bot in bots if bot.strategy == strategy]
        total_bots = len(strategy_bots)
        total_pnl = sum(
            float(bot.realized_pnl + bot.unrealized_pnl)
            for bot in strategy_bots
        )

        stats = trade_stats.get(strategy)
        total_trades = int(stats.total_trades) if stats else 0
        winning_trades = int(stats.winning_trades) if stats else 0
        win_rate = winning_trades / total_trades if total_trades else 0.0
        total_volume = float(stats.total_volume or 0) if stats else 0.0

        strategies.append(
            StrategyComparison(
                strategy=strategy,  # type: ignore[arg-type]
                total_bots=total_bots,
                total_trades=total_trades,
                win_rate=win_rate,
                total_pnl=total_pnl,
                total_volume=total_volume,
            )
        )

    return StrategyComparisonResponse(strategies=strategies)


@router.get("/trades/export")
async def export_trades_csv(
    bot_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export trades to CSV."""
    stmt = (
        select(Trade, Bot)
        .join(Bot, Bot.id == Trade.bot_id)
        .where(Bot.user_id == current_user.id)
        .order_by(Trade.timestamp.desc())
    )
    if bot_id:
        stmt = stmt.where(Trade.bot_id == bot_id)

    result = await db.execute(stmt)

    def _generate():
        buffer = StringIO()
        buffer.write("timestamp,bot_id,bot_name,strategy,symbol,side,price,quantity,fee,fee_currency,realized_pnl\n")
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for trade, bot in result.all():
            buffer.write(
                f"{trade.timestamp.isoformat()},{trade.bot_id},{bot.name},{bot.strategy},"
                f"{trade.symbol},{trade.side},{trade.price},{trade.quantity},"
                f"{trade.fee},{trade.fee_currency or ''},{trade.realized_pnl or 0}\n"
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    filename = f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
