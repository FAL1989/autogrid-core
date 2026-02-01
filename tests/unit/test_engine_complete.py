"""
Comprehensive Unit Tests for Bot Engine.

Tests for the main trading bot orchestrator covering:
- Engine initialization and configuration
- Start/stop lifecycle
- Tick execution with strategies
- Circuit breaker integration
- Risk manager integration
- Order filtering by balance/min notional
- Grid level deduplication
- Notification on fills
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from bot.engine import BotConfig, BotEngine, BotState
from bot.order_manager import ManagedOrder, OrderState
from bot.risk_manager import RiskAction, RiskDecision, RiskStatus
from bot.strategies.base import Order


class TestBotEngineInitialization:
    """Tests for BotEngine initialization."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        mock.investment = Decimal("1000")
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        mock.connect = AsyncMock()
        mock.disconnect = AsyncMock()
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 10000.0, "BTC": 0.5},
                "total": {"USDT": 10000.0, "BTC": 0.5},
            }
        )
        mock.create_order = AsyncMock(
            return_value={"id": "12345", "status": "open"}
        )
        mock.cancel_order = AsyncMock(return_value=True)
        mock.get_min_notional = AsyncMock(return_value=Decimal("10"))
        mock.get_min_qty = AsyncMock(return_value=Decimal("0.0001"))
        mock.get_step_size = AsyncMock(return_value=Decimal("0.0001"))
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    def test_engine_initialization(self, bot_config: BotConfig) -> None:
        """Engine should initialize with correct defaults."""
        engine = BotEngine(config=bot_config)

        assert engine.config == bot_config
        assert engine.strategy == bot_config.strategy
        assert engine.exchange == bot_config.exchange
        assert engine.order_manager is None
        assert engine.circuit_breaker is None
        assert engine.risk_manager is None
        assert engine.is_running is False
        assert engine.tick_interval == 1.0

    def test_engine_initialization_with_custom_tick_interval(
        self, bot_config: BotConfig
    ) -> None:
        """Engine should respect custom tick interval."""
        engine = BotEngine(config=bot_config, tick_interval=5.0)
        assert engine.tick_interval == 5.0

    def test_engine_initialization_with_order_manager(
        self, bot_config: BotConfig
    ) -> None:
        """Engine should accept OrderManager."""
        mock_order_manager = MagicMock()
        engine = BotEngine(config=bot_config, order_manager=mock_order_manager)
        assert engine.order_manager == mock_order_manager

    def test_engine_initialization_with_circuit_breaker(
        self, bot_config: BotConfig
    ) -> None:
        """Engine should accept CircuitBreaker."""
        mock_cb = MagicMock()
        engine = BotEngine(config=bot_config, circuit_breaker=mock_cb)
        assert engine.circuit_breaker == mock_cb

    def test_engine_initialization_with_risk_manager(
        self, bot_config: BotConfig
    ) -> None:
        """Engine should accept RiskManager."""
        mock_rm = MagicMock()
        engine = BotEngine(config=bot_config, risk_manager=mock_rm)
        assert engine.risk_manager == mock_rm

    def test_engine_initialization_with_notifier(
        self, bot_config: BotConfig
    ) -> None:
        """Engine should accept Notifier."""
        mock_notifier = MagicMock()
        engine = BotEngine(config=bot_config, notifier=mock_notifier)
        assert engine.notifier == mock_notifier

    def test_engine_initial_state(self, bot_config: BotConfig) -> None:
        """Engine state should be initialized correctly."""
        engine = BotEngine(config=bot_config)
        state = engine.state

        assert isinstance(state, BotState)
        assert state.is_running is False
        assert state.current_price == Decimal("0")
        assert state.position == {}
        assert state.total_orders == 0
        assert state.filled_orders == 0
        assert state.realized_pnl == Decimal("0")


