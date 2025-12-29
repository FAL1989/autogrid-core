"""
Unit Tests for Circuit Breaker.

Tests for circuit breaker safety limits and state management.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import redis.asyncio as redis_async

from bot.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitStatus,
    TripReason,
)


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig defaults."""

    def test_default_max_orders_per_minute(self) -> None:
        """Default should be 50 orders per minute."""
        config = CircuitBreakerConfig()
        assert config.max_orders_per_minute == 50

    def test_default_max_loss_percent(self) -> None:
        """Default should be 5% loss limit."""
        config = CircuitBreakerConfig()
        assert config.max_loss_percent_per_hour == Decimal("5.0")

    def test_default_max_price_deviation(self) -> None:
        """Default should be 10% price deviation limit."""
        config = CircuitBreakerConfig()
        assert config.max_price_deviation_percent == Decimal("10.0")

    def test_default_cooldown(self) -> None:
        """Default cooldown should be 300 seconds (5 minutes)."""
        config = CircuitBreakerConfig()
        assert config.cooldown_seconds == 300

    def test_custom_config(self) -> None:
        """Custom config values should be respected."""
        config = CircuitBreakerConfig(
            max_orders_per_minute=100,
            max_loss_percent_per_hour=Decimal("10.0"),
            max_price_deviation_percent=Decimal("5.0"),
            cooldown_seconds=600,
        )
        assert config.max_orders_per_minute == 100
        assert config.max_loss_percent_per_hour == Decimal("10.0")
        assert config.max_price_deviation_percent == Decimal("5.0")
        assert config.cooldown_seconds == 600


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_closed_state(self) -> None:
        """CLOSED state should allow operations."""
        assert CircuitState.CLOSED.value == "closed"

    def test_open_state(self) -> None:
        """OPEN state should block operations."""
        assert CircuitState.OPEN.value == "open"

    def test_half_open_state(self) -> None:
        """HALF_OPEN state should allow limited operations."""
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestTripReason:
    """Tests for TripReason enum."""

    def test_all_reasons_defined(self) -> None:
        """All expected trip reasons should be defined."""
        expected = [
            "ORDER_RATE_EXCEEDED",
            "LOSS_LIMIT_EXCEEDED",
            "PRICE_DEVIATION",
            "MANUAL",
            "ERROR",
        ]
        actual = [r.name for r in TripReason]
        assert sorted(actual) == sorted(expected)


