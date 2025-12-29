"""
Circuit Breaker

Safety mechanism to protect against excessive trading, losses, and price manipulation.
Uses Redis for distributed state across multiple workers.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

import redis.asyncio as redis_async

logger = logging.getLogger(__name__)


# Redis key prefixes
REDIS_PREFIX = "autogrid:circuit_breaker"
ORDER_COUNT_KEY = f"{REDIS_PREFIX}:orders"  # :{{bot_id}}:count
LOSS_KEY = f"{REDIS_PREFIX}:loss"  # :{{bot_id}}:amount
STATE_KEY = f"{REDIS_PREFIX}:state"  # :{{bot_id}}
TRIP_REASON_KEY = f"{REDIS_PREFIX}:reason"  # :{{bot_id}}
COOLDOWN_KEY = f"{REDIS_PREFIX}:cooldown"  # :{{bot_id}}


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, orders allowed
    OPEN = "open"  # Tripped, orders blocked
    HALF_OPEN = "half_open"  # Testing recovery


class TripReason(Enum):
    """Reasons why circuit breaker tripped."""

    ORDER_RATE_EXCEEDED = "order_rate_exceeded"
    LOSS_LIMIT_EXCEEDED = "loss_limit_exceeded"
    PRICE_DEVIATION = "price_deviation"
    MANUAL = "manual"
    ERROR = "error"


@dataclass
class CircuitBreakerConfig:
    """
    Circuit breaker configuration.

    Attributes:
        max_orders_per_minute: Maximum orders per minute (default: 50)
        max_loss_percent_per_hour: Maximum loss as % of investment per hour (default: 5.0)
        max_price_deviation_percent: Maximum order price deviation from market (default: 10.0)
        cooldown_seconds: Time to wait before allowing orders after trip (default: 300)
        half_open_orders: Number of test orders allowed in half-open state (default: 3)
    """

    max_orders_per_minute: int = 50
    max_loss_percent_per_hour: Decimal = Decimal("5.0")
    max_price_deviation_percent: Decimal = Decimal("10.0")
    cooldown_seconds: int = 300
    half_open_orders: int = 3


@dataclass
class CircuitStatus:
    """Current circuit breaker status."""

    state: CircuitState
    orders_last_minute: int
    loss_last_hour: Decimal
    trip_reason: TripReason | None
    tripped_at: datetime | None
    cooldown_remaining: int


class CircuitBreaker:
    """
    Circuit breaker for trading safety.

    Monitors order rate, P&L, and price deviation to prevent:
    - Excessive order placement (50/min limit)
    - Rapid losses (5% of investment per hour)
    - Orders at manipulated prices (10% from market)

    Uses Redis for distributed state management across Celery workers.
    """

    def __init__(
        self,
        redis_client: redis_async.Redis,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            redis_client: Redis client for state storage
            config: Circuit breaker configuration
        """
        self.redis = redis_client
        self.config = config or CircuitBreakerConfig()

    async def check_order_allowed(
        self,
        bot_id: UUID,
        order_price: Decimal | None,
        current_price: Decimal,
        investment: Decimal,
    ) -> tuple[bool, str | None]:
        """
        Check if an order is allowed to be placed.

        Performs all safety checks:
        1. Circuit state (must be CLOSED or HALF_OPEN)
        2. Order rate (max 50/min)
        3. Loss limit (max 5%/hour of investment)
        4. Price deviation (max 10% from market)

        Args:
            bot_id: Bot ID placing the order
            order_price: Order price (None for market orders)
            current_price: Current market price
            investment: Total bot investment

        Returns:
            Tuple of (allowed, reason). If not allowed, reason explains why.
        """
        bot_key = str(bot_id)

        # Check circuit state
        state = await self.get_state(bot_id)
        if state == CircuitState.OPEN:
            return False, "circuit_breaker_open"

        # Check order rate
        order_count = await self._get_order_count(bot_key)
        if order_count >= self.config.max_orders_per_minute:
            await self.trip(bot_id, TripReason.ORDER_RATE_EXCEEDED)
            return False, f"order_rate_exceeded ({order_count}/{self.config.max_orders_per_minute}/min)"

        # Check loss limit
        loss_amount = await self._get_hourly_loss(bot_key)
        loss_percent = (loss_amount / investment * 100) if investment > 0 else Decimal("0")
        if loss_percent >= self.config.max_loss_percent_per_hour:
            await self.trip(bot_id, TripReason.LOSS_LIMIT_EXCEEDED)
            return False, f"loss_limit_exceeded ({loss_percent:.2f}%/{self.config.max_loss_percent_per_hour}%)"

        # Check price deviation (only for limit orders)
        if order_price is not None:
            deviation = self._calculate_price_deviation(order_price, current_price)
            if deviation > self.config.max_price_deviation_percent:
                return False, f"price_deviation_exceeded ({deviation:.2f}%/{self.config.max_price_deviation_percent}%)"

        # All checks passed
        return True, None

    async def record_order_placed(self, bot_id: UUID) -> None:
        """
        Record that an order was placed.

        Increments order counter with 1-minute TTL for rate limiting.

        Args:
            bot_id: Bot that placed the order
        """
        key = f"{ORDER_COUNT_KEY}:{bot_id}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 60)  # 1 minute TTL
        await pipe.execute()

    async def record_pnl(self, bot_id: UUID, pnl: Decimal) -> None:
        """
        Record realized P&L.

        Tracks hourly losses for loss limit checking.
        Only records negative P&L (losses) for limit checking.

        Args:
            bot_id: Bot with P&L
            pnl: Realized P&L (positive = profit, negative = loss)
        """
        if pnl >= 0:
            return  # Only track losses

        key = f"{LOSS_KEY}:{bot_id}"
        loss = abs(pnl)

        pipe = self.redis.pipeline()
        pipe.incrbyfloat(key, float(loss))
        pipe.expire(key, 3600)  # 1 hour TTL
        await pipe.execute()

    async def trip(self, bot_id: UUID, reason: TripReason) -> None:
        """
        Trip the circuit breaker.

        Opens the circuit, blocking all orders for the cooldown period.

        Args:
            bot_id: Bot to trip
            reason: Reason for tripping
        """
        bot_key = str(bot_id)
        now = datetime.now(timezone.utc).isoformat()

        pipe = self.redis.pipeline()
        pipe.set(f"{STATE_KEY}:{bot_key}", CircuitState.OPEN.value)
        pipe.set(f"{TRIP_REASON_KEY}:{bot_key}", reason.value)
        pipe.set(
            f"{COOLDOWN_KEY}:{bot_key}",
            now,
            ex=self.config.cooldown_seconds,
        )
        await pipe.execute()

        logger.warning(
            f"Circuit breaker TRIPPED for bot {bot_id}: {reason.value}"
        )

    async def reset(self, bot_id: UUID) -> None:
        """
        Reset circuit breaker to closed state.

        Clears all trip data and allows orders again.

        Args:
            bot_id: Bot to reset
        """
        bot_key = str(bot_id)

        pipe = self.redis.pipeline()
        pipe.set(f"{STATE_KEY}:{bot_key}", CircuitState.CLOSED.value)
        pipe.delete(f"{TRIP_REASON_KEY}:{bot_key}")
        pipe.delete(f"{COOLDOWN_KEY}:{bot_key}")
        await pipe.execute()

        logger.info(f"Circuit breaker RESET for bot {bot_id}")

    async def half_open(self, bot_id: UUID) -> None:
        """
        Transition to half-open state.

        Allows limited orders to test if the issue is resolved.

        Args:
            bot_id: Bot to transition
        """
        bot_key = str(bot_id)
        await self.redis.set(f"{STATE_KEY}:{bot_key}", CircuitState.HALF_OPEN.value)

        logger.info(f"Circuit breaker HALF-OPEN for bot {bot_id}")

    async def get_state(self, bot_id: UUID) -> CircuitState:
        """
        Get current circuit breaker state.

        Also checks cooldown and auto-transitions to HALF_OPEN when expired.

        Args:
            bot_id: Bot to check

        Returns:
            Current circuit state
        """
        bot_key = str(bot_id)

        state_str = await self.redis.get(f"{STATE_KEY}:{bot_key}")
        if not state_str:
            return CircuitState.CLOSED

        state = CircuitState(state_str)

        # If OPEN, check if cooldown has expired
        if state == CircuitState.OPEN:
            cooldown_key = f"{COOLDOWN_KEY}:{bot_key}"
            cooldown = await self.redis.get(cooldown_key)
            if cooldown is None:
                # Cooldown expired, transition to HALF_OPEN
                await self.half_open(bot_id)
                return CircuitState.HALF_OPEN

        return state

    async def is_tripped(self, bot_id: UUID) -> bool:
        """
        Check if circuit breaker is tripped (OPEN state).

        Args:
            bot_id: Bot to check

        Returns:
            True if circuit is OPEN
        """
        state = await self.get_state(bot_id)
        return state == CircuitState.OPEN

    async def get_status(self, bot_id: UUID, investment: Decimal) -> CircuitStatus:
        """
        Get detailed circuit breaker status.

        Args:
            bot_id: Bot to check
            investment: Bot investment for loss calculation

        Returns:
            CircuitStatus with all metrics
        """
        bot_key = str(bot_id)

        # Get all data from Redis
        pipe = self.redis.pipeline()
        pipe.get(f"{STATE_KEY}:{bot_key}")
        pipe.get(f"{ORDER_COUNT_KEY}:{bot_key}")
        pipe.get(f"{LOSS_KEY}:{bot_key}")
        pipe.get(f"{TRIP_REASON_KEY}:{bot_key}")
        pipe.ttl(f"{COOLDOWN_KEY}:{bot_key}")
        results = await pipe.execute()

        state_str, order_count_str, loss_str, reason_str, cooldown_ttl = results

        # Parse values
        state = CircuitState(state_str) if state_str else CircuitState.CLOSED
        orders = int(order_count_str) if order_count_str else 0
        loss = Decimal(str(loss_str)) if loss_str else Decimal("0")
        reason = TripReason(reason_str) if reason_str else None
        cooldown = max(0, cooldown_ttl) if cooldown_ttl and cooldown_ttl > 0 else 0

        return CircuitStatus(
            state=state,
            orders_last_minute=orders,
            loss_last_hour=loss,
            trip_reason=reason,
            tripped_at=None,  # Not tracked currently
            cooldown_remaining=cooldown,
        )

    async def clear_metrics(self, bot_id: UUID) -> None:
        """
        Clear all metrics for a bot.

        Useful when resetting or restarting a bot.

        Args:
            bot_id: Bot to clear
        """
        bot_key = str(bot_id)

        pipe = self.redis.pipeline()
        pipe.delete(f"{ORDER_COUNT_KEY}:{bot_key}")
        pipe.delete(f"{LOSS_KEY}:{bot_key}")
        await pipe.execute()

    def _calculate_price_deviation(
        self,
        order_price: Decimal,
        market_price: Decimal,
    ) -> Decimal:
        """
        Calculate percentage deviation from market price.

        Args:
            order_price: Proposed order price
            market_price: Current market price

        Returns:
            Absolute deviation percentage
        """
        if market_price == 0:
            return Decimal("100")  # Treat zero as 100% deviation

        deviation = abs(order_price - market_price) / market_price * 100
        return deviation

    async def _get_order_count(self, bot_key: str) -> int:
        """Get order count for rate limiting."""
        count = await self.redis.get(f"{ORDER_COUNT_KEY}:{bot_key}")
        return int(count) if count else 0

    async def _get_hourly_loss(self, bot_key: str) -> Decimal:
        """Get total loss for the last hour."""
        loss = await self.redis.get(f"{LOSS_KEY}:{bot_key}")
        return Decimal(str(loss)) if loss else Decimal("0")


async def create_circuit_breaker(
    redis_url: str = "redis://localhost:6379",
    config: CircuitBreakerConfig | None = None,
) -> CircuitBreaker:
    """
    Factory function to create a CircuitBreaker instance.

    Args:
        redis_url: Redis connection URL
        config: Optional circuit breaker configuration

    Returns:
        Configured CircuitBreaker instance
    """
    redis_client = redis_async.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    return CircuitBreaker(redis_client, config)