@pytest.mark.asyncio
class TestBotEngineStartStop:
    """Tests for engine start/stop lifecycle."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = False
        mock.connect = AsyncMock()
        mock.disconnect = AsyncMock()
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 10000.0, "BTC": 0.5},
                "total": {"USDT": 10000.0, "BTC": 0.5},
            }
        )
        mock.cancel_order = AsyncMock(return_value=True)
        mock.get_min_notional = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    async def test_engine_start_connects_exchange(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Start should connect to exchange if not connected."""
        engine = BotEngine(config=bot_config, tick_interval=0.01)

        # Start and immediately stop
        async def stop_after_start():
            await asyncio.sleep(0.02)
            engine._state.is_running = False

        with patch.object(engine, "_tick", new_callable=AsyncMock):
            task = asyncio.create_task(engine.start())
            await stop_after_start()
            await task

        mock_exchange.connect.assert_called_once()

    async def test_engine_start_skips_connect_if_already_connected(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Start should not connect if already connected."""
        mock_exchange.is_connected = True
        engine = BotEngine(config=bot_config, tick_interval=0.01)

        async def stop_after_start():
            await asyncio.sleep(0.02)
            engine._state.is_running = False

        with patch.object(engine, "_tick", new_callable=AsyncMock):
            task = asyncio.create_task(engine.start())
            await stop_after_start()
            await task

        mock_exchange.connect.assert_not_called()

    async def test_engine_stop_cancels_orders(
        self, bot_config: BotConfig
    ) -> None:
        """Stop should cancel all open orders."""
        mock_order_manager = MagicMock()
        mock_order_manager.cancel_all_orders = AsyncMock(return_value=5)

        engine = BotEngine(
            config=bot_config, order_manager=mock_order_manager
        )
        engine._state.is_running = True

        await engine.stop()

        assert engine._state.is_running is False
        mock_order_manager.cancel_all_orders.assert_called_once_with(
            bot_config.id
        )

    async def test_engine_stop_disconnects_exchange(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Stop should disconnect from exchange."""
        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        await engine.stop()

        mock_exchange.disconnect.assert_called_once()


@pytest.mark.asyncio
class TestBotEngineTick:
    """Tests for engine tick execution."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        mock.investment = Decimal("1000")
        mock.dynamic_range_enabled = False
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        mock.connect = AsyncMock()
        mock.disconnect = AsyncMock()
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 10000.0, "BTC": 0.5},
                "total": {"USDT": 10000.0, "BTC": 0.5},
            }
        )
        mock.create_order = AsyncMock(
            return_value={"id": "12345", "status": "open"}
        )
        mock.cancel_order = AsyncMock(return_value=True)
        mock.get_min_notional = AsyncMock(return_value=Decimal("10"))
        mock.get_min_qty = AsyncMock(return_value=Decimal("0.0001"))
        mock.get_step_size = AsyncMock(return_value=Decimal("0.0001"))
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    async def test_tick_fetches_ticker(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Tick should fetch current ticker."""
        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        await engine._tick()

        mock_exchange.fetch_ticker.assert_called_once_with("BTC/USDT")

    async def test_tick_updates_current_price(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Tick should update current price in state."""
        mock_exchange.fetch_ticker = AsyncMock(return_value={"last": 51000.0})
        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        await engine._tick()

        assert engine._state.current_price == Decimal("51000.0")

    async def test_tick_calls_strategy_calculate_orders(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Tick should call strategy to calculate orders."""
        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        await engine._tick()

        mock_strategy.calculate_orders.assert_called_once()
        call_kwargs = mock_strategy.calculate_orders.call_args[1]
        assert "current_price" in call_kwargs
        assert "open_orders" in call_kwargs

    async def test_tick_executes_orders(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Tick should execute orders returned by strategy."""
        order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.01"),
        )
        mock_strategy.calculate_orders = MagicMock(return_value=[order])

        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        await engine._tick()

        # Order should be submitted
        assert engine._state.total_orders == 1

    async def test_tick_with_no_orders(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Tick with no orders should not increase order count."""
        mock_strategy.calculate_orders = MagicMock(return_value=[])

        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        await engine._tick()

        assert engine._state.total_orders == 0

    async def test_tick_handles_ticker_timeout(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Tick should handle ticker fetch timeout gracefully."""
        mock_exchange.fetch_ticker = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        engine = BotEngine(
            config=bot_config, exchange_timeout_seconds=0.01
        )
        engine._state.is_running = True

        # Should not raise
        await engine._tick()

        # Price should not be updated
        assert engine._state.current_price == Decimal("0")

    async def test_tick_handles_ticker_error(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Tick should handle ticker fetch error gracefully."""
        mock_exchange.fetch_ticker = AsyncMock(
            side_effect=Exception("API Error")
        )

        engine = BotEngine(config=bot_config)
        engine._state.is_running = True

        # Should not raise
        await engine._tick()


@pytest.mark.asyncio
class TestBotEngineCircuitBreaker:
    """Tests for circuit breaker integration."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        mock.dynamic_range_enabled = False
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 10000.0, "BTC": 0.5},
                "total": {"USDT": 10000.0, "BTC": 0.5},
            }
        )
        mock.get_min_notional = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    async def test_tick_respects_circuit_breaker(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Tick should return early if circuit breaker is tripped."""
        mock_cb = MagicMock()
        mock_cb.is_tripped = AsyncMock(return_value=True)

        mock_order_manager = MagicMock()
        mock_order_manager.cancel_all_orders = AsyncMock(return_value=0)

        engine = BotEngine(
            config=bot_config,
            circuit_breaker=mock_cb,
            order_manager=mock_order_manager,
        )
        engine._state.is_running = True

        await engine._tick()

        # Strategy should not be called when circuit is tripped
        mock_strategy.calculate_orders.assert_not_called()
        # Should cancel all orders
        mock_order_manager.cancel_all_orders.assert_called_once()

    async def test_tick_checks_order_with_circuit_breaker(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Orders should be checked against circuit breaker."""
        order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.01"),
        )
        mock_strategy.calculate_orders = MagicMock(return_value=[order])

        mock_cb = MagicMock()
        mock_cb.is_tripped = AsyncMock(return_value=False)
        mock_cb.check_order_allowed = AsyncMock(
            return_value=(False, "order_rate_exceeded")
        )
        mock_cb.record_order_placed = AsyncMock()

        engine = BotEngine(
            config=bot_config, circuit_breaker=mock_cb
        )
        engine._state.is_running = True

        await engine._tick()

        # Order should be checked
        mock_cb.check_order_allowed.assert_called_once()
        # Order should not be placed since it was blocked
        assert engine._state.total_orders == 0


@pytest.mark.asyncio
class TestBotEngineRiskManager:
    """Tests for risk manager integration."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        mock.dynamic_range_enabled = False
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 10000.0, "BTC": 0.5},
                "total": {"USDT": 10000.0, "BTC": 0.5},
            }
        )
        mock.get_min_notional = AsyncMock(return_value=None)
        mock.cancel_order = AsyncMock()
        mock.create_order = AsyncMock(return_value={"id": "12345"})
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    async def test_tick_calls_risk_manager(
        self, bot_config: BotConfig
    ) -> None:
        """Tick should call risk manager update_state."""
        mock_rm = MagicMock()
        mock_rm.update_state = AsyncMock(
            return_value=RiskDecision(
                status=RiskStatus.OK, action=RiskAction.NONE
            )
        )
        mock_rm.is_trading_allowed = MagicMock(return_value=True)

        engine = BotEngine(config=bot_config, risk_manager=mock_rm)
        engine._state.is_running = True

        await engine._tick()

        mock_rm.update_state.assert_called_once()

    async def test_tick_respects_risk_pause_decision(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Tick should return early on PAUSE decision."""
        mock_rm = MagicMock()
        mock_rm.update_state = AsyncMock(
            return_value=RiskDecision(
                status=RiskStatus.PAUSED,
                action=RiskAction.PAUSE,
                reason="daily_stop",
            )
        )

        mock_order_manager = MagicMock()
        mock_order_manager.get_open_orders = AsyncMock(return_value=[])
        mock_order_manager.cancel_all_orders = AsyncMock(return_value=0)

        engine = BotEngine(
            config=bot_config,
            risk_manager=mock_rm,
            order_manager=mock_order_manager,
        )
        engine._state.is_running = True

        await engine._tick()

        # Strategy should not calculate orders on pause
        mock_strategy.calculate_orders.assert_not_called()

    async def test_tick_respects_risk_liquidate_decision(
        self, bot_config: BotConfig, mock_exchange: MagicMock
    ) -> None:
        """Tick should liquidate position on LIQUIDATE decision."""
        mock_rm = MagicMock()
        mock_rm.update_state = AsyncMock(
            return_value=RiskDecision(
                status=RiskStatus.LIQUIDATED,
                action=RiskAction.LIQUIDATE,
                reason="monthly_stop",
            )
        )

        mock_order_manager = MagicMock()
        mock_order_manager.get_open_orders = AsyncMock(return_value=[])
        mock_order_manager.cancel_all_orders = AsyncMock(return_value=0)
        mock_order_manager.submit_order = AsyncMock()

        engine = BotEngine(
            config=bot_config,
            risk_manager=mock_rm,
            order_manager=mock_order_manager,
        )
        engine._state.is_running = True
        engine._position = {"BTC": Decimal("0.1")}

        await engine._tick()

        # Should stop running after liquidation
        assert engine._state.is_running is False

    async def test_tick_checks_trading_allowed(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Tick should not trade if trading not allowed."""
        mock_rm = MagicMock()
        mock_rm.update_state = AsyncMock(
            return_value=RiskDecision(
                status=RiskStatus.OK, action=RiskAction.NONE
            )
        )
        mock_rm.is_trading_allowed = MagicMock(return_value=False)

        engine = BotEngine(config=bot_config, risk_manager=mock_rm)
        engine._state.is_running = True

        await engine._tick()

        # Strategy should not be called
        mock_strategy.calculate_orders.assert_not_called()


@pytest.mark.asyncio
class TestBotEngineOrderFiltering:
    """Tests for order filtering logic."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        mock.dynamic_range_enabled = False
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 100.0, "BTC": 0.001},
                "total": {"USDT": 100.0, "BTC": 0.001},
            }
        )
        mock.create_order = AsyncMock(
            return_value={"id": "12345", "status": "open"}
        )
        mock.get_min_notional = AsyncMock(return_value=Decimal("10"))
        mock.get_min_qty = AsyncMock(return_value=Decimal("0.0001"))
        mock.get_step_size = AsyncMock(return_value=Decimal("0.0001"))
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    def test_filter_orders_by_balance_buy(
        self, bot_config: BotConfig
    ) -> None:
        """Should filter buy orders by available quote balance."""
        engine = BotEngine(config=bot_config)

        orders = [
            Order(side="buy", type="limit", price=Decimal("50000"), quantity=Decimal("0.01")),
            Order(side="buy", type="limit", price=Decimal("49000"), quantity=Decimal("0.01")),
        ]

        # 100 USDT available, need 500 USDT for first order
        balance = {
            "free": {"USDT": 100.0, "BTC": 0.0},
        }

        filtered = engine._filter_orders_by_balance(
            orders,
            Decimal("50000"),
            balance,
            min_notional=Decimal("10"),
            min_qty=Decimal("0.0001"),
            step_size=Decimal("0.0001"),
        )

        # Both orders need more than 100 USDT
        assert len(filtered) == 0

    def test_filter_orders_by_balance_sell(
        self, bot_config: BotConfig
    ) -> None:
        """Should filter sell orders by available base balance."""
        engine = BotEngine(config=bot_config)

        orders = [
            Order(side="sell", type="limit", price=Decimal("51000"), quantity=Decimal("0.1")),
        ]

        # Only 0.01 BTC available
        balance = {
            "free": {"USDT": 10000.0, "BTC": 0.01},
        }

        filtered = engine._filter_orders_by_balance(
            orders,
            Decimal("50000"),
            balance,
            min_notional=Decimal("10"),
            min_qty=Decimal("0.0001"),
            step_size=Decimal("0.0001"),
        )

        # Order needs 0.1 BTC but only 0.01 available
        # Should adjust quantity to available balance
        assert len(filtered) == 1
        assert filtered[0].quantity == Decimal("0.01")

    def test_filter_orders_by_min_notional(
        self, bot_config: BotConfig
    ) -> None:
        """Should filter orders below min notional."""
        engine = BotEngine(config=bot_config)

        orders = [
            Order(side="buy", type="limit", price=Decimal("50000"), quantity=Decimal("0.0001")),
        ]

        balance = {
            "free": {"USDT": 10000.0, "BTC": 1.0},
        }

        # Order notional: 50000 * 0.0001 = 5 USDT < 10 USDT min
        filtered = engine._filter_orders_by_balance(
            orders,
            Decimal("50000"),
            balance,
            min_notional=Decimal("10"),
            min_qty=Decimal("0.0001"),
            step_size=Decimal("0.0001"),
        )

        assert len(filtered) == 0

    def test_normalize_quantity(self, bot_config: BotConfig) -> None:
        """Should normalize quantity to step size."""
        engine = BotEngine(config=bot_config)

        # 0.01234 with step 0.001 should become 0.012
        normalized = engine._normalize_quantity(
            Decimal("0.01234"),
            min_qty=Decimal("0.001"),
            step_size=Decimal("0.001"),
        )
        assert normalized == Decimal("0.012")

    def test_normalize_quantity_below_min(
        self, bot_config: BotConfig
    ) -> None:
        """Should return 0 if normalized quantity below min."""
        engine = BotEngine(config=bot_config)

        normalized = engine._normalize_quantity(
            Decimal("0.0001"),
            min_qty=Decimal("0.001"),
            step_size=Decimal("0.001"),
        )
        assert normalized == Decimal("0")

    def test_prioritize_orders_by_price(
        self, bot_config: BotConfig
    ) -> None:
        """Should prioritize orders closest to current price."""
        engine = BotEngine(config=bot_config)

        orders = [
            Order(side="buy", type="limit", price=Decimal("45000"), quantity=Decimal("0.01")),
            Order(side="buy", type="limit", price=Decimal("49000"), quantity=Decimal("0.01")),
            Order(side="buy", type="limit", price=Decimal("48000"), quantity=Decimal("0.01")),
        ]

        balance = {
            "free": {"USDT": 500.0, "BTC": 0.0},
        }

        # Current price 50000, balance 500 USDT
        # Order at 49000 * 0.01 = 490 USDT (closest, should be accepted)
        filtered = engine._filter_orders_by_balance(
            orders,
            Decimal("50000"),
            balance,
            min_notional=Decimal("10"),
            min_qty=Decimal("0.0001"),
            step_size=Decimal("0.0001"),
        )

        # Should get the closest order
        assert len(filtered) == 1
        assert filtered[0].price == Decimal("49000")


@pytest.mark.asyncio
class TestBotEngineGridDeduplication:
    """Tests for grid level deduplication."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("0"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("0")
        mock.dynamic_range_enabled = False
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        mock.fetch_ticker = AsyncMock(return_value={"last": 50000.0})
        mock.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 10000.0, "BTC": 0.5},
                "total": {"USDT": 10000.0, "BTC": 0.5},
            }
        )
        mock.create_order = AsyncMock(
            return_value={"id": "12345", "status": "open"}
        )
        mock.get_min_notional = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    async def test_deduplicates_orders_by_grid_level(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Should skip orders with duplicate grid levels."""
        order_with_level = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.01"),
            grid_level=5,
        )
        mock_strategy.calculate_orders = MagicMock(
            return_value=[order_with_level]
        )

        mock_order_manager = MagicMock()
        mock_order_manager.get_open_orders = AsyncMock(return_value=[])
        mock_order_manager.has_active_grid_order = MagicMock(return_value=True)
        mock_order_manager.submit_order = AsyncMock()

        engine = BotEngine(
            config=bot_config, order_manager=mock_order_manager
        )
        engine._state.is_running = True

        await engine._tick()

        # Order should be skipped due to duplicate grid level
        mock_order_manager.submit_order.assert_not_called()

    async def test_allows_orders_without_duplicate_grid_level(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Should allow orders without duplicate grid levels."""
        order_with_level = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.01"),
            grid_level=5,
        )
        mock_strategy.calculate_orders = MagicMock(
            return_value=[order_with_level]
        )

        mock_order_manager = MagicMock()
        mock_order_manager.get_open_orders = AsyncMock(return_value=[])
        mock_order_manager.has_active_grid_order = MagicMock(return_value=False)
        mock_order_manager.submit_order = AsyncMock()

        engine = BotEngine(
            config=bot_config, order_manager=mock_order_manager
        )
        engine._state.is_running = True

        await engine._tick()

        # Order should be submitted
        mock_order_manager.submit_order.assert_called_once()


