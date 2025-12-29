"""
Unit Tests for Complete Grid Trading Strategy

Tests for GridStrategy with:
- GridLevel position tracking
- Sell order generation
- P&L calculation
- Stop conditions
"""

from decimal import Decimal

import pytest

from bot.strategies.base import Order
from bot.strategies.grid import GridLevel, GridStrategy


class TestGridLevel:
    """Tests for GridLevel dataclass."""

    def test_grid_level_creation(self) -> None:
        """Test GridLevel can be created with default values."""
        level = GridLevel(price=Decimal("50000"), index=5)

        assert level.price == Decimal("50000")
        assert level.index == 5
        assert level.buy_order_id is None
        assert level.sell_order_id is None
        assert level.position_qty == Decimal("0")
        assert level.avg_buy_price is None

    def test_has_position_empty(self) -> None:
        """Test has_position returns False when no position."""
        level = GridLevel(price=Decimal("50000"), index=5)

        assert level.has_position() is False

    def test_has_position_with_quantity(self) -> None:
        """Test has_position returns True when position exists."""
        level = GridLevel(
            price=Decimal("50000"),
            index=5,
            position_qty=Decimal("0.1"),
            avg_buy_price=Decimal("49500"),
        )

        assert level.has_position() is True


class TestGridStrategyBuyOrders:
    """Tests for GridStrategy buy order generation."""

    def test_generates_buy_orders_below_price(self, grid_config: dict) -> None:
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

        buy_orders = [o for o in orders if o.side == "buy"]

        # Should have buy orders
        assert len(buy_orders) > 0

        # All buy orders should be below current price
        for order in buy_orders:
            assert order.price is not None
            assert order.price < current_price

    def test_buy_orders_have_grid_level(self, grid_config: dict) -> None:
        """Test that buy orders have grid_level set."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        current_price = Decimal("50000")
        orders = strategy.calculate_orders(current_price, [])

        buy_orders = [o for o in orders if o.side == "buy"]

        for order in buy_orders:
            assert order.grid_level is not None
            assert isinstance(order.grid_level, int)

    def test_no_duplicate_buy_orders(self, grid_config: dict) -> None:
        """Test that buy orders are not created if open orders exist."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        current_price = Decimal("50000")

        # First call - generate orders
        first_orders = strategy.calculate_orders(current_price, [])
        buy_orders = [o for o in first_orders if o.side == "buy"]

        # Second call - pass existing orders as open orders
        # Simulate orders with grid_level set
        second_orders = strategy.calculate_orders(current_price, buy_orders)

        # Should not generate duplicate orders for same levels
        new_buy_orders = [o for o in second_orders if o.side == "buy"]
        assert len(new_buy_orders) == 0