@pytest.mark.asyncio
class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        """Create a mock Redis client."""
        mock = MagicMock(spec=redis_async.Redis)

        # Default mock returns
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        mock.delete = AsyncMock()
        mock.incr = AsyncMock()
        mock.incrbyfloat = AsyncMock()
        mock.expire = AsyncMock()
        mock.ttl = AsyncMock(return_value=-2)

        # Pipeline mock
        pipe_mock = MagicMock()
        pipe_mock.incr = MagicMock(return_value=pipe_mock)
        pipe_mock.incrbyfloat = MagicMock(return_value=pipe_mock)
        pipe_mock.expire = MagicMock(return_value=pipe_mock)
        pipe_mock.set = MagicMock(return_value=pipe_mock)
        pipe_mock.delete = MagicMock(return_value=pipe_mock)
        pipe_mock.get = MagicMock(return_value=pipe_mock)
        pipe_mock.ttl = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[])
        mock.pipeline = MagicMock(return_value=pipe_mock)

        return mock

    @pytest.fixture
    def circuit_breaker(self, mock_redis: MagicMock) -> CircuitBreaker:
        """Create a CircuitBreaker instance."""
        return CircuitBreaker(mock_redis)

    @pytest.fixture
    def bot_id(self) -> uuid4:
        """Create a test bot ID."""
        return uuid4()

    # ==================================================================
    # Order Rate Limit Tests (50 orders/min)
    # ==================================================================

    async def test_order_allowed_under_rate_limit(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders under rate limit should be allowed."""
        # Mock 10 orders in last minute (under 50)
        circuit_breaker.redis.get = AsyncMock(return_value=None)

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is True
        assert reason is None

    async def test_order_blocked_at_rate_limit(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders at rate limit should be blocked."""
        # Mock 50 orders in last minute (at limit)
        async def mock_get(key: str):
            if "orders" in key:
                return "50"
            return None  # state defaults to CLOSED

        circuit_breaker.redis.get = AsyncMock(side_effect=mock_get)

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert "order_rate_exceeded" in reason
        assert "50/50" in reason

    async def test_order_blocked_over_rate_limit(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders over rate limit should be blocked and trip circuit."""
        # Mock 60 orders in last minute (over limit)
        async def mock_get(key: str):
            if "orders" in key:
                return "60"
            return None  # state defaults to CLOSED

        circuit_breaker.redis.get = AsyncMock(side_effect=mock_get)

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert "order_rate_exceeded" in reason

    async def test_record_order_increments_counter(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Recording order should increment Redis counter."""
        await circuit_breaker.record_order_placed(bot_id)

        # Verify pipeline was used
        pipe = circuit_breaker.redis.pipeline.return_value
        pipe.incr.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_called_once()

    # ==================================================================
    # Loss Limit Tests (5% per hour)
    # ==================================================================

    async def test_order_allowed_under_loss_limit(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders under loss limit should be allowed."""
        # Mock 2% loss (under 5%)
        async def mock_get(key: str):
            if "loss" in key:
                return "200"  # 200 loss on 10000 = 2%
            return None

        circuit_breaker.redis.get = AsyncMock(side_effect=mock_get)

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is True
        assert reason is None

    async def test_order_blocked_at_loss_limit(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders at loss limit should be blocked."""
        # Mock 5% loss (at limit)
        async def mock_get(key: str):
            if "loss" in key:
                return "500"  # 500 loss on 10000 = 5%
            return None

        circuit_breaker.redis.get = AsyncMock(side_effect=mock_get)

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert "loss_limit_exceeded" in reason
        assert "5.00%" in reason

    async def test_order_blocked_over_loss_limit(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders over loss limit should be blocked."""
        # Mock 8% loss (over limit)
        async def mock_get(key: str):
            if "loss" in key:
                return "800"  # 800 loss on 10000 = 8%
            return None

        circuit_breaker.redis.get = AsyncMock(side_effect=mock_get)

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert "loss_limit_exceeded" in reason

    async def test_record_pnl_loss(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Recording loss should update Redis."""
        await circuit_breaker.record_pnl(bot_id, Decimal("-100"))

        pipe = circuit_breaker.redis.pipeline.return_value
        pipe.incrbyfloat.assert_called_once()
        pipe.execute.assert_called_once()

    async def test_record_pnl_profit_ignored(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Recording profit should not update loss counter."""
        await circuit_breaker.record_pnl(bot_id, Decimal("100"))

        # Pipeline should not have been used for profits
        circuit_breaker.redis.pipeline.assert_not_called()

    # ==================================================================
    # Price Deviation Tests (10% max)
    # ==================================================================

    async def test_order_allowed_within_price_deviation(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders within price deviation should be allowed."""
        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("51000"),  # 2% above market
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is True
        assert reason is None

    async def test_order_blocked_price_too_high(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders with price too far above market should be blocked."""
        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("56000"),  # 12% above market
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert "price_deviation_exceeded" in reason
        assert "12.00%" in reason

    async def test_order_blocked_price_too_low(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders with price too far below market should be blocked."""
        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("44000"),  # 12% below market
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert "price_deviation_exceeded" in reason
        assert "12.00%" in reason

    async def test_market_order_no_price_deviation_check(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Market orders (no price) should skip price deviation check."""
        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=None,  # Market order
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is True
        assert reason is None

    async def test_price_deviation_edge_case(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """10% deviation should be at the limit."""
        # Exactly 10% deviation
        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("55000"),  # Exactly 10% above
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is True  # 10% is at limit, not over

    async def test_price_deviation_zero_market_price(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Zero market price should return 100% deviation."""
        deviation = circuit_breaker._calculate_price_deviation(
            Decimal("50000"), Decimal("0")
        )
        assert deviation == Decimal("100")

    # ==================================================================
    # Circuit State Tests
    # ==================================================================

    async def test_get_state_default_closed(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Default state should be CLOSED."""
        state = await circuit_breaker.get_state(bot_id)
        assert state == CircuitState.CLOSED

    async def test_get_state_open(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Should return OPEN state when set."""
        circuit_breaker.redis.get = AsyncMock(
            side_effect=lambda key: "open" if "state" in key else "cooldown"
        )

        state = await circuit_breaker.get_state(bot_id)
        assert state == CircuitState.OPEN

    async def test_get_state_auto_half_open_after_cooldown(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Should transition to HALF_OPEN when cooldown expires."""
        # State is OPEN but cooldown key doesn't exist (expired)
        async def mock_get(key: str):
            if "state" in key:
                return "open"
            return None  # Cooldown expired

        circuit_breaker.redis.get = AsyncMock(side_effect=mock_get)

        state = await circuit_breaker.get_state(bot_id)
        assert state == CircuitState.HALF_OPEN

    async def test_order_blocked_when_circuit_open(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Orders should be blocked when circuit is OPEN."""
        circuit_breaker.redis.get = AsyncMock(
            side_effect=lambda key: "open" if "state" in key else "cooldown"
        )

        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )

        assert allowed is False
        assert reason == "circuit_breaker_open"

    async def test_is_tripped_when_open(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """is_tripped should return True when OPEN."""
        circuit_breaker.redis.get = AsyncMock(
            side_effect=lambda key: "open" if "state" in key else "cooldown"
        )

        assert await circuit_breaker.is_tripped(bot_id) is True

    async def test_is_tripped_when_closed(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """is_tripped should return False when CLOSED."""
        circuit_breaker.redis.get = AsyncMock(return_value=None)

        assert await circuit_breaker.is_tripped(bot_id) is False

    # ==================================================================
    # Trip and Reset Tests
    # ==================================================================

    async def test_trip_sets_open_state(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Trip should set circuit to OPEN."""
        await circuit_breaker.trip(bot_id, TripReason.ORDER_RATE_EXCEEDED)

        pipe = circuit_breaker.redis.pipeline.return_value
        pipe.set.assert_called()
        pipe.execute.assert_called_once()

    async def test_reset_clears_state(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Reset should clear circuit state."""
        await circuit_breaker.reset(bot_id)

        pipe = circuit_breaker.redis.pipeline.return_value
        pipe.set.assert_called()
        pipe.delete.assert_called()
        pipe.execute.assert_called_once()

    async def test_half_open_sets_state(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """half_open should set HALF_OPEN state."""
        await circuit_breaker.half_open(bot_id)

        circuit_breaker.redis.set.assert_called_once()

    # ==================================================================
    # Status and Metrics Tests
    # ==================================================================

    async def test_get_status(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Should return complete status."""
        pipe = circuit_breaker.redis.pipeline.return_value
        pipe.execute = AsyncMock(
            return_value=[
                "closed",  # state
                "25",  # order count
                "150.5",  # loss
                None,  # trip reason
                -2,  # cooldown TTL (expired)
            ]
        )

        status = await circuit_breaker.get_status(bot_id, Decimal("10000"))

        assert status.state == CircuitState.CLOSED
        assert status.orders_last_minute == 25
        assert status.loss_last_hour == Decimal("150.5")
        assert status.trip_reason is None
        assert status.cooldown_remaining == 0

    async def test_get_status_with_trip_reason(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Should include trip reason in status."""
        pipe = circuit_breaker.redis.pipeline.return_value
        pipe.execute = AsyncMock(
            return_value=[
                "open",
                "55",
                "0",
                "order_rate_exceeded",
                180,
            ]
        )

        status = await circuit_breaker.get_status(bot_id, Decimal("10000"))

        assert status.state == CircuitState.OPEN
        assert status.trip_reason == TripReason.ORDER_RATE_EXCEEDED
        assert status.cooldown_remaining == 180

    async def test_clear_metrics(
        self,
        circuit_breaker: CircuitBreaker,
        bot_id: uuid4,
    ) -> None:
        """Should clear all metrics."""
        await circuit_breaker.clear_metrics(bot_id)

        pipe = circuit_breaker.redis.pipeline.return_value
        assert pipe.delete.call_count == 2
        pipe.execute.assert_called_once()


@pytest.mark.asyncio
class TestCircuitBreakerIntegration:
    """Integration tests using real Redis mock behavior."""

    async def test_full_order_flow(self) -> None:
        """Test complete order flow with rate limiting."""
        # Use a more realistic mock that simulates Redis state
        redis_state: dict[str, str] = {}

        mock_redis = MagicMock(spec=redis_async.Redis)

        async def mock_get(key: str):
            return redis_state.get(key)

        mock_redis.get = AsyncMock(side_effect=mock_get)

        pipe_mock = MagicMock()

        def mock_incr(key: str):
            current = int(redis_state.get(key, "0"))
            redis_state[key] = str(current + 1)
            return pipe_mock

        pipe_mock.incr = mock_incr
        pipe_mock.expire = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[])
        mock_redis.pipeline = MagicMock(return_value=pipe_mock)

        cb = CircuitBreaker(mock_redis)
        bot_id = uuid4()

        # Place 49 orders (should all be allowed)
        for i in range(49):
            await cb.record_order_placed(bot_id)

        # 50th order should still be allowed (at limit, not over)
        allowed, _ = await cb.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=Decimal("10000"),
        )
        assert allowed is True

    async def test_loss_accumulation(self) -> None:
        """Test loss accumulation triggers circuit breaker."""
        redis_state: dict[str, str] = {}

        mock_redis = MagicMock(spec=redis_async.Redis)

        async def mock_get(key: str):
            return redis_state.get(key)

        mock_redis.get = AsyncMock(side_effect=mock_get)

        pipe_mock = MagicMock()

        def mock_incrbyfloat(key: str, value: float):
            current = float(redis_state.get(key, "0"))
            redis_state[key] = str(current + value)
            return pipe_mock

        pipe_mock.incrbyfloat = mock_incrbyfloat
        pipe_mock.expire = MagicMock(return_value=pipe_mock)
        pipe_mock.set = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[])
        mock_redis.pipeline = MagicMock(return_value=pipe_mock)

        cb = CircuitBreaker(mock_redis)
        bot_id = uuid4()
        investment = Decimal("10000")

        # Record 4.5% loss
        await cb.record_pnl(bot_id, Decimal("-450"))

        # Should still be allowed (4.5% < 5%)
        allowed, _ = await cb.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=investment,
        )
        assert allowed is True

        # Record another 1% loss (total 5.5%)
        await cb.record_pnl(bot_id, Decimal("-100"))

        # Should now be blocked (5.5% > 5%)
        allowed, reason = await cb.check_order_allowed(
            bot_id=bot_id,
            order_price=Decimal("50000"),
            current_price=Decimal("50000"),
            investment=investment,
        )
        assert allowed is False
        assert "loss_limit_exceeded" in reason