@pytest.mark.asyncio
class TestBotEngineOrderFilled:
    """Tests for order fill handling."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.calculate_orders = MagicMock(return_value=[])
        mock.on_order_filled = MagicMock(return_value=Decimal("50"))
        mock.get_stats = MagicMock(return_value={})
        mock.realized_pnl = Decimal("100")
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        mock.is_connected = True
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    async def test_handle_order_filled_updates_filled_count(
        self, bot_config: BotConfig
    ) -> None:
        """Should increment filled orders count."""
        engine = BotEngine(config=bot_config)

        filled_order = ManagedOrder(
            id=uuid4(),
            bot_id=bot_config.id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )
        filled_order._state = OrderState.FILLED
        filled_order.filled_quantity = Decimal("0.01")
        filled_order.average_fill_price = Decimal("50000")

        with patch("api.core.ws_manager.broadcast_pnl_update", new_callable=AsyncMock):
            await engine.handle_order_filled(filled_order)

        assert engine._state.filled_orders == 1

    async def test_handle_order_filled_updates_position_buy(
        self, bot_config: BotConfig
    ) -> None:
        """Should update position on buy fill."""
        engine = BotEngine(config=bot_config)

        filled_order = ManagedOrder(
            id=uuid4(),
            bot_id=bot_config.id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )
        filled_order._state = OrderState.FILLED
        filled_order.filled_quantity = Decimal("0.01")
        filled_order.average_fill_price = Decimal("50000")

        with patch("api.core.ws_manager.broadcast_pnl_update", new_callable=AsyncMock):
            await engine.handle_order_filled(filled_order)

        assert engine._position["BTC"] == Decimal("0.01")

    async def test_handle_order_filled_updates_position_sell(
        self, bot_config: BotConfig
    ) -> None:
        """Should update position on sell fill."""
        engine = BotEngine(config=bot_config)
        engine._position["BTC"] = Decimal("0.05")

        filled_order = ManagedOrder(
            id=uuid4(),
            bot_id=bot_config.id,
            symbol="BTC/USDT",
            side="sell",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("51000"),
        )
        filled_order._state = OrderState.FILLED
        filled_order.filled_quantity = Decimal("0.01")
        filled_order.average_fill_price = Decimal("51000")

        with patch("api.core.ws_manager.broadcast_pnl_update", new_callable=AsyncMock):
            await engine.handle_order_filled(filled_order)

        assert engine._position["BTC"] == Decimal("0.04")

    async def test_handle_order_filled_notifies_on_fill(
        self, bot_config: BotConfig
    ) -> None:
        """Should call on_order_filled callback."""
        callback = MagicMock()
        engine = BotEngine(config=bot_config, on_order_filled=callback)

        filled_order = ManagedOrder(
            id=uuid4(),
            bot_id=bot_config.id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )
        filled_order._state = OrderState.FILLED
        filled_order.filled_quantity = Decimal("0.01")
        filled_order.average_fill_price = Decimal("50000")

        with patch("api.core.ws_manager.broadcast_pnl_update", new_callable=AsyncMock):
            await engine.handle_order_filled(filled_order)

        callback.assert_called_once_with(filled_order)

    async def test_handle_order_filled_records_pnl_in_circuit_breaker(
        self, bot_config: BotConfig, mock_strategy: MagicMock
    ) -> None:
        """Should record negative P&L in circuit breaker."""
        mock_strategy.on_order_filled = MagicMock(return_value=Decimal("-25"))

        mock_cb = MagicMock()
        mock_cb.record_pnl = AsyncMock()

        engine = BotEngine(config=bot_config, circuit_breaker=mock_cb)

        filled_order = ManagedOrder(
            id=uuid4(),
            bot_id=bot_config.id,
            symbol="BTC/USDT",
            side="sell",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("49000"),
        )
        filled_order._state = OrderState.FILLED
        filled_order.filled_quantity = Decimal("0.01")
        filled_order.average_fill_price = Decimal("49000")

        with patch("api.core.ws_manager.broadcast_pnl_update", new_callable=AsyncMock):
            await engine.handle_order_filled(filled_order)

        mock_cb.record_pnl.assert_called_once_with(
            bot_config.id, Decimal("-25")
        )

    async def test_handle_partial_fill_adjusts_for_fee(
        self, bot_config: BotConfig
    ) -> None:
        """Should adjust filled quantity for fees in base asset."""
        engine = BotEngine(config=bot_config)

        filled_order = ManagedOrder(
            id=uuid4(),
            bot_id=bot_config.id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )
        filled_order._state = OrderState.FILLED
        filled_order.filled_quantity = Decimal("0.01")
        filled_order.average_fill_price = Decimal("50000")
        filled_order.fee = Decimal("0.0001")  # 1% fee
        filled_order.fee_asset = "BTC"

        with patch("api.core.ws_manager.broadcast_pnl_update", new_callable=AsyncMock):
            await engine.handle_order_filled(filled_order)

        # Position should be reduced by fee
        assert engine._position["BTC"] == Decimal("0.0099")


class TestBotEngineStats:
    """Tests for bot statistics."""

    @pytest.fixture
    def mock_strategy(self) -> MagicMock:
        """Create mock strategy."""
        mock = MagicMock()
        mock.get_stats = MagicMock(
            return_value={"grid_levels": 20, "filled_levels": 5}
        )
        mock.realized_pnl = Decimal("150")
        return mock

    @pytest.fixture
    def mock_exchange(self) -> MagicMock:
        """Create mock exchange connector."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def bot_config(
        self, mock_strategy: MagicMock, mock_exchange: MagicMock
    ) -> BotConfig:
        """Create bot configuration."""
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    def test_get_stats_returns_correct_data(
        self, bot_config: BotConfig
    ) -> None:
        """Should return correct stats."""
        engine = BotEngine(config=bot_config)
        engine._state.is_running = True
        engine._state.current_price = Decimal("50000")
        engine._state.total_orders = 10
        engine._state.filled_orders = 5
        engine._state.realized_pnl = Decimal("150")
        engine._position = {"BTC": Decimal("0.05")}

        stats = engine.get_stats()

        assert stats["bot_id"] == str(bot_config.id)
        assert stats["symbol"] == "BTC/USDT"
        assert stats["is_running"] is True
        assert stats["current_price"] == 50000.0
        assert stats["position"] == {"BTC": 0.05}
        assert stats["total_orders"] == 10
        assert stats["filled_orders"] == 5
        assert stats["realized_pnl"] == 150.0
        assert "strategy_stats" in stats
