"""
Tests for grid level deduplication functionality.

These tests validate that orders are not duplicated on the same grid level.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from bot.order_manager import ManagedOrder, OrderManager, OrderState


class TestHasActiveGridOrder:
    """Tests for OrderManager.has_active_grid_order method."""

    @pytest.fixture
    def order_manager(self):
        """Create an OrderManager with mocked dependencies."""
        mock_exchange = MagicMock()
        mock_exchange.create_order = AsyncMock()
        mock_exchange.cancel_order = AsyncMock()
        return OrderManager(
            exchange=mock_exchange,
            db_session=AsyncMock(),
            notifier=None,
        )

    @pytest.fixture
    def bot_id(self):
        """Create a sample bot ID."""
        return uuid4()

    def test_detects_open_order_same_level(self, order_manager, bot_id):
        """Test that has_active_grid_order detects an open order on the same level."""
        # Add an open order at grid_level 5
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.OPEN,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        # Should detect the order
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is True

    def test_allows_different_side_same_level(self, order_manager, bot_id):
        """Test that buy and sell orders can coexist on the same level."""
        # Add a buy order at grid_level 5
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.OPEN,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        # Sell order on same level should be allowed
        assert order_manager.has_active_grid_order(bot_id, "sell", 5) is False

    def test_allows_different_bot_same_level(self, order_manager, bot_id):
        """Test that different bots can have orders on the same level."""
        other_bot_id = uuid4()

        # Add order for other_bot_id
        order = ManagedOrder(
            bot_id=other_bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.OPEN,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        # Our bot should be able to place order on same level
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False

    def test_detects_pending_order(self, order_manager, bot_id):
        """Test that pending orders are detected as active."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.PENDING,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is True

    def test_detects_submitting_order(self, order_manager, bot_id):
        """Test that submitting orders are detected as active."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.SUBMITTING,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is True

    def test_detects_partially_filled_order(self, order_manager, bot_id):
        """Test that partially_filled orders are detected as active."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.PARTIALLY_FILLED,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is True

    def test_ignores_filled_order(self, order_manager, bot_id):
        """Test that filled orders do not block new orders on the same level."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.FILLED,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        # Filled order should not block new orders
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False

    def test_ignores_cancelled_order(self, order_manager, bot_id):
        """Test that cancelled orders do not block new orders on the same level."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.CANCELLED,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        # Cancelled order should not block new orders
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False

    def test_ignores_rejected_order(self, order_manager, bot_id):
        """Test that rejected orders do not block new orders on the same level."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.REJECTED,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False

    def test_ignores_error_order(self, order_manager, bot_id):
        """Test that error orders do not block new orders on the same level."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.ERROR,
            grid_level=5,
        )
        order_manager._orders[order.id] = order

        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False

    def test_handles_none_grid_level(self, order_manager, bot_id):
        """Test that orders without grid_level are not matched."""
        order = ManagedOrder(
            bot_id=bot_id,
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            state=OrderState.OPEN,
            grid_level=None,  # No grid level
        )
        order_manager._orders[order.id] = order

        # Should not match any specific grid level
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False

    def test_multiple_orders_different_levels(self, order_manager, bot_id):
        """Test with multiple orders on different levels."""
        # Add orders at levels 3, 5, 7
        for level in [3, 5, 7]:
            order = ManagedOrder(
                bot_id=bot_id,
                symbol="BTC/USDT",
                side="buy",
                order_type="limit",
                quantity=Decimal("0.1"),
                price=Decimal("50000"),
                state=OrderState.OPEN,
                grid_level=level,
            )
            order_manager._orders[order.id] = order

        # Levels with orders should be detected
        assert order_manager.has_active_grid_order(bot_id, "buy", 3) is True
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is True
        assert order_manager.has_active_grid_order(bot_id, "buy", 7) is True

        # Levels without orders should be free
        assert order_manager.has_active_grid_order(bot_id, "buy", 4) is False
        assert order_manager.has_active_grid_order(bot_id, "buy", 6) is False

    def test_empty_order_manager(self, order_manager, bot_id):
        """Test has_active_grid_order with no orders."""
        # Should return False when no orders exist
        assert order_manager.has_active_grid_order(bot_id, "buy", 5) is False
        assert order_manager.has_active_grid_order(bot_id, "sell", 5) is False


class TestManagedOrderGridLevel:
    """Tests for ManagedOrder grid_level attribute."""

    def test_managed_order_has_grid_level(self):
        """Test that ManagedOrder can store grid_level."""
        order = ManagedOrder(
            bot_id=uuid4(),
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            grid_level=10,
        )
        assert order.grid_level == 10

    def test_managed_order_grid_level_defaults_to_none(self):
        """Test that grid_level defaults to None."""
        order = ManagedOrder(
            bot_id=uuid4(),
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
        )
        assert order.grid_level is None
