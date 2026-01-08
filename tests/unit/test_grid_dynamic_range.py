"""Tests for dynamic grid range behavior."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bot.strategies.grid import GridStrategy, calculate_atr


def _make_strategy() -> GridStrategy:
    return GridStrategy(
        symbol="BTC/USDT",
        investment=Decimal("100"),
        lower_price=Decimal("90"),
        upper_price=Decimal("110"),
        grid_count=4,
        dynamic_range_enabled=True,
        atr_period=14,
        atr_multiplier=Decimal("1.5"),
        atr_timeframe="1h",
        cooldown_minutes=30,
        recenter_minutes=360,
    )


def test_dynamic_regrid_due_out_of_range() -> None:
    strategy = _make_strategy()
    now = datetime.now(timezone.utc)

    should_regrid, reason = strategy.dynamic_regrid_due(Decimal("120"), now=now)

    assert should_regrid is True
    assert reason == "out_of_range"


def test_dynamic_regrid_due_cooldown_blocks() -> None:
    strategy = _make_strategy()
    now = datetime.now(timezone.utc)
    strategy._last_regrid_at = now - timedelta(minutes=5)

    should_regrid, reason = strategy.dynamic_regrid_due(Decimal("120"), now=now)

    assert should_regrid is False
    assert reason == "cooldown"


def test_compute_dynamic_bounds_uses_atr_multiplier() -> None:
    strategy = _make_strategy()

    lower, upper = strategy.compute_dynamic_bounds(
        current_price=Decimal("100"),
        atr_value=Decimal("10"),
    )

    assert lower == Decimal("85")
    assert upper == Decimal("115")


def test_apply_dynamic_bounds_preserves_positions() -> None:
    strategy = _make_strategy()
    level = strategy._levels[0]
    level.position_qty = Decimal("0.5")
    level.avg_buy_price = Decimal("92")
    total_before = strategy.get_total_position()
    avg_before = strategy.get_average_entry_price()

    strategy.apply_dynamic_bounds(
        lower_price=Decimal("80"),
        upper_price=Decimal("120"),
        now=datetime.now(timezone.utc),
    )

    assert strategy.get_total_position() == total_before
    assert strategy.get_average_entry_price() == avg_before


def test_calculate_atr_basic() -> None:
    ohlcv = [
        [0, 100, 110, 90, 105, 1],
        [1, 105, 115, 95, 110, 1],
        [2, 110, 120, 100, 115, 1],
    ]

    atr_value = calculate_atr(ohlcv, period=2)

    assert atr_value == Decimal("20")
