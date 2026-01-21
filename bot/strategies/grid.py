"""
Grid Trading Strategy

Places buy and sell orders at fixed price intervals within a range.
Profits from sideways market volatility.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from bot.strategies.base import BaseStrategy, Order


@dataclass
class GridLevel:
    """
    Represents a single grid level with its state.

    Tracks position and orders at each price level.
    """

    price: Decimal
    index: int
    buy_order_id: UUID | None = None
    sell_order_id: UUID | None = None
    position_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_buy_price: Decimal | None = None

    def has_position(self) -> bool:
        """Check if this level has an open position."""
        return self.position_qty > Decimal("0")


class GridStrategy(BaseStrategy):
    """
    Grid Trading Strategy.

    Creates a grid of buy orders below current price and sell orders above.
    When an order is filled, a new order is placed at the opposite side.

    Flow:
        1. Place BUY orders below current price
        2. When BUY fills → track position at that level
        3. Place SELL order at next grid level up
        4. When SELL fills → realize profit, clear position
        5. Place new BUY at that level again

    Example:
        If price range is $40,000 - $48,000 with 20 grids:
        - Grid spacing = ($48,000 - $40,000) / 20 = $400
        - Buy orders at $40,000, $40,400, $40,800, ...
        - Sell orders placed after buys fill
    """

    def __init__(
        self,
        symbol: str,
        investment: Decimal,
        lower_price: Decimal,
        upper_price: Decimal,
        grid_count: int,
        dynamic_range_enabled: bool = False,
        atr_period: int = 14,
        atr_multiplier: Decimal | None = None,
        atr_timeframe: str = "1h",
        cooldown_minutes: int = 30,
        recenter_minutes: int = 360,
        recenter_position_policy: str = "ignore",
        recenter_min_unrealized_pnl: Decimal | None = None,
        recenter_max_wait_minutes: int = 0,
        min_sell_profit_pct: Decimal | None = None,
    ) -> None:
        """
        Initialize Grid Strategy.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            investment: Total investment amount
            lower_price: Lower price boundary
            upper_price: Upper price boundary
            grid_count: Number of grid lines
        """
        super().__init__(symbol, investment)

        if lower_price >= upper_price:
            raise ValueError("lower_price must be less than upper_price")
        if grid_count < 2:
            raise ValueError("grid_count must be at least 2")
        if atr_period < 2:
            raise ValueError("atr_period must be at least 2")
        if cooldown_minutes < 0:
            raise ValueError("cooldown_minutes must be >= 0")
        if recenter_minutes < 0:
            raise ValueError("recenter_minutes must be >= 0")
        if recenter_max_wait_minutes < 0:
            raise ValueError("recenter_max_wait_minutes must be >= 0")

        if atr_multiplier is None:
            atr_multiplier = Decimal("1.5")
        if atr_multiplier <= 0:
            raise ValueError("atr_multiplier must be > 0")
        if recenter_position_policy not in {
            "ignore",
            "block_any",
            "block_outside_range",
        }:
            raise ValueError("recenter_position_policy must be a valid policy")
        if min_sell_profit_pct is not None and min_sell_profit_pct < 0:
            raise ValueError("min_sell_profit_pct must be >= 0")

        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grid_count = grid_count
        self.dynamic_range_enabled = dynamic_range_enabled
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.atr_timeframe = atr_timeframe
        self.cooldown_minutes = cooldown_minutes
        self.recenter_minutes = recenter_minutes
        self.recenter_position_policy = recenter_position_policy
        self.recenter_min_unrealized_pnl = recenter_min_unrealized_pnl
        self.recenter_max_wait_minutes = recenter_max_wait_minutes
        self.min_sell_profit_pct = min_sell_profit_pct

        # Calculate grid parameters
        self.grid_spacing = (upper_price - lower_price) / Decimal(grid_count)
        self.amount_per_grid = investment / Decimal(grid_count)

        # Grid price levels (indexed 0 to grid_count)
        self._grid_prices: list[Decimal] = []
        self._initialize_grid_prices()

        # Grid level state tracking
        self._levels: dict[int, GridLevel] = {}
        self._initialize_levels()

        # Current price for stop conditions
        self._current_price: Decimal = Decimal("0")
        self._last_regrid_at: datetime | None = None
        self._last_recenter_at: datetime | None = (
            datetime.now(timezone.utc) if dynamic_range_enabled else None
        )

    def _initialize_grid_prices(self) -> None:
        """Calculate all grid price levels."""
        for i in range(self.grid_count + 1):
            price = self.lower_price + (self.grid_spacing * Decimal(i))
            self._grid_prices.append(price)

    def update_investment(self, investment: Decimal) -> None:
        """Update investment and recompute sizing."""
        self.investment = investment
        self.amount_per_grid = investment / Decimal(self.grid_count)

    def _initialize_levels(self) -> None:
        """Initialize grid level tracking."""
        for i, price in enumerate(self._grid_prices):
            self._levels[i] = GridLevel(price=price, index=i)

    def _rebuild_grid(self, lower_price: Decimal, upper_price: Decimal) -> None:
        """Rebuild grid levels and preserve existing positions."""
        previous_levels = list(self._levels.values())

        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grid_spacing = (upper_price - lower_price) / Decimal(self.grid_count)
        self.amount_per_grid = self.investment / Decimal(self.grid_count)

        self._grid_prices = []
        self._initialize_grid_prices()
        self._levels = {}
        self._initialize_levels()

        for level in previous_levels:
            if level.position_qty <= Decimal("0"):
                continue
            anchor_price = level.avg_buy_price or level.price
            target_index = self._find_nearest_level_index(anchor_price)
            target_level = self._levels[target_index]

            total_qty = target_level.position_qty + level.position_qty
            if total_qty > 0:
                target_avg = target_level.avg_buy_price or Decimal("0")
                level_avg = level.avg_buy_price or level.price
                target_level.avg_buy_price = (
                    (target_avg * target_level.position_qty)
                    + (level_avg * level.position_qty)
                ) / total_qty
                target_level.position_qty = total_qty

            target_level.buy_order_id = target_level.buy_order_id or level.buy_order_id
            target_level.sell_order_id = (
                target_level.sell_order_id or level.sell_order_id
            )

    def calculate_orders(
        self,
        current_price: Decimal,
        open_orders: list[Order],
    ) -> list[Order]:
        """
        Calculate grid orders based on current price.

        Places BUY orders below current price.
        Places SELL orders above current price for levels with position.

        Args:
            current_price: Current market price
            open_orders: List of currently open orders

        Returns:
            List of new orders to place
        """
        self._current_price = current_price
        new_orders: list[Order] = []

        # Build set of levels with open orders (by grid_level index)
        open_buy_levels: set[int] = set()
        open_sell_levels: set[int] = set()

        for order in open_orders:
            if order.grid_level is not None:
                if order.side == "buy":
                    open_buy_levels.add(order.grid_level)
                else:
                    open_sell_levels.add(order.grid_level)

        # Process each grid level
        for i, level in self._levels.items():
            price = level.price

            # Skip if level is exactly at current price
            if price == current_price:
                continue

            # BUY orders: below current price, no position, no open buy order
            if price < current_price:
                if not level.has_position() and i not in open_buy_levels:
                    order = Order(
                        side="buy",
                        type="limit",
                        price=price,
                        quantity=self._calculate_quantity(price),
                        grid_level=i,
                    )
                    new_orders.append(order)

            # SELL orders: place at next grid level up for levels with position
            if level.has_position() and i not in open_sell_levels:
                sell_index = i + 1
                if sell_index >= len(self._grid_prices):
                    continue
                sell_price = self._grid_prices[sell_index]
                if (
                    level.avg_buy_price is not None
                    and self.min_sell_profit_pct is not None
                ):
                    min_sell_price = level.avg_buy_price * (
                        Decimal("1") + (self.min_sell_profit_pct / Decimal("100"))
                    )
                    while (
                        sell_index < len(self._grid_prices)
                        and sell_price < min_sell_price
                    ):
                        sell_index += 1
                        if sell_index < len(self._grid_prices):
                            sell_price = self._grid_prices[sell_index]
                    if sell_index >= len(self._grid_prices):
                        continue
                order = Order(
                    side="sell",
                    type="limit",
                    price=sell_price,
                    quantity=level.position_qty,
                    grid_level=i,
                )
                new_orders.append(order)

        return new_orders

    def _calculate_quantity(self, price: Decimal) -> Decimal:
        """Calculate order quantity for a given price level."""
        return self.amount_per_grid / price

    def on_order_filled(self, order: Order, fill_price: Decimal) -> Decimal:
        """
        Handle filled order - update position and calculate P&L.

        When buy is filled:
            - Track position at that grid level
            - Return 0 (no realized P&L yet)

        When sell is filled:
            - Calculate profit based on actual fill prices
            - Clear position at that level
            - Return realized P&L

        Args:
            order: The filled order
            fill_price: Actual fill price from exchange

        Returns:
            Realized P&L from this fill (0 for buys, profit/loss for sells)
        """
        self._filled_orders.append(order)

        # Determine grid level
        level_idx = order.grid_level
        if level_idx is None:
            # Fallback: find level by price
            level_idx = self._find_level_by_price(order.price or fill_price)

        if level_idx is None or level_idx not in self._levels:
            # Unknown level, skip tracking
            return Decimal("0")

        level = self._levels[level_idx]

        if order.side == "buy":
            # Update position at this level
            old_qty = level.position_qty
            old_avg = level.avg_buy_price or Decimal("0")

            # Weighted average for multiple buys at same level
            new_qty = old_qty + order.quantity
            if new_qty > 0:
                level.avg_buy_price = (
                    (old_avg * old_qty) + (fill_price * order.quantity)
                ) / new_qty
            else:
                level.avg_buy_price = fill_price

            level.position_qty = new_qty
            level.buy_order_id = order.id

            return Decimal("0")  # No realized P&L on buys

        else:  # sell
            # Calculate realized P&L
            buy_price = level.avg_buy_price
            if buy_price is None:
                # Fallback: assume bought at grid level below
                buy_price = fill_price - self.grid_spacing

            profit = (fill_price - buy_price) * order.quantity

            # Reduce position at this level (partial fills possible)
            new_qty = level.position_qty - order.quantity
            if new_qty <= Decimal("0"):
                level.position_qty = Decimal("0")
                level.avg_buy_price = None
            else:
                level.position_qty = new_qty
            level.sell_order_id = order.id

            # Accumulate realized P&L
            self.realized_pnl += profit

            return profit

    def _find_level_by_price(self, price: Decimal) -> int | None:
        """Find grid level index by price."""
        for i, level_price in enumerate(self._grid_prices):
            # Allow small tolerance for price matching
            if abs(level_price - price) < self.grid_spacing * Decimal("0.01"):
                return i
        return None

    def _find_nearest_level_index(self, price: Decimal) -> int:
        """Find closest grid level index for a given price."""
        return min(
            range(len(self._grid_prices)),
            key=lambda i: abs(self._grid_prices[i] - price),
        )

    def dynamic_regrid_due(
        self,
        current_price: Decimal,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        """Check whether dynamic grid should recenter or regrid."""
        if not self.dynamic_range_enabled:
            return False, "disabled"

        now = now or datetime.now(timezone.utc)
        if self._last_regrid_at:
            cooldown = timedelta(minutes=self.cooldown_minutes)
            if cooldown > timedelta(0) and (now - self._last_regrid_at) < cooldown:
                return False, "cooldown"

        if current_price < self.lower_price or current_price > self.upper_price:
            return True, "out_of_range"

        if self.recenter_minutes > 0 and self._last_recenter_at:
            recenter_delta = timedelta(minutes=self.recenter_minutes)
            if (now - self._last_recenter_at) >= recenter_delta:
                return True, "recenter"

        return False, "in_range"

    def compute_dynamic_bounds(
        self,
        current_price: Decimal,
        atr_value: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Compute dynamic bounds around current price using ATR."""
        if atr_value <= Decimal("0"):
            raise ValueError("ATR must be > 0")
        half_range = atr_value * self.atr_multiplier
        lower = current_price - half_range
        upper = current_price + half_range
        if lower <= Decimal("0"):
            lower = Decimal("0.00000001")
        if lower >= upper:
            raise ValueError("Computed bounds are invalid")
        return lower, upper

    def apply_dynamic_bounds(
        self,
        lower_price: Decimal,
        upper_price: Decimal,
        now: datetime | None = None,
    ) -> None:
        """Apply new bounds and rebuild grid state."""
        self._rebuild_grid(lower_price, upper_price)
        now = now or datetime.now(timezone.utc)
        self._last_regrid_at = now
        self._last_recenter_at = now

    def can_recenter_pre_atr(
        self,
        current_price: Decimal,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        """Check recenter gates that do not require dynamic bounds."""
        now = now or datetime.now(timezone.utc)
        total_position = self.get_total_position()
        if self.recenter_position_policy == "block_any" and total_position > 0:
            return False, "position_open"
        if self.recenter_min_unrealized_pnl is None:
            return True, "ok"
        if self.recenter_max_wait_minutes > 0 and self._last_recenter_at:
            max_wait = timedelta(minutes=self.recenter_max_wait_minutes)
            if (now - self._last_recenter_at) >= max_wait:
                return True, "max_wait_elapsed"
        if total_position <= 0:
            return True, "no_position"
        unrealized = self.get_unrealized_pnl(current_price)
        if unrealized >= self.recenter_min_unrealized_pnl:
            return True, "pnl_ok"
        return False, "pnl_below_threshold"

    def can_recenter_with_bounds(
        self,
        lower_price: Decimal,
        upper_price: Decimal,
    ) -> tuple[bool, str]:
        """Check recenter gates that require computed bounds."""
        if self.recenter_position_policy != "block_outside_range":
            return True, "ok"
        for level in self._levels.values():
            if not level.has_position():
                continue
            anchor_price = level.avg_buy_price or level.price
            if anchor_price < lower_price or anchor_price > upper_price:
                return False, "position_outside_range"
        return True, "ok"

    def should_stop(self) -> bool:
        """
        Check if strategy should stop.

        Stops if price moves significantly outside the grid range:
        - 5% below lower_price
        - 5% above upper_price
        """
        if self._current_price <= Decimal("0"):
            return False  # Not yet initialized

        # Stop if price drops 5% below lower bound
        stop_lower = self.lower_price * Decimal("0.95")
        if self._current_price < stop_lower:
            return True

        # Stop if price rises 5% above upper bound
        stop_upper = self.upper_price * Decimal("1.05")
        if self._current_price > stop_upper:
            return True

        return False

    def get_total_position(self) -> Decimal:
        """Get total position across all grid levels."""
        return sum(
            (level.position_qty for level in self._levels.values()),
            Decimal("0"),
        )

    def get_average_entry_price(self) -> Decimal:
        """Get weighted average entry price for current position."""
        total_qty = Decimal("0")
        total_value = Decimal("0")

        for level in self._levels.values():
            if level.has_position() and level.avg_buy_price:
                total_qty += level.position_qty
                total_value += level.position_qty * level.avg_buy_price

        if total_qty > 0:
            return total_value / total_qty
        return Decimal("0")

    def get_unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """
        Calculate unrealized P&L for open positions.

        Args:
            current_price: Current market price

        Returns:
            Unrealized profit/loss
        """
        unrealized = Decimal("0")

        for level in self._levels.values():
            if level.has_position() and level.avg_buy_price:
                pnl = (current_price - level.avg_buy_price) * level.position_qty
                unrealized += pnl

        return unrealized

    def get_level_states(self) -> list[dict]:
        """Get state of all grid levels for debugging/monitoring."""
        return [
            {
                "index": level.index,
                "price": float(level.price),
                "position_qty": float(level.position_qty),
                "avg_buy_price": (
                    float(level.avg_buy_price) if level.avg_buy_price else None
                ),
                "has_position": level.has_position(),
            }
            for level in self._levels.values()
        ]

    def get_stats(self) -> dict:
        """Get grid strategy statistics."""
        base_stats = super().get_stats()
        base_stats.update(
            {
                "lower_price": float(self.lower_price),
                "upper_price": float(self.upper_price),
                "grid_count": self.grid_count,
                "grid_spacing": float(self.grid_spacing),
                "amount_per_grid": float(self.amount_per_grid),
                "total_position": float(self.get_total_position()),
                "average_entry_price": float(self.get_average_entry_price()),
                "unrealized_pnl": float(self.get_unrealized_pnl(self._current_price)),
                "levels_with_position": sum(
                    1 for level in self._levels.values() if level.has_position()
                ),
                "dynamic_range_enabled": self.dynamic_range_enabled,
                "atr_period": self.atr_period,
                "atr_multiplier": float(self.atr_multiplier),
                "atr_timeframe": self.atr_timeframe,
                "cooldown_minutes": self.cooldown_minutes,
                "recenter_minutes": self.recenter_minutes,
                "recenter_position_policy": self.recenter_position_policy,
                "recenter_min_unrealized_pnl": (
                    float(self.recenter_min_unrealized_pnl)
                    if self.recenter_min_unrealized_pnl is not None
                    else None
                ),
                "recenter_max_wait_minutes": self.recenter_max_wait_minutes,
                "min_sell_profit_pct": (
                    float(self.min_sell_profit_pct)
                    if self.min_sell_profit_pct is not None
                    else None
                ),
            }
        )
        return base_stats


def calculate_atr(ohlcv: list[list], period: int) -> Decimal:
    """Calculate ATR from OHLCV data."""
    if period < 2:
        raise ValueError("period must be at least 2")
    if len(ohlcv) < period + 1:
        raise ValueError("Not enough candles for ATR")

    true_ranges: list[Decimal] = []
    prev_close = Decimal(str(ohlcv[0][4]))

    for candle in ohlcv[1:]:
        high = Decimal(str(candle[2]))
        low = Decimal(str(candle[3]))
        close = Decimal(str(candle[4]))
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(tr)
        prev_close = close

    if len(true_ranges) < period:
        raise ValueError("Not enough true range values")

    return sum(true_ranges[-period:]) / Decimal(period)
