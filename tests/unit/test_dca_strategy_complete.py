"""
Complete Tests for DCA Strategy.

Comprehensive tests covering:
- Parameter validation
- Time-based buying
- Price-drop trigger
- Take profit
- Order fill processing
- State persistence
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from bot.strategies.base import Order
from bot.strategies.dca import DCAStrategy


class TestDCAStrategyValidation:
    """Tests for DCA parameter validation."""

    def test_rejects_negative_investment(self) -> None:
        """Test that negative investment raises error."""
        with pytest.raises(ValueError, match="investment must be positive"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("-100"),
                amount_per_buy=Decimal("50"),
                interval="daily",
            )

    def test_rejects_zero_investment(self) -> None:
        """Test that zero investment raises error."""
        with pytest.raises(ValueError, match="investment must be positive"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("0"),
                amount_per_buy=Decimal("50"),
                interval="daily",
            )

    def test_rejects_negative_amount_per_buy(self) -> None:
        """Test that negative amount_per_buy raises error."""
        with pytest.raises(ValueError, match="amount_per_buy must be positive"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("-100"),
                interval="daily",
            )

    def test_rejects_zero_amount_per_buy(self) -> None:
        """Test that zero amount_per_buy raises error."""
        with pytest.raises(ValueError, match="amount_per_buy must be positive"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("0"),
                interval="daily",
            )

    def test_rejects_amount_exceeding_investment(self) -> None:
        """Test that amount_per_buy > investment raises error."""
        with pytest.raises(ValueError, match="cannot exceed investment"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("100"),
                amount_per_buy=Decimal("200"),
                interval="daily",
            )

    def test_rejects_invalid_drop_percent_too_high(self) -> None:
        """Test that trigger_drop_percent > 100 raises error."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("100"),
                trigger_drop_percent=Decimal("150"),
            )

    def test_rejects_invalid_drop_percent_zero(self) -> None:
        """Test that trigger_drop_percent = 0 raises error."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("100"),
                trigger_drop_percent=Decimal("0"),
            )

    def test_rejects_negative_drop_percent(self) -> None:
        """Test that negative trigger_drop_percent raises error."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("100"),
                trigger_drop_percent=Decimal("-5"),
            )

    def test_rejects_negative_take_profit(self) -> None:
        """Test that negative take_profit_percent raises error."""
        with pytest.raises(ValueError, match="take_profit_percent must be positive"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("100"),
                interval="daily",
                take_profit_percent=Decimal("-10"),
            )

    def test_rejects_zero_take_profit(self) -> None:
        """Test that zero take_profit_percent raises error."""
        with pytest.raises(ValueError, match="take_profit_percent must be positive"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("100"),
                interval="daily",
                take_profit_percent=Decimal("0"),
            )

    def test_requires_at_least_one_trigger(self) -> None:
        """Test that at least one trigger is required."""
        with pytest.raises(ValueError, match="At least one trigger"):
            DCAStrategy(
                symbol="BTC/USDT",
                investment=Decimal("1000"),
                amount_per_buy=Decimal("100"),
                interval=None,
                trigger_drop_percent=None,
            )

    def test_accepts_interval_only(self) -> None:
        """Test that interval-only trigger is valid."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            trigger_drop_percent=None,
        )
        assert strategy.interval == "daily"
        assert strategy.trigger_drop_percent is None

    def test_accepts_drop_only(self) -> None:
        """Test that drop-only trigger is valid."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval=None,
            trigger_drop_percent=Decimal("5"),
        )
        assert strategy.interval is None
        assert strategy.trigger_drop_percent == Decimal("5")

    def test_accepts_both_triggers(self) -> None:
        """Test that both triggers can be used together."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="hourly",
            trigger_drop_percent=Decimal("5"),
        )
        assert strategy.interval == "hourly"
        assert strategy.trigger_drop_percent == Decimal("5")


class TestDCATimeBased:
    """Tests for time-based buying."""

    def test_first_buy_immediate(self) -> None:
        """Test that first buy happens immediately (no last_buy_time)."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="hourly",
        )

        # First call should return True (no previous buy time)
        assert strategy._should_buy_by_time() is True

    def test_hourly_interval_not_elapsed(self) -> None:
        """Test that buy is blocked if hourly interval not elapsed."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="hourly",
        )
        # Simulate last buy 30 minutes ago
        strategy._last_buy_time = datetime.utcnow() - timedelta(minutes=30)

        assert strategy._should_buy_by_time() is False

    def test_hourly_interval_elapsed(self) -> None:
        """Test that buy is allowed after 1 hour."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="hourly",
        )
        # Simulate last buy 61 minutes ago
        strategy._last_buy_time = datetime.utcnow() - timedelta(hours=1, minutes=1)

        assert strategy._should_buy_by_time() is True

    def test_daily_interval_not_elapsed(self) -> None:
        """Test that buy is blocked if daily interval not elapsed."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Simulate last buy 12 hours ago
        strategy._last_buy_time = datetime.utcnow() - timedelta(hours=12)

        assert strategy._should_buy_by_time() is False

    def test_daily_interval_elapsed(self) -> None:
        """Test that buy is allowed after 24 hours."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Simulate last buy 25 hours ago
        strategy._last_buy_time = datetime.utcnow() - timedelta(hours=25)

        assert strategy._should_buy_by_time() is True

    def test_weekly_interval_not_elapsed(self) -> None:
        """Test that buy is blocked if weekly interval not elapsed."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="weekly",
        )
        # Simulate last buy 3 days ago
        strategy._last_buy_time = datetime.utcnow() - timedelta(days=3)

        assert strategy._should_buy_by_time() is False

    def test_weekly_interval_elapsed(self) -> None:
        """Test that buy is allowed after 7 days."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="weekly",
        )
        # Simulate last buy 8 days ago
        strategy._last_buy_time = datetime.utcnow() - timedelta(days=8)

        assert strategy._should_buy_by_time() is True

    def test_no_interval_returns_false(self) -> None:
        """Test that _should_buy_by_time returns False when interval is None."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("5"),  # Only drop trigger
        )

        assert strategy._should_buy_by_time() is False


class TestDCAPriceDrop:
    """Tests for price-drop trigger."""

    def test_drop_not_triggered_without_highest_price(self) -> None:
        """Test that drop is not triggered without reference price."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("5"),
        )
        # No _highest_price set yet
        assert strategy._should_buy_by_drop(Decimal("95")) is False

    def test_drop_detected_correctly(self) -> None:
        """Test that 5% drop triggers buy."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("5"),
        )
        strategy._highest_price = Decimal("100")

        # 5% drop (100 -> 95) should trigger
        assert strategy._should_buy_by_drop(Decimal("95")) is True

    def test_drop_not_triggered_below_threshold(self) -> None:
        """Test that 4% drop does not trigger 5% threshold."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("5"),
        )
        strategy._highest_price = Decimal("100")

        # 4% drop (100 -> 96) should not trigger
        assert strategy._should_buy_by_drop(Decimal("96")) is False

    def test_drop_triggered_at_exact_threshold(self) -> None:
        """Test that exact threshold triggers buy."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("10"),
        )
        strategy._highest_price = Decimal("50000")

        # Exactly 10% drop
        assert strategy._should_buy_by_drop(Decimal("45000")) is True

    def test_highest_price_updated_on_rise(self) -> None:
        """Test that highest price is updated when price rises."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("5"),
        )

        strategy._update_price_tracking(Decimal("100"))
        assert strategy._highest_price == Decimal("100")

        strategy._update_price_tracking(Decimal("110"))
        assert strategy._highest_price == Decimal("110")

        strategy._update_price_tracking(Decimal("105"))
        # Should not decrease
        assert strategy._highest_price == Decimal("110")

    def test_last_price_always_updated(self) -> None:
        """Test that last price is always updated."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            trigger_drop_percent=Decimal("5"),
        )

        strategy._update_price_tracking(Decimal("100"))
        assert strategy._last_price == Decimal("100")

        strategy._update_price_tracking(Decimal("90"))
        assert strategy._last_price == Decimal("90")

    def test_no_drop_trigger_returns_false(self) -> None:
        """Test that _should_buy_by_drop returns False when trigger is None."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",  # Only time trigger
        )
        strategy._highest_price = Decimal("100")

        assert strategy._should_buy_by_drop(Decimal("80")) is False


