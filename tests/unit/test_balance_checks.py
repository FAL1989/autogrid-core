"""
Tests for balance and NOTIONAL check functionality.

These tests validate the balance checks before order submission.
All tests reflect the current behavior of the code.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bot.engine import BotConfig, BotEngine
from bot.strategies.base import Order


class TestCheckMinNotional:
    """Tests for BotEngine._check_min_notional method."""

    @pytest.fixture
    def bot_config(self):
        """Create a minimal bot config."""
        mock_strategy = MagicMock()
        mock_exchange = MagicMock()
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    @pytest.fixture
    def engine(self, bot_config):
        """Create a BotEngine instance."""
        return BotEngine(config=bot_config)

    @pytest.mark.asyncio
    async def test_order_passes_min_notional(self, engine):
        """Test that order with notional >= min_notional passes."""
        engine.exchange = MagicMock()
        engine.exchange.get_min_notional = AsyncMock(return_value=Decimal("10"))

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.001"),  # notional = 50
        )

        result = await engine._check_min_notional(order, Decimal("50000"))
        assert result is True

    @pytest.mark.asyncio
    async def test_order_blocked_below_min_notional(self, engine):
        """Test that order with notional < min_notional is blocked."""
        engine.exchange = MagicMock()
        engine.exchange.get_min_notional = AsyncMock(return_value=Decimal("100"))

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.001"),  # notional = 50 < 100
        )

        result = await engine._check_min_notional(order, Decimal("50000"))
        assert result is False

    @pytest.mark.asyncio
    async def test_market_order_uses_current_price(self, engine):
        """Test that market orders use current_price when order.price is None."""
        engine.exchange = MagicMock()
        engine.exchange.get_min_notional = AsyncMock(return_value=Decimal("10"))

        order = Order(
            side="buy",
            type="market",
            price=None,  # Market order, no price
            quantity=Decimal("0.001"),
        )

        # notional = 50000 * 0.001 = 50 >= 10
        result = await engine._check_min_notional(order, Decimal("50000"))
        assert result is True

    @pytest.mark.asyncio
    async def test_no_min_notional_returns_true(self, engine):
        """Test that None min_notional returns True (no check)."""
        engine.exchange = MagicMock()
        engine.exchange.get_min_notional = AsyncMock(return_value=None)

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.0001"),  # Very small
        )

        result = await engine._check_min_notional(order, Decimal("50000"))
        assert result is True

    @pytest.mark.asyncio
    async def test_no_exchange_returns_true(self, engine):
        """Test that missing exchange returns True."""
        engine.exchange = None

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.001"),
        )

        result = await engine._check_min_notional(order, Decimal("50000"))
        assert result is True

    @pytest.mark.asyncio
    async def test_zero_price_returns_true(self, engine):
        """Test that zero price returns True (skips check)."""
        engine.exchange = MagicMock()
        engine.exchange.get_min_notional = AsyncMock(return_value=Decimal("10"))

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("0"),
            quantity=Decimal("0.001"),
        )

        result = await engine._check_min_notional(order, Decimal("0"))
        assert result is True


class TestCheckAvailableBalance:
    """Tests for BotEngine._check_available_balance method."""

    @pytest.fixture
    def bot_config(self):
        """Create a minimal bot config."""
        mock_strategy = MagicMock()
        mock_exchange = MagicMock()
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    @pytest.fixture
    def engine(self, bot_config):
        """Create a BotEngine instance."""
        return BotEngine(config=bot_config)

    def test_buy_with_sufficient_quote(self, engine):
        """Test buy order passes with sufficient quote balance."""
        balance = {"free": {"USDT": 10000, "BTC": 0.5}}

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),  # needs 5000 USDT
        )

        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is True

    def test_buy_blocked_insufficient_quote(self, engine):
        """Test buy order blocked with insufficient quote balance."""
        balance = {"free": {"USDT": 1000, "BTC": 0.5}}

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),  # needs 5000 USDT, have 1000
        )

        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is False

    def test_sell_with_sufficient_base(self, engine):
        """Test sell order passes with sufficient base balance."""
        balance = {"free": {"USDT": 10000, "BTC": 0.5}}

        order = Order(
            side="sell",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),  # needs 0.1 BTC, have 0.5
        )

        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is True

    def test_sell_blocked_insufficient_base(self, engine):
        """Test sell order blocked with insufficient base balance."""
        balance = {"free": {"USDT": 10000, "BTC": 0.05}}

        order = Order(
            side="sell",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),  # needs 0.1 BTC, have 0.05
        )

        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is False

    def test_none_balance_returns_true(self, engine):
        """Test that None balance returns True (skips check)."""
        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
        )

        result = engine._check_available_balance(order, Decimal("50000"), None)
        assert result is True

    def test_invalid_symbol_returns_true(self, engine):
        """Test that invalid symbol (no slash) returns True."""
        engine.config.symbol = "BTCUSDT"  # No slash

        balance = {"free": {"USDT": 100, "BTC": 0.001}}

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
        )

        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is True

    def test_missing_asset_in_balance(self, engine):
        """Test order blocked when asset not in balance dict."""
        balance = {"free": {"ETH": 10}}  # No USDT or BTC

        order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),  # needs USDT
        )

        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is False

    def test_market_order_uses_current_price(self, engine):
        """Test market order uses current_price for notional calculation."""
        balance = {"free": {"USDT": 10000, "BTC": 0.5}}

        order = Order(
            side="buy",
            type="market",
            price=None,  # Market order
            quantity=Decimal("0.1"),
        )

        # notional = 50000 * 0.1 = 5000
        result = engine._check_available_balance(order, Decimal("50000"), balance)
        assert result is True


class TestNormalizeQuantity:
    """Tests for BotEngine._normalize_quantity method."""

    @pytest.fixture
    def bot_config(self):
        """Create a minimal bot config."""
        mock_strategy = MagicMock()
        mock_exchange = MagicMock()
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    @pytest.fixture
    def engine(self, bot_config):
        """Create a BotEngine instance."""
        return BotEngine(config=bot_config)

    def test_rounds_down_to_step_size(self, engine):
        """Test quantity is rounded down to step_size."""
        result = engine._normalize_quantity(
            quantity=Decimal("0.12345"),
            min_qty=Decimal("0.001"),
            step_size=Decimal("0.01"),
        )
        assert result == Decimal("0.12")

    def test_returns_zero_below_min_qty(self, engine):
        """Test that quantity below min_qty returns 0."""
        result = engine._normalize_quantity(
            quantity=Decimal("0.005"),
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.001"),
        )
        assert result == Decimal("0")

    def test_none_step_size_no_rounding(self, engine):
        """Test that None step_size skips rounding."""
        result = engine._normalize_quantity(
            quantity=Decimal("0.12345"),
            min_qty=Decimal("0.001"),
            step_size=None,
        )
        assert result == Decimal("0.12345")

    def test_none_min_qty_no_minimum_check(self, engine):
        """Test that None min_qty skips minimum check."""
        result = engine._normalize_quantity(
            quantity=Decimal("0.00001"),
            min_qty=None,
            step_size=Decimal("0.00001"),
        )
        assert result == Decimal("0.00001")

    def test_zero_step_size_no_rounding(self, engine):
        """Test that zero step_size skips rounding."""
        result = engine._normalize_quantity(
            quantity=Decimal("0.12345"),
            min_qty=None,
            step_size=Decimal("0"),
        )
        assert result == Decimal("0.12345")

    def test_exact_step_size_unchanged(self, engine):
        """Test quantity that's exact multiple of step_size is unchanged."""
        result = engine._normalize_quantity(
            quantity=Decimal("0.12"),
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.01"),
        )
        assert result == Decimal("0.12")


