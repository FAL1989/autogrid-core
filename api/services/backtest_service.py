"""
Backtest service.

Handles historical data loading, strategy simulation, and result storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import Backtest


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class SimTrade:
    timestamp: datetime
    side: Literal["buy", "sell"]
    price: float
    quantity: float
    realized_pnl: float


class BacktestService:
    """Run and persist backtests."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def run_and_store(
        self,
        *,
        user_id: UUID,
        strategy: Literal["grid", "dca"],
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        config: dict[str, Any],
        exchange_id: str = "binance",
    ) -> Backtest:
        candles = await self._fetch_ohlcv(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        if not candles:
            raise ValueError("No historical data returned for the requested range.")

        if strategy == "grid":
            results = self._simulate_grid(candles, config)
        else:
            results = self._simulate_dca(candles, config)

        backtest = Backtest(
            user_id=user_id,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            config=config,
            results=results,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )

        self.db.add(backtest)
        await self.db.commit()
        await self.db.refresh(backtest)
        return backtest

    async def list_for_user(
        self, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[Backtest], int]:
        stmt = (
            select(Backtest)
            .where(Backtest.user_id == user_id)
            .order_by(Backtest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Backtest).where(
            Backtest.user_id == user_id
        )
        result = await self.db.execute(stmt)
        count_result = await self.db.execute(count_stmt)
        return result.scalars().all(), count_result.scalar_one()

    async def get_for_user(self, backtest_id: UUID, user_id: UUID) -> Backtest | None:
        stmt = select(Backtest).where(
            Backtest.id == backtest_id, Backtest.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _fetch_ohlcv(
        self,
        *,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Candle]:
        import ccxt.async_support as ccxt

        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({"enableRateLimit": True})

        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        candles: list[Candle] = []
        since = start_ms
        timeframe_seconds = exchange.parse_timeframe(timeframe)
        step_ms = timeframe_seconds * 1000

        try:
            while since < end_ms:
                batch = await exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=1000
                )
                if not batch:
                    break

                for row in batch:
                    ts, o, h, l, c, v = row
                    if ts < start_ms or ts > end_ms:
                        continue
                    candles.append(
                        Candle(
                            timestamp=datetime.fromtimestamp(
                                ts / 1000, tz=timezone.utc
                            ),
                            open=float(o),
                            high=float(h),
                            low=float(l),
                            close=float(c),
                            volume=float(v),
                        )
                    )

                last_ts = batch[-1][0]
                next_since = last_ts + step_ms
                if next_since <= since:
                    break
                since = next_since
        finally:
            await exchange.close()

        return candles

    def _simulate_grid(self, candles: list[Candle], config: dict[str, Any]) -> dict[str, Any]:
        lower = float(config["lower_price"])
        upper = float(config["upper_price"])
        grid_count = int(config["grid_count"])
        investment = float(config.get("investment", 0))

        if grid_count <= 0 or upper <= lower or investment <= 0:
            return self._empty_results()

        spacing = (upper - lower) / grid_count
        levels = [lower + i * spacing for i in range(grid_count + 1)]
        mid_index = grid_count // 2
        buy_levels = levels[: mid_index + 1]

        cash = investment
        per_level_investment = investment / max(len(buy_levels), 1)
        open_positions: dict[float, tuple[float, float]] = {}
        trades: list[SimTrade] = []
        equity_points: list[tuple[datetime, float]] = []

        for candle in candles:
            price = candle.close

            for level in buy_levels:
                if price <= level and level not in open_positions and cash >= per_level_investment:
                    quantity = per_level_investment / level
                    cash -= per_level_investment
                    open_positions[level] = (level, quantity)
                    trades.append(
                        SimTrade(
                            timestamp=candle.timestamp,
                            side="buy",
                            price=level,
                            quantity=quantity,
                            realized_pnl=0,
                        )
                    )

            to_close = []
            for entry_price, (level, quantity) in open_positions.items():
                target_price = entry_price + spacing
                if price >= target_price:
                    pnl = (target_price - entry_price) * quantity
                    cash += target_price * quantity
                    trades.append(
                        SimTrade(
                            timestamp=candle.timestamp,
                            side="sell",
                            price=target_price,
                            quantity=quantity,
                            realized_pnl=pnl,
                        )
                    )
                    to_close.append(entry_price)

            for entry_price in to_close:
                open_positions.pop(entry_price, None)

            inventory_value = sum(quantity * price for _, (_, quantity) in open_positions.items())
            equity_points.append((candle.timestamp, cash + inventory_value))

        return self._build_results(trades, equity_points, investment)

    def _simulate_dca(self, candles: list[Candle], config: dict[str, Any]) -> dict[str, Any]:
        amount = float(config.get("amount", 0))
        interval = str(config.get("interval", "daily"))
        trigger_drop = config.get("trigger_drop")
        take_profit = config.get("take_profit")

        if amount <= 0:
            return self._empty_results()

        interval_seconds = {
            "hourly": 3600,
            "daily": 86400,
            "weekly": 86400 * 7,
        }.get(interval, 86400)

        position_qty = 0.0
        total_cost = 0.0
        cash = 0.0
        last_buy_time: datetime | None = None
        recent_high = candles[0].close
        trades: list[SimTrade] = []
        equity_points: list[tuple[datetime, float]] = []
        total_invested = 0.0

        for candle in candles:
            price = candle.close
            recent_high = max(recent_high, price)

            should_buy = False
            if last_buy_time is None:
                should_buy = True
            else:
                delta = (candle.timestamp - last_buy_time).total_seconds()
                if delta >= interval_seconds:
                    should_buy = True

            if trigger_drop:
                drop_pct = (recent_high - price) / recent_high * 100
                if drop_pct >= float(trigger_drop):
                    should_buy = True

            if should_buy:
                quantity = amount / price
                position_qty += quantity
                total_cost += amount
                total_invested += amount
                last_buy_time = candle.timestamp
                recent_high = price
                trades.append(
                    SimTrade(
                        timestamp=candle.timestamp,
                        side="buy",
                        price=price,
                        quantity=quantity,
                        realized_pnl=0,
                    )
                )

            if position_qty > 0 and take_profit:
                avg_entry = total_cost / position_qty
                if price >= avg_entry * (1 + float(take_profit) / 100):
                    pnl = (price - avg_entry) * position_qty
                    cash += price * position_qty
                    trades.append(
                        SimTrade(
                            timestamp=candle.timestamp,
                            side="sell",
                            price=price,
                            quantity=position_qty,
                            realized_pnl=pnl,
                        )
                    )
                    position_qty = 0.0
                    total_cost = 0.0

            equity_points.append((candle.timestamp, cash + position_qty * price))

        initial_capital = max(total_invested, 1.0)
        return self._build_results(trades, equity_points, initial_capital)

    def _build_results(
        self, trades: list[SimTrade], equity_points: list[tuple[datetime, float]], initial_capital: float
    ) -> dict[str, Any]:
        equity_curve = self._downsample_equity(equity_points)
        equity_values = [point["value"] for point in equity_curve]

        total_return = (
            (equity_values[-1] - initial_capital) / initial_capital
            if equity_values
            else 0.0
        )
        sharpe_ratio = self._calculate_sharpe(equity_values)
        max_drawdown = self._calculate_max_drawdown(equity_values)

        wins = sum(1 for trade in trades if trade.realized_pnl > 0)
        total_trades = len(trades)
        win_rate = wins / total_trades if total_trades else 0.0

        gross_profit = sum(trade.realized_pnl for trade in trades if trade.realized_pnl > 0)
        gross_loss = abs(sum(trade.realized_pnl for trade in trades if trade.realized_pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        return {
            "total_return": float(total_return),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "total_trades": total_trades,
            "equity_curve": equity_curve,
        }

    def _calculate_sharpe(self, equity_values: list[float]) -> float:
        if len(equity_values) < 2:
            return 0.0
        returns = []
        for i in range(1, len(equity_values)):
            prev = equity_values[i - 1]
            if prev == 0:
                returns.append(0.0)
            else:
                returns.append((equity_values[i] - prev) / prev)
        if not returns:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / max(len(returns) - 1, 1)
        std_dev = variance ** 0.5
        if std_dev == 0:
            return 0.0
        return mean_return / std_dev * (len(returns) ** 0.5)

    def _calculate_max_drawdown(self, equity_values: list[float]) -> float:
        if not equity_values:
            return 0.0
        peak = equity_values[0]
        max_dd = 0.0
        for value in equity_values:
            peak = max(peak, value)
            drawdown = (peak - value) / peak if peak else 0.0
            max_dd = max(max_dd, drawdown)
        return max_dd

    def _downsample_equity(
        self, equity_points: list[tuple[datetime, float]], max_points: int = 200
    ) -> list[dict[str, Any]]:
        if not equity_points:
            return []

        if len(equity_points) <= max_points:
            return [
                {"date": ts.date().isoformat(), "value": float(value)}
                for ts, value in equity_points
            ]

        step = max(1, len(equity_points) // max_points)
        sampled = equity_points[::step]
        if sampled[-1] != equity_points[-1]:
            sampled.append(equity_points[-1])
        return [
            {"date": ts.date().isoformat(), "value": float(value)}
            for ts, value in sampled
        ]

    def _empty_results(self) -> dict[str, Any]:
        return {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
            "equity_curve": [],
        }