class TestDCATakeProfit:
    """Tests for take-profit."""

    def test_take_profit_no_position(self) -> None:
        """Test that take profit is not triggered with no position."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            take_profit_percent=Decimal("10"),
        )
        # No position
        assert strategy._should_take_profit(Decimal("55000")) is False

    def test_take_profit_triggered(self) -> None:
        """Test that take profit triggers at 10% profit."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            take_profit_percent=Decimal("10"),
        )
        # Simulate position: bought at $50,000 avg
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")  # avg = 50000

        # 10% profit: 50000 * 1.10 = 55000
        assert strategy._should_take_profit(Decimal("55000")) is True

    def test_take_profit_not_triggered_below_threshold(self) -> None:
        """Test that take profit is not triggered below threshold."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            take_profit_percent=Decimal("10"),
        )
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")  # avg = 50000

        # 8% profit: 50000 * 1.08 = 54000
        assert strategy._should_take_profit(Decimal("54000")) is False

    def test_take_profit_at_exact_threshold(self) -> None:
        """Test that exact threshold triggers take profit."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            take_profit_percent=Decimal("10"),
        )
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")

        # Exactly 10%
        assert strategy._should_take_profit(Decimal("55000")) is True

    def test_no_take_profit_returns_false(self) -> None:
        """Test that take profit returns False when not configured."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            take_profit_percent=None,
        )
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")

        assert strategy._should_take_profit(Decimal("100000")) is False


class TestDCAOnOrderFilled:
    """Tests for order fill processing."""

    def test_buy_updates_position(self) -> None:
        """Test that buy order updates position correctly."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        order = Order(
            side="buy",
            type="market",
            price=Decimal("50000"),
            quantity=Decimal("0.002"),  # 100 / 50000
        )

        pnl = strategy.on_order_filled(order, Decimal("50000"))

        assert pnl == Decimal("0")  # Buys have no realized P&L
        assert strategy._total_quantity == Decimal("0.002")
        assert strategy._total_spent == Decimal("100")  # 50000 * 0.002
        assert strategy._last_buy_time is not None

    def test_buy_updates_average_price(self) -> None:
        """Test that average price is calculated correctly after multiple buys."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )

        # First buy at 50000
        order1 = Order(side="buy", type="market", price=Decimal("50000"), quantity=Decimal("0.002"))
        strategy.on_order_filled(order1, Decimal("50000"))

        # Second buy at 48000
        order2 = Order(side="buy", type="market", price=Decimal("48000"), quantity=Decimal("0.002"))
        strategy.on_order_filled(order2, Decimal("48000"))

        # Total spent: 100 + 96 = 196
        # Total quantity: 0.004
        # Average: 196 / 0.004 = 49000
        assert strategy._total_spent == Decimal("196")
        assert strategy._total_quantity == Decimal("0.004")
        assert strategy.average_entry_price == Decimal("49000")

    def test_sell_calculates_pnl_profit(self) -> None:
        """Test that sell order calculates profit correctly."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Setup position: bought at $50,000 avg
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")

        order = Order(
            side="sell",
            type="market",
            price=Decimal("55000"),
            quantity=Decimal("0.02"),
        )

        pnl = strategy.on_order_filled(order, Decimal("55000"))

        # P&L = (55000 * 0.02) - 1000 = 1100 - 1000 = 100
        assert pnl == Decimal("100")
        assert strategy.realized_pnl == Decimal("100")
        assert strategy._total_quantity == Decimal("0")
        assert strategy._total_spent == Decimal("0")

    def test_sell_calculates_pnl_loss(self) -> None:
        """Test that sell order calculates loss correctly."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Setup position: bought at $50,000 avg
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")

        order = Order(
            side="sell",
            type="market",
            price=Decimal("45000"),
            quantity=Decimal("0.02"),
        )

        pnl = strategy.on_order_filled(order, Decimal("45000"))

        # P&L = (45000 * 0.02) - 1000 = 900 - 1000 = -100
        assert pnl == Decimal("-100")
        assert strategy.realized_pnl == Decimal("-100")

    def test_sell_resets_position(self) -> None:
        """Test that sell resets position state."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")
        strategy._highest_price = Decimal("55000")

        order = Order(side="sell", type="market", price=Decimal("50000"), quantity=Decimal("0.02"))
        strategy.on_order_filled(order, Decimal("50000"))

        assert strategy._total_quantity == Decimal("0")
        assert strategy._total_spent == Decimal("0")
        assert strategy._highest_price is None