class TestGridStrategySellOrders:
    """Tests for GridStrategy sell order generation."""

    def test_generates_sell_orders_with_position(self, grid_config: dict) -> None:
        """Test that sell orders are created when position exists and price is above."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Simulate buy order filled at level 5 (price = 47500)
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("47500"),
            quantity=Decimal("0.02"),
            grid_level=5,
        )
        strategy.on_order_filled(buy_order, Decimal("47500"))

        # Current price BELOW the level with position
        # The sell order should be generated because the level price (47500) is ABOVE current price (46000)
        current_price = Decimal("46000")
        orders = strategy.calculate_orders(current_price, [])

        # Sell order should be generated for level 5 (47500 > 46000)
        sell_orders = [o for o in orders if o.side == "sell"]
        assert len(sell_orders) == 1
        assert sell_orders[0].grid_level == 5
        assert sell_orders[0].price == Decimal("47500")
        assert sell_orders[0].quantity == Decimal("0.02")

    def test_no_sell_orders_when_price_above_position(self, grid_config: dict) -> None:
        """Test that no sell orders when current price is above position level."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Simulate buy order filled at level 5 (price = 47500)
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("47500"),
            quantity=Decimal("0.02"),
            grid_level=5,
        )
        strategy.on_order_filled(buy_order, Decimal("47500"))

        # Current price ABOVE the level with position
        # No sell order because the level price (47500) is BELOW current price (48000)
        current_price = Decimal("48000")
        orders = strategy.calculate_orders(current_price, [])

        # No sell orders when level price is below current price
        sell_orders = [o for o in orders if o.side == "sell"]
        assert len(sell_orders) == 0

    def test_sell_orders_have_grid_level(self, grid_config: dict) -> None:
        """Test that sell orders have grid_level set."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Simulate position at level 10
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.02"),
            grid_level=10,
        )
        strategy.on_order_filled(buy_order, Decimal("50000"))

        # Price below position to generate sell
        current_price = Decimal("49500")
        orders = strategy.calculate_orders(current_price, [])

        sell_orders = [o for o in orders if o.side == "sell"]

        for order in sell_orders:
            assert order.grid_level is not None
            assert isinstance(order.grid_level, int)


class TestGridStrategyPnL:
    """Tests for GridStrategy P&L calculation."""

    def test_buy_order_returns_zero_pnl(self, grid_config: dict) -> None:
        """Test that buy orders return 0 P&L."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        pnl = strategy.on_order_filled(buy_order, Decimal("49000"))

        assert pnl == Decimal("0")
        assert strategy.realized_pnl == Decimal("0")

    def test_sell_order_calculates_profit(self, grid_config: dict) -> None:
        """Test that sell order calculates correct profit."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Buy at 49000
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        strategy.on_order_filled(buy_order, Decimal("49000"))

        # Sell at 49500
        sell_order = Order(
            side="sell",
            type="limit",
            price=Decimal("49500"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        pnl = strategy.on_order_filled(sell_order, Decimal("49500"))

        # Profit = (49500 - 49000) * 0.02 = 10
        expected_pnl = Decimal("10")
        assert pnl == expected_pnl
        assert strategy.realized_pnl == expected_pnl

    def test_sell_order_calculates_loss(self, grid_config: dict) -> None:
        """Test that sell order calculates correct loss."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Buy at 50000
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.02"),
            grid_level=10,
        )
        strategy.on_order_filled(buy_order, Decimal("50000"))

        # Sell at 49000 (loss)
        sell_order = Order(
            side="sell",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.02"),
            grid_level=10,
        )
        pnl = strategy.on_order_filled(sell_order, Decimal("49000"))

        # Loss = (49000 - 50000) * 0.02 = -20
        expected_pnl = Decimal("-20")
        assert pnl == expected_pnl
        assert strategy.realized_pnl == expected_pnl

    def test_multiple_cycles_accumulate_pnl(self, grid_config: dict) -> None:
        """Test that multiple buy/sell cycles accumulate P&L."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # First cycle: +10 profit
        buy1 = Order(side="buy", type="limit", price=Decimal("49000"),
                     quantity=Decimal("0.02"), grid_level=8)
        sell1 = Order(side="sell", type="limit", price=Decimal("49500"),
                      quantity=Decimal("0.02"), grid_level=8)
        strategy.on_order_filled(buy1, Decimal("49000"))
        strategy.on_order_filled(sell1, Decimal("49500"))

        # Second cycle: +20 profit
        buy2 = Order(side="buy", type="limit", price=Decimal("48000"),
                     quantity=Decimal("0.02"), grid_level=6)
        sell2 = Order(side="sell", type="limit", price=Decimal("49000"),
                      quantity=Decimal("0.02"), grid_level=6)
        strategy.on_order_filled(buy2, Decimal("48000"))
        strategy.on_order_filled(sell2, Decimal("49000"))

        # Total P&L = 10 + 20 = 30
        assert strategy.realized_pnl == Decimal("30")


class TestGridStrategyPositionTracking:
    """Tests for GridStrategy position tracking."""

    def test_position_tracked_on_buy(self, grid_config: dict) -> None:
        """Test that position is tracked when buy order fills."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        strategy.on_order_filled(buy_order, Decimal("49000"))

        # Check position at level 8
        level = strategy._levels[8]
        assert level.position_qty == Decimal("0.02")
        assert level.avg_buy_price == Decimal("49000")
        assert level.has_position() is True

    def test_position_cleared_on_sell(self, grid_config: dict) -> None:
        """Test that position is cleared when sell order fills."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Buy first
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        strategy.on_order_filled(buy_order, Decimal("49000"))

        # Then sell
        sell_order = Order(
            side="sell",
            type="limit",
            price=Decimal("49500"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        strategy.on_order_filled(sell_order, Decimal("49500"))

        # Position should be cleared
        level = strategy._levels[8]
        assert level.position_qty == Decimal("0")
        assert level.avg_buy_price is None
        assert level.has_position() is False

    def test_get_total_position(self, grid_config: dict) -> None:
        """Test get_total_position aggregates across levels."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Buy at multiple levels
        buy1 = Order(side="buy", type="limit", price=Decimal("49000"),
                     quantity=Decimal("0.02"), grid_level=8)
        buy2 = Order(side="buy", type="limit", price=Decimal("48000"),
                     quantity=Decimal("0.03"), grid_level=6)
        strategy.on_order_filled(buy1, Decimal("49000"))
        strategy.on_order_filled(buy2, Decimal("48000"))

        total = strategy.get_total_position()
        assert total == Decimal("0.05")

    def test_get_average_entry_price(self, grid_config: dict) -> None:
        """Test get_average_entry_price calculates weighted average."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Buy at multiple levels
        buy1 = Order(side="buy", type="limit", price=Decimal("49000"),
                     quantity=Decimal("0.02"), grid_level=8)
        buy2 = Order(side="buy", type="limit", price=Decimal("48000"),
                     quantity=Decimal("0.02"), grid_level=6)
        strategy.on_order_filled(buy1, Decimal("49000"))
        strategy.on_order_filled(buy2, Decimal("48000"))

        # Average = (49000 * 0.02 + 48000 * 0.02) / (0.02 + 0.02) = 48500
        avg = strategy.get_average_entry_price()
        assert avg == Decimal("48500")


class TestGridStrategyUnrealizedPnL:
    """Tests for GridStrategy unrealized P&L calculation."""

    def test_unrealized_pnl_profit(self, grid_config: dict) -> None:
        """Test unrealized P&L when price is above entry."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            grid_level=8,
        )
        strategy.on_order_filled(buy_order, Decimal("49000"))

        # Price at 50000 = +1000 profit on 0.1 BTC
        unrealized = strategy.get_unrealized_pnl(Decimal("50000"))
        assert unrealized == Decimal("100")

    def test_unrealized_pnl_loss(self, grid_config: dict) -> None:
        """Test unrealized P&L when price is below entry."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            grid_level=10,
        )
        strategy.on_order_filled(buy_order, Decimal("50000"))

        # Price at 49000 = -1000 loss on 0.1 BTC
        unrealized = strategy.get_unrealized_pnl(Decimal("49000"))
        assert unrealized == Decimal("-100")


class TestGridStrategyShouldStop:
    """Tests for GridStrategy stop conditions."""

    def test_should_stop_returns_false_in_range(self, grid_config: dict) -> None:
        """Test should_stop returns False when price is in range."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Price in range
        strategy._current_price = Decimal("50000")
        assert strategy.should_stop() is False

    def test_should_stop_below_lower_bound(self, grid_config: dict) -> None:
        """Test should_stop returns True when price drops 5% below lower bound."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),  # 45000
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # 5% below 45000 = 42750
        strategy._current_price = Decimal("42000")
        assert strategy.should_stop() is True

    def test_should_stop_above_upper_bound(self, grid_config: dict) -> None:
        """Test should_stop returns True when price rises 5% above upper bound."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),  # 55000
            grid_count=grid_config["grid_count"],
        )

        # 5% above 55000 = 57750
        strategy._current_price = Decimal("58000")
        assert strategy.should_stop() is True

    def test_should_stop_at_boundary_returns_false(self, grid_config: dict) -> None:
        """Test should_stop returns False at exact boundary."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Exactly at lower bound
        strategy._current_price = Decimal("45000")
        assert strategy.should_stop() is False

        # Exactly at upper bound
        strategy._current_price = Decimal("55000")
        assert strategy.should_stop() is False


class TestGridStrategyStats:
    """Tests for GridStrategy statistics."""

    def test_get_stats_includes_grid_info(self, grid_config: dict) -> None:
        """Test get_stats includes grid-specific information."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        stats = strategy.get_stats()

        assert "lower_price" in stats
        assert "upper_price" in stats
        assert "grid_count" in stats
        assert "grid_spacing" in stats
        assert "amount_per_grid" in stats
        assert "total_position" in stats
        assert "average_entry_price" in stats
        assert "unrealized_pnl" in stats
        assert "levels_with_position" in stats

    def test_get_stats_updates_after_trades(self, grid_config: dict) -> None:
        """Test get_stats reflects actual trading state."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        # Buy at a level
        buy_order = Order(
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.02"),
            grid_level=8,
        )
        strategy.on_order_filled(buy_order, Decimal("49000"))
        strategy._current_price = Decimal("49000")

        stats = strategy.get_stats()

        assert stats["total_position"] == 0.02
        assert stats["levels_with_position"] == 1
        assert stats["average_entry_price"] == 49000.0

    def test_get_level_states(self, grid_config: dict) -> None:
        """Test get_level_states returns all level information."""
        strategy = GridStrategy(
            symbol=grid_config["symbol"],
            investment=Decimal(str(grid_config["investment"])),
            lower_price=Decimal(str(grid_config["lower_price"])),
            upper_price=Decimal(str(grid_config["upper_price"])),
            grid_count=grid_config["grid_count"],
        )

        levels = strategy.get_level_states()

        # Should have grid_count + 1 levels
        assert len(levels) == grid_config["grid_count"] + 1

        for level in levels:
            assert "index" in level
            assert "price" in level
            assert "position_qty" in level
            assert "avg_buy_price" in level
            assert "has_position" in level