class TestFilterOrdersByBalance:
    """Tests for BotEngine._filter_orders_by_balance method."""

    @pytest.fixture
    def bot_config(self):
        """Create a minimal bot config."""
        mock_strategy = MagicMock()
        mock_exchange = MagicMock()
        return BotConfig(
            id=uuid4(),
            user_id=uuid4(),
            strategy=mock_strategy,
            exchange=mock_exchange,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
        )

    @pytest.fixture
    def engine(self, bot_config):
        """Create a BotEngine instance."""
        return BotEngine(config=bot_config)

    def test_filters_orders_by_available_balance(self, engine):
        """Test that orders exceeding balance are filtered out."""
        balance = {"free": {"USDT": 5000, "BTC": 0.1}}

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),  # needs 5000
            Order(
                side="buy",
                type="limit",
                price=Decimal("49000"),
                quantity=Decimal("0.1"),
            ),  # needs 4900, no balance left
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=None,
            step_size=None,
        )

        # Only first order should pass (second exceeds remaining balance)
        assert len(result) == 1
        assert result[0].price == Decimal("50000")

    def test_prioritizes_by_price_proximity(self, engine):
        """Test that orders closer to current price are prioritized."""
        balance = {"free": {"USDT": 5500, "BTC": 0.1}}

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("48000"),
                quantity=Decimal("0.1"),
            ),  # far
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),  # closest
            Order(
                side="buy",
                type="limit",
                price=Decimal("49000"),
                quantity=Decimal("0.1"),
            ),  # middle
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=None,
            step_size=None,
        )

        # Order at 50000 should be first (closest), then either of others
        assert len(result) >= 1
        assert result[0].price == Decimal("50000")

    def test_adjusts_sell_quantity_to_available(self, engine):
        """Test that sell quantity is adjusted to available balance."""
        balance = {"free": {"USDT": 10000, "BTC": 0.05}}

        orders = [
            Order(
                side="sell",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),  # wants 0.1, have 0.05
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.01"),
        )

        # Order should be adjusted to available balance
        assert len(result) == 1
        assert result[0].quantity == Decimal("0.05")

    def test_removes_below_min_notional(self, engine):
        """Test that orders below min_notional are removed."""
        balance = {"free": {"USDT": 10000, "BTC": 0.1}}

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.0001"),
            ),  # notional = 5 < 10
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=Decimal("10"),
            min_qty=None,
            step_size=None,
        )

        assert len(result) == 0

    def test_none_balance_returns_all_orders(self, engine):
        """Test that None balance returns all orders unchanged."""
        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),
            Order(
                side="sell",
                type="limit",
                price=Decimal("51000"),
                quantity=Decimal("0.1"),
            ),
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=None,
            min_notional=None,
            min_qty=None,
            step_size=None,
        )

        assert len(result) == 2

    def test_invalid_symbol_returns_all_orders(self, engine):
        """Test that invalid symbol returns all orders unchanged."""
        engine.config.symbol = "BTCUSDT"  # No slash

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance={"free": {"USDT": 100}},  # Very low balance
            min_notional=None,
            min_qty=None,
            step_size=None,
        )

        # Should return orders unchanged due to invalid symbol
        assert len(result) == 1

    def test_normalizes_quantity_before_balance_check(self, engine):
        """Test that quantity is normalized before balance check."""
        balance = {"free": {"USDT": 10000, "BTC": 0.1}}

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.12345"),
            ),
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.01"),
        )

        assert len(result) == 1
        # Quantity should be normalized to 0.12
        assert result[0].quantity == Decimal("0.12")

    def test_removes_orders_with_zero_normalized_quantity(self, engine):
        """Test that orders with zero normalized quantity are removed."""
        balance = {"free": {"USDT": 10000, "BTC": 0.1}}

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.005"),
            ),  # below min_qty
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.001"),
        )

        assert len(result) == 0

    def test_multiple_buys_deplete_balance(self, engine):
        """Test that multiple buy orders deplete available balance."""
        balance = {"free": {"USDT": 10000, "BTC": 0.1}}

        orders = [
            Order(
                side="buy",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),  # needs 5000
            Order(
                side="buy",
                type="limit",
                price=Decimal("49000"),
                quantity=Decimal("0.1"),
            ),  # needs 4900
            Order(
                side="buy",
                type="limit",
                price=Decimal("48000"),
                quantity=Decimal("0.1"),
            ),  # needs 4800, no balance
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=None,
            step_size=None,
        )

        # Only 2 orders should fit in 10000 USDT
        assert len(result) == 2

    def test_multiple_sells_deplete_base_balance(self, engine):
        """Test that multiple sell orders deplete available base balance."""
        balance = {"free": {"USDT": 10000, "BTC": 0.15}}

        orders = [
            Order(
                side="sell",
                type="limit",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
            ),  # needs 0.1 BTC
            Order(
                side="sell",
                type="limit",
                price=Decimal("51000"),
                quantity=Decimal("0.1"),
            ),  # needs 0.1 BTC, only 0.05 left
        ]

        result = engine._filter_orders_by_balance(
            orders=orders,
            current_price=Decimal("50000"),
            balance=balance,
            min_notional=None,
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.01"),
        )

        # First order takes 0.1, second adjusted to 0.05
        assert len(result) == 2
        # Check that quantities sum to available balance
        total_qty = sum(o.quantity for o in result)
        assert total_qty == Decimal("0.15")