class TestDCACalculateOrders:
    """Tests for calculate_orders method."""

    def test_creates_buy_on_first_call(self) -> None:
        """Test that first call creates a buy order."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )

        orders = strategy.calculate_orders(Decimal("50000"), [])

        assert len(orders) == 1
        assert orders[0].side == "buy"
        assert orders[0].type == "market"

    def test_no_order_when_budget_exhausted(self) -> None:
        """Test that no order is created when budget is exhausted."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("100"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Simulate spending the budget
        strategy._total_spent = Decimal("100")
        # remaining_budget = 100 - 100 = 0, which is < amount_per_buy
        orders = strategy.calculate_orders(Decimal("50000"), [])

        assert len(orders) == 0

    def test_creates_sell_on_take_profit(self) -> None:
        """Test that take profit creates sell order."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            take_profit_percent=Decimal("10"),
        )
        strategy._total_spent = Decimal("1000")
        strategy._total_quantity = Decimal("0.02")  # avg = 50000

        # Price at 55000 = 10% profit
        orders = strategy.calculate_orders(Decimal("55000"), [])

        assert len(orders) == 1
        assert orders[0].side == "sell"
        assert orders[0].quantity == Decimal("0.02")

    def test_time_and_drop_both_checked(self) -> None:
        """Test that both time and drop triggers are checked independently."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="hourly",
            trigger_drop_percent=Decimal("5"),
        )
        strategy._last_buy_time = datetime.utcnow()  # Recent buy
        strategy._highest_price = Decimal("100")

        # Time trigger: blocked (recent buy)
        # Drop trigger: should be checked independently

        # Price at 94 = 6% drop, should trigger
        orders = strategy.calculate_orders(Decimal("94"), [])

        assert len(orders) == 1
        assert orders[0].side == "buy"

    def test_no_duplicate_buy_orders(self) -> None:
        """Test that duplicate buy orders are prevented."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="hourly",
            trigger_drop_percent=Decimal("5"),
        )
        strategy._highest_price = Decimal("100")
        # Both triggers would fire

        orders = strategy.calculate_orders(Decimal("94"), [])

        # Should only have one buy order
        buy_orders = [o for o in orders if o.side == "buy"]
        assert len(buy_orders) == 1


class TestDCAStatePersistence:
    """Tests for state serialization and restoration."""

    def test_to_state_dict(self) -> None:
        """Test that state is serialized correctly."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        strategy._last_buy_time = datetime(2025, 1, 1, 12, 0, 0)
        strategy._last_price = Decimal("50000")
        strategy._highest_price = Decimal("52000")
        strategy._total_spent = Decimal("500")
        strategy._total_quantity = Decimal("0.01")
        strategy.realized_pnl = Decimal("25")

        state = strategy.to_state_dict()

        assert state["last_buy_time"] == "2025-01-01T12:00:00"
        assert state["last_price"] == "50000"
        assert state["highest_price"] == "52000"
        assert state["total_spent"] == "500"
        assert state["total_quantity"] == "0.01"
        assert state["realized_pnl"] == "25"

    def test_to_state_dict_with_none_values(self) -> None:
        """Test serialization with None values."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Fresh strategy with no state

        state = strategy.to_state_dict()

        assert state["last_buy_time"] is None
        assert state["last_price"] is None
        assert state["highest_price"] is None
        assert state["total_spent"] == "0"
        assert state["total_quantity"] == "0"

    def test_from_state_dict_restores_state(self) -> None:
        """Test that state is restored correctly."""
        state = {
            "last_buy_time": "2025-01-01T12:00:00",
            "last_price": "50000",
            "highest_price": "52000",
            "total_spent": "500",
            "total_quantity": "0.01",
            "realized_pnl": "25",
        }

        strategy = DCAStrategy.from_state_dict(
            state=state,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )

        assert strategy._last_buy_time == datetime(2025, 1, 1, 12, 0, 0)
        assert strategy._last_price == Decimal("50000")
        assert strategy._highest_price == Decimal("52000")
        assert strategy._total_spent == Decimal("500")
        assert strategy._total_quantity == Decimal("0.01")
        assert strategy.realized_pnl == Decimal("25")

    def test_from_state_dict_with_empty_state(self) -> None:
        """Test restoration from empty state."""
        state = {}

        strategy = DCAStrategy.from_state_dict(
            state=state,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )

        assert strategy._last_buy_time is None
        assert strategy._total_spent == Decimal("0")
        assert strategy._total_quantity == Decimal("0")

    def test_roundtrip_serialization(self) -> None:
        """Test that state survives roundtrip serialization."""
        original = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            trigger_drop_percent=Decimal("5"),
            take_profit_percent=Decimal("10"),
        )
        original._last_buy_time = datetime(2025, 6, 15, 9, 30, 0)
        original._last_price = Decimal("48500")
        original._highest_price = Decimal("51000")
        original._total_spent = Decimal("300")
        original._total_quantity = Decimal("0.006")
        original.realized_pnl = Decimal("50")

        # Serialize and restore
        state = original.to_state_dict()
        restored = DCAStrategy.from_state_dict(
            state=state,
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            trigger_drop_percent=Decimal("5"),
            take_profit_percent=Decimal("10"),
        )

        assert restored._last_buy_time == original._last_buy_time
        assert restored._last_price == original._last_price
        assert restored._highest_price == original._highest_price
        assert restored._total_spent == original._total_spent
        assert restored._total_quantity == original._total_quantity
        assert restored.realized_pnl == original.realized_pnl
        assert restored.remaining_budget == original.remaining_budget


class TestDCAGetStats:
    """Tests for get_stats method."""

    def test_get_stats_returns_all_fields(self) -> None:
        """Test that get_stats returns all expected fields."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
            trigger_drop_percent=Decimal("5"),
            take_profit_percent=Decimal("10"),
        )
        strategy._total_spent = Decimal("200")
        strategy._total_quantity = Decimal("0.004")

        stats = strategy.get_stats()

        assert stats["symbol"] == "BTC/USDT"
        assert stats["investment"] == 1000.0
        assert stats["amount_per_buy"] == 100.0
        assert stats["interval"] == "daily"
        assert stats["trigger_drop_percent"] == 5.0
        assert stats["remaining_budget"] == 800.0
        assert stats["average_entry_price"] == 50000.0
        assert stats["total_quantity"] == 0.004
        assert stats["total_spent"] == 200.0


class TestDCAShouldStop:
    """Tests for should_stop method."""

    def test_should_stop_when_budget_exhausted_no_position(self) -> None:
        """Test that strategy stops when budget is gone and no position."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("100"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        # Simulate spending all budget
        strategy._total_spent = Decimal("100")
        strategy._total_quantity = Decimal("0")  # Position sold

        assert strategy.should_stop() is True

    def test_should_not_stop_with_remaining_budget(self) -> None:
        """Test that strategy continues with remaining budget."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("1000"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        strategy._total_spent = Decimal("500")

        assert strategy.should_stop() is False

    def test_should_not_stop_with_position(self) -> None:
        """Test that strategy continues while holding position."""
        strategy = DCAStrategy(
            symbol="BTC/USDT",
            investment=Decimal("100"),
            amount_per_buy=Decimal("100"),
            interval="daily",
        )
        strategy._total_spent = Decimal("100")
        strategy._total_quantity = Decimal("0.002")  # Still holding

        assert strategy.should_stop() is False
