"""
Unit Tests for Trading Strategies

Tests for GridStrategy and DCAStrategy.
"""

from decimal import Decimal

import pytest

from bot.strategies.base import Order
from bot.strategies.dca import DCAStrategy
from bot.strategies.grid import GridStrategy


class TestGridStrategy:
    """Tests for GridStrategy."""

    def test_init_valid_params(self, grid_config: dict) -> None:
        """Test initialization with valid parameters."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        assert strategy.symbol == "BTC/USDT"
        assert strategy.grid_count == 20
        assert strategy.lower_price == Decimal("45000")
        assert strategy.upper_price == Decimal("55000")

    def test_init_invalid_price_range(self) -> None:
        """Test that invalid price range raises error."""
        with pytest.raises(ValueError, match="lower_price must be less than upper_price"):
            GridStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                lower_price=Decimal("55000"),
                upper_price=Decimal("45000"),
                grid_count=20,
            )

    def test_init_invalid_grid_count(self) -> None:
        """Test that invalid grid count raises error."""
        with pytest.raises(ValueError, match="grid_count must be at least 2"):
            GridStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                lower_price=Decimal("45000"),
                upper_price=Decimal("55000"),
                grid_count=1,
            )

    def test_grid_spacing_calculation(self, grid_config: dict) -> None:
        """Test that grid spacing is calculated correctly."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # (55000 - 45000) / 20 = 500
        assert strategy.grid_spacing == Decimal("500")

    def test_calculate_orders_creates_buy_orders(self, grid_config: dict) -> None:
        """Test that buy orders are created below current price."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        current_price = Decimal("50000")
        orders = strategy.calculate_orders(current_price, [])

        # Should have buy orders below current price
        buy_orders = [o for o in orders if o.side == "buy"]
        assert len(buy_orders) > 0

        # All buy orders should be below current price
        for order in buy_orders:
            assert order.price is not None
            assert order.price < current_price

    def test_on_order_filled_tracks_pnl(self, grid_config: dict) -> None:
        """Test that P&L is tracked when orders are filled."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Simulate buy and sell
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49500"),
            quantity=Decimal("0.02"),
        )
        sell_order = Order(
            side="sell",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.02"),
        )

        strategy.on_order_filled(buy_order, Decimal("49500"))
        strategy.on_order_filled(sell_order, Decimal("50000"))

        # Profit = (50000 - 49500) * 0.02 = 10
        assert strategy.realized_pnl == Decimal("10")


class TestDCAStrategy:
    """Tests for DCAStrategy."""

    def test_init_valid_params(self, dca_config: dict) -> None:
        """Test initialization with valid parameters."""
        strategy = DCAStrategy(
            symbol=dca_config["symbol"],
            investment=Decimal(str(dca_config["investment"])),
            amount_per_buy=Decimal(str(dca_config["amount_per_buy"])),
            interval=dca_config["interval"],
            trigger_drop_percent=Decimal(str(dca_config["trigger_drop_percent"])),
            take_profit_percent=Decimal(str(dca_config["take_profit_percent"])),
        )

        assert strategy.symbol == "BTC/USDT"
        assert strategy.amount_per_buy == Decimal("100")
        assert strategy.interval == "daily"

    def test_remaining_budget(self, dca_config: dict) -> None:
        """Test remaining budget calculation."""
        strategy = DCAStrategy(
            symbol=dca_config["symbol"],
            investment=Decimal(str(dca_config["investment"])),
            amount_per_buy=Decimal(str(dca_config["amount_per_buy"])),
            interval=dca_config["interval"],
        )

        assert strategy.remaining_budget == Decimal("1000")

    def test_average_entry_price_zero_position(self, dca_config: dict) -> None:
        """Test average entry price with no position."""
        strategy = DCAStrategy(
            symbol=dca_config["symbol"],
            investment=Decimal(str(dca_config["investment"])),
            amount_per_buy=Decimal(str(dca_config["amount_per_buy"])),
            interval=dca_config["interval"],
        )

        assert strategy.average_entry_price == Decimal("0")

    def test_should_stop_budget_exhausted(self, dca_config: dict) -> None:
        """Test that strategy stops when budget is exhausted."""
        strategy = DCAStrategy(
            symbol=dca_config["symbol"],
            investment=Decimal("50"),  # Small budget
            amount_per_buy=Decimal("100"),  # More than budget
            interval=dca_config["interval"],
        )

        # Should stop since budget < amount_per_buy and no position
        assert strategy.should_stop() is True

    def test_calculate_orders_first_buy(self, dca_config: dict) -> None:
        """Test first buy order is created."""
        strategy = DCAStrategy(
            symbol=dca_config["symbol"],
            investment=Decimal(str(dca_config["investment"])),
            amount_per_buy=Decimal(str(dca_config["amount_per_buy"])),
            interval=dca_config["interval"],
        )

        current_price = Decimal("50000")
        orders = strategy.calculate_orders(current_price, [])

        # First call should create a buy order (no last_buy_time)
        assert len(orders) == 1
        assert orders[0].side == "buy"
        assert orders[0].type == "market"

    def test_get_stats(self, dca_config: dict) -> None:
        """Test statistics retrieval."""
        strategy = DCAStrategy(
            symbol=dca_config["symbol"],
            investment=Decimal(str(dca_config["investment"])),
            amount_per_buy=Decimal(str(dca_config["amount_per_buy"])),
            interval=dca_config["interval"],
        )

        stats = strategy.get_stats()

        assert stats["symbol"] == "BTC/USDT"
        assert stats["investment"] == 1000.0
        assert stats["amount_per_buy"] == 100.0
        assert stats["interval"] == "daily"
        assert stats["remaining_budget"] == 1000.0
