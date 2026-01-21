"""
Risk management engine for bots.

Tracks equity, stops, trailing, and reinforcements with DB persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import get_settings
from api.models.orm import RiskEvent, RiskState
from bot.strategies.base import BaseStrategy, Order

logger = logging.getLogger(__name__)


class RiskStatus(Enum):
    """Risk status states."""

    OK = "ok"
    PAUSED = "paused"
    PENDING_LIQUIDATION = "pending_liquidation"
    LIQUIDATED = "liquidated"


class RiskAction(Enum):
    """Actions required by the engine."""

    NONE = "none"
    PAUSE = "pause"
    PENDING_LIQUIDATION = "pending_liquidation"
    LIQUIDATE = "liquidate"
    RESUME = "resume"


@dataclass
class RiskDecision:
    """Decision returned by risk manager per tick."""

    status: RiskStatus
    action: RiskAction
    reason: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class RiskConfig:
    """Risk thresholds for a bot."""

    daily_stop_percent: Decimal
    weekly_stop_percent: Decimal
    monthly_stop_percent: Decimal
    daily_pause_hours: int
    two_step_wait_minutes: int
    trailing_percent: Decimal
    trailing_wait_minutes: int
    active_capital_percent: Decimal
    reserve_capital_percent: Decimal
    reinforcement_levels_percent: list[Decimal]


class RiskManager:
    """Risk manager for a single bot."""

    def __init__(
        self,
        bot_id: UUID,
        user_id: UUID,
        symbol: str,
        strategy: BaseStrategy,
        db_session: AsyncSession,
        profile: str | None = None,
    ) -> None:
        self.bot_id = bot_id
        self.user_id = user_id
        self.symbol = symbol
        self.strategy = strategy
        self.db = db_session
        self.settings = get_settings()
        self.profile = profile or self.settings.risk_default_profile
        self.base_symbol, self.quote_symbol = self._split_symbol(symbol)
        self._state: RiskState | None = None
        self._last_decision: RiskDecision = RiskDecision(
            status=RiskStatus.OK,
            action=RiskAction.NONE,
        )
        self.config = RiskConfig(
            daily_stop_percent=Decimal(str(self.settings.risk_daily_stop_percent)),
            weekly_stop_percent=Decimal(str(self.settings.risk_weekly_stop_percent)),
            monthly_stop_percent=Decimal(str(self.settings.risk_monthly_stop_percent)),
            daily_pause_hours=self.settings.risk_daily_pause_hours,
            two_step_wait_minutes=self.settings.risk_two_step_wait_minutes,
            trailing_percent=Decimal(str(self.settings.risk_trailing_percent)),
            trailing_wait_minutes=self.settings.risk_trailing_wait_minutes,
            active_capital_percent=Decimal(
                str(self.settings.risk_active_capital_percent)
            ),
            reserve_capital_percent=Decimal(
                str(self.settings.risk_reserve_capital_percent)
            ),
            reinforcement_levels_percent=[
                Decimal(str(value))
                for value in self.settings.risk_reinforcement_levels_percent
            ],
        )

    async def load_state(self) -> None:
        """Load persisted state for this bot."""
        result = await self.db.execute(
            select(RiskState).where(RiskState.bot_id == self.bot_id)
        )
        self._state = result.scalar_one_or_none()
        if self._state and self._state.investment_override:
            self._apply_investment_override(self._state.investment_override)

    async def update_state(
        self,
        current_price: Decimal,
        balance: dict[str, Any] | None,
    ) -> RiskDecision:
        """Update risk state using latest price and balance."""
        if balance is None:
            return self._last_decision

        equity_total = self._calculate_equity(balance, current_price)
        if equity_total <= 0:
            return self._last_decision

        state = await self._ensure_state(current_price, equity_total)
        now = datetime.now(timezone.utc)

        self._update_windows(state, equity_total, now)

        decision = await self._apply_existing_pauses(state, equity_total, now)
        if decision.action != RiskAction.NONE:
            await self._commit_state(state, decision)
            self._last_decision = decision
            return decision

        decision = await self._check_stops(state, equity_total, now)
        if decision.action != RiskAction.NONE:
            await self._commit_state(state, decision)
            self._last_decision = decision
            return decision

        decision = await self._check_trailing(state, equity_total, now)
        if decision.action != RiskAction.NONE:
            await self._commit_state(state, decision)
            self._last_decision = decision
            return decision

        await self._check_reinforcements(state, current_price, balance)

        decision = RiskDecision(status=RiskStatus.OK, action=RiskAction.NONE)
        self._last_decision = decision
        return decision

    def check_order(self, order: Order, current_price: Decimal) -> bool:
        """Check whether orders are allowed under current risk state."""
        if not self._state:
            return True

        if self._state.status in {
            RiskStatus.PAUSED.value,
            RiskStatus.PENDING_LIQUIDATION.value,
            RiskStatus.LIQUIDATED.value,
        }:
            return False

        return True

    def check_loss_limit(self, pnl: Decimal, investment: Decimal) -> bool:
        """Return whether loss limits allow trading."""
        return True

    def is_trading_allowed(self) -> bool:
        """Return whether trading is allowed."""
        if not self._state:
            return True
        return self._state.status == RiskStatus.OK.value

    async def _ensure_state(
        self,
        current_price: Decimal,
        equity_total: Decimal,
    ) -> RiskState:
        if self._state is not None:
            self._state.last_equity = equity_total
            return self._state

        now = datetime.now(timezone.utc)
        state = RiskState(
            bot_id=self.bot_id,
            user_id=self.user_id,
            status=RiskStatus.OK.value,
            equity_peak=equity_total,
            last_equity=equity_total,
            daily_peak=equity_total,
            weekly_peak=equity_total,
            monthly_peak=equity_total,
            daily_window_start=now,
            weekly_window_start=now,
            monthly_window_start=now,
            reference_price=current_price,
        )
        self.db.add(state)
        await self.db.commit()
        await self.db.refresh(state)
        self._state = state
        return state

    async def _apply_existing_pauses(
        self,
        state: RiskState,
        equity_total: Decimal,
        now: datetime,
    ) -> RiskDecision:
        if state.status == RiskStatus.LIQUIDATED.value:
            return RiskDecision(status=RiskStatus.LIQUIDATED, action=RiskAction.NONE)

        if state.pending_liquidation_until:
            if now < state.pending_liquidation_until:
                return RiskDecision(
                    status=RiskStatus.PENDING_LIQUIDATION,
                    action=RiskAction.NONE,
                    reason="pending_liquidation",
                    metadata={"equity": str(equity_total)},
                )

            pending_threshold = self._pending_threshold(state)
            if pending_threshold and self._is_below_threshold(
                state, equity_total, pending_threshold
            ):
                state.status = RiskStatus.LIQUIDATED.value
                return RiskDecision(
                    status=RiskStatus.LIQUIDATED,
                    action=RiskAction.LIQUIDATE,
                    reason=state.pending_reason or "pending_liquidation",
                    metadata={"equity": str(equity_total)},
                )

            state.pending_liquidation_until = None
            state.pending_reason = None
            state.status = RiskStatus.OK.value
            return RiskDecision(
                status=RiskStatus.OK,
                action=RiskAction.RESUME,
                reason="pending_liquidation_recovered",
                metadata={"equity": str(equity_total)},
            )

        if state.paused_until and now < state.paused_until:
            return RiskDecision(
                status=RiskStatus.PAUSED,
                action=RiskAction.NONE,
                reason="daily_pause",
                metadata={"equity": str(equity_total)},
            )

        if state.paused_until and now >= state.paused_until:
            state.paused_until = None
            state.status = RiskStatus.OK.value
            return RiskDecision(
                status=RiskStatus.OK,
                action=RiskAction.RESUME,
                reason="daily_pause_ended",
                metadata={"equity": str(equity_total)},
            )

        if state.trailing_pause_until:
            if now < state.trailing_pause_until:
                return RiskDecision(
                    status=RiskStatus.PAUSED,
                    action=RiskAction.NONE,
                    reason="trailing_pause",
                    metadata={"equity": str(equity_total)},
                )

            trailing_threshold = state.equity_peak * (
                Decimal("1") - (self.config.trailing_percent / Decimal("100"))
            )
            if equity_total >= trailing_threshold:
                state.trailing_pause_until = None
                state.status = RiskStatus.OK.value
                return RiskDecision(
                    status=RiskStatus.OK,
                    action=RiskAction.RESUME,
                    reason="trailing_recovered",
                    metadata={"equity": str(equity_total)},
                )

            state.trailing_pause_until = now + timedelta(
                minutes=self.config.trailing_wait_minutes
            )
            return RiskDecision(
                status=RiskStatus.PAUSED,
                action=RiskAction.PAUSE,
                reason="trailing_pause_extended",
                metadata={"equity": str(equity_total)},
            )

        return RiskDecision(status=RiskStatus.OK, action=RiskAction.NONE)

    async def _check_stops(
        self,
        state: RiskState,
        equity_total: Decimal,
        now: datetime,
    ) -> RiskDecision:
        if self._is_below_threshold(
            state, equity_total, self.config.monthly_stop_percent
        ):
            return await self._start_pending_liquidation(
                state,
                now,
                "monthly_stop",
                equity_total,
            )

        if self._is_below_threshold(
            state, equity_total, self.config.weekly_stop_percent
        ):
            return await self._start_pending_liquidation(
                state,
                now,
                "weekly_stop",
                equity_total,
            )

        if self._is_below_threshold(
            state, equity_total, self.config.daily_stop_percent
        ):
            state.status = RiskStatus.PAUSED.value
            state.paused_until = now + timedelta(hours=self.config.daily_pause_hours)
            return RiskDecision(
                status=RiskStatus.PAUSED,
                action=RiskAction.PAUSE,
                reason="daily_stop",
                metadata={"equity": str(equity_total)},
            )

        return RiskDecision(status=RiskStatus.OK, action=RiskAction.NONE)

    async def _check_trailing(
        self,
        state: RiskState,
        equity_total: Decimal,
        now: datetime,
    ) -> RiskDecision:
        if state.equity_peak <= 0:
            return RiskDecision(status=RiskStatus.OK, action=RiskAction.NONE)

        trailing_threshold = state.equity_peak * (
            Decimal("1") - (self.config.trailing_percent / Decimal("100"))
        )
        if equity_total < trailing_threshold:
            state.status = RiskStatus.PAUSED.value
            state.trailing_pause_until = now + timedelta(
                minutes=self.config.trailing_wait_minutes
            )
            return RiskDecision(
                status=RiskStatus.PAUSED,
                action=RiskAction.PAUSE,
                reason="trailing_pause",
                metadata={"equity": str(equity_total)},
            )

        return RiskDecision(status=RiskStatus.OK, action=RiskAction.NONE)

    async def _check_reinforcements(
        self,
        state: RiskState,
        current_price: Decimal,
        balance: dict[str, Any],
    ) -> None:
        if state.paused_until or state.pending_liquidation_until:
            return

        if state.reference_price is None:
            state.reference_price = current_price
            return

        if state.reinforcements_used >= len(self.config.reinforcement_levels_percent):
            return

        level_index = state.reinforcements_used
        level_percent = self.config.reinforcement_levels_percent[level_index]
        trigger_price = state.reference_price * (
            Decimal("1") - (level_percent / Decimal("100"))
        )

        if current_price > trigger_price:
            return

        additional_investment = self._calculate_reinforcement_amount()
        free_quote = self._get_balance(balance, self.quote_symbol, "free")
        if free_quote < additional_investment:
            await self._record_event(
                state,
                event_type="reinforcement_skipped",
                status=state.status,
                message="Insufficient free balance for reinforcement",
                metadata={
                    "needed": str(additional_investment),
                    "free_quote": str(free_quote),
                },
            )
            return

        new_investment = self.strategy.investment + additional_investment
        self._apply_investment_override(new_investment)
        state.investment_override = new_investment
        state.reinforcements_used += 1

        await self._record_event(
            state,
            event_type="reinforcement_applied",
            status=state.status,
            message="Reinforcement applied",
            metadata={
                "level_percent": str(level_percent),
                "additional_investment": str(additional_investment),
                "new_investment": str(new_investment),
            },
        )
        self.db.add(state)
        await self.db.commit()

    async def _start_pending_liquidation(
        self,
        state: RiskState,
        now: datetime,
        reason: str,
        equity_total: Decimal,
    ) -> RiskDecision:
        state.status = RiskStatus.PENDING_LIQUIDATION.value
        state.pending_liquidation_until = now + timedelta(
            minutes=self.config.two_step_wait_minutes
        )
        state.pending_reason = reason
        return RiskDecision(
            status=RiskStatus.PENDING_LIQUIDATION,
            action=RiskAction.PENDING_LIQUIDATION,
            reason=reason,
            metadata={"equity": str(equity_total)},
        )

    def _update_windows(
        self,
        state: RiskState,
        equity_total: Decimal,
        now: datetime,
    ) -> None:
        state.last_equity = equity_total
        state.equity_peak = max(state.equity_peak or equity_total, equity_total)

        if (
            state.daily_window_start is None
            or now - state.daily_window_start >= timedelta(days=1)
        ):
            state.daily_window_start = now
            state.daily_peak = equity_total
        else:
            state.daily_peak = max(state.daily_peak or equity_total, equity_total)

        if (
            state.weekly_window_start is None
            or now - state.weekly_window_start >= timedelta(days=7)
        ):
            state.weekly_window_start = now
            state.weekly_peak = equity_total
        else:
            state.weekly_peak = max(state.weekly_peak or equity_total, equity_total)

        if (
            state.monthly_window_start is None
            or now - state.monthly_window_start >= timedelta(days=30)
        ):
            state.monthly_window_start = now
            state.monthly_peak = equity_total
        else:
            state.monthly_peak = max(state.monthly_peak or equity_total, equity_total)

    def _is_below_threshold(
        self,
        state: RiskState,
        equity_total: Decimal,
        threshold_percent: Decimal,
    ) -> bool:
        peak = state.daily_peak
        if threshold_percent == self.config.weekly_stop_percent:
            peak = state.weekly_peak
        if threshold_percent == self.config.monthly_stop_percent:
            peak = state.monthly_peak

        if peak <= 0:
            return False
        drawdown = (equity_total - peak) / peak * Decimal("100")
        return drawdown <= -threshold_percent

    def _pending_threshold(self, state: RiskState) -> Decimal | None:
        if state.pending_reason == "monthly_stop":
            return self.config.monthly_stop_percent
        if state.pending_reason == "weekly_stop":
            return self.config.weekly_stop_percent
        return None

    async def _commit_state(self, state: RiskState, decision: RiskDecision) -> None:
        state.status = decision.status.value
        state.last_event_at = datetime.now(timezone.utc)
        if decision.action != RiskAction.NONE:
            self.db.add(state)
            await self.db.commit()
            await self._record_event(
                state,
                event_type=decision.reason or decision.action.value,
                status=decision.status.value,
                message=decision.reason,
                metadata=decision.metadata or {},
            )

    async def _record_event(
        self,
        state: RiskState,
        event_type: str,
        status: str,
        message: str | None,
        metadata: dict[str, Any],
    ) -> None:
        event = RiskEvent(
            bot_id=self.bot_id,
            user_id=self.user_id,
            event_type=event_type,
            status=status,
            message=message,
            metadata_json=metadata,
        )
        self.db.add(event)
        await self.db.commit()

    def _calculate_equity(
        self,
        balance: dict[str, Any],
        current_price: Decimal,
    ) -> Decimal:
        quote_total = self._get_balance(balance, self.quote_symbol, "total")
        base_total = self._get_balance(balance, self.base_symbol, "total")
        return quote_total + (base_total * current_price)

    def _get_balance(
        self,
        balance: dict[str, Any],
        asset: str,
        bucket: str,
    ) -> Decimal:
        asset = asset.upper()
        if bucket in balance and isinstance(balance[bucket], dict):
            value = balance[bucket].get(asset)
            if value is not None:
                return Decimal(str(value))

        total = balance.get("total") if isinstance(balance.get("total"), dict) else None
        if total and asset in total:
            return Decimal(str(total[asset]))

        free = balance.get("free") if isinstance(balance.get("free"), dict) else None
        if free and asset in free:
            return Decimal(str(free[asset]))

        return Decimal("0")

    def _calculate_reinforcement_amount(self) -> Decimal:
        reserve_ratio = self.config.reserve_capital_percent / Decimal("100")
        levels = max(len(self.config.reinforcement_levels_percent), 1)
        return (self.strategy.investment * reserve_ratio) / Decimal(levels)

    def _apply_investment_override(self, investment: Decimal) -> None:
        try:
            self.strategy.update_investment(investment)
        except Exception as exc:
            logger.warning("Failed to apply investment override: %s", exc)

    @staticmethod
    def _split_symbol(symbol: str) -> tuple[str, str]:
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return base, quote
        return symbol, "USDT"
