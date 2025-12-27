"""
DCA (Dollar Cost Averaging) Strategy

Buys at regular intervals or on price drops to reduce average entry price.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from bot.strategies.base import BaseStrategy, Order


class DCAStrategy(BaseStrategy):
    """
    Dollar Cost Averaging Strategy.

    Supports two modes:
    1. Time-based: Buy at regular intervals (hourly, daily, weekly)
    2. Price-drop: Buy when price drops by X%

    Can also combine both modes (hybrid).
    """

    def __init__(
        self,
        symbol: str,
        investment: Decimal,
        amount_per_buy: Decimal,
        interval: Literal["hourly", "daily", "weekly"] | None = None,
        trigger_drop_percent: Decimal | None = None,
        take_profit_percent: Decimal | None = None,
    ) -> None:
        """
        Initialize DCA Strategy.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            investment: Total budget for DCA
            amount_per_buy: Amount to buy each time
            interval: Time interval for buys (None to disable)
            trigger_drop_percent: Price drop % to trigger extra buy (None to disable)
            take_profit_percent: Sell all when profit reaches this % (None to disable)
        """
        super().__init__(symbol, investment)

        self.amount_per_buy = amount_per_buy
        self.interval = interval
        self.trigger_drop_percent = trigger_drop_percent
        self.take_profit_percent = take_profit_percent

        # Track state
        self._last_buy_time: datetime | None = None
        self._last_price: Decimal | None = None
        self._highest_price: Decimal | None = None
        self._total_spent = Decimal("0")
        self._total_quantity = Decimal("0")
        self._average_price = Decimal("0")

    @property
    def remaining_budget(self) -> Decimal:
        """Calculate remaining DCA budget."""
        return self.investment - self._total_spent

    @property
    def average_entry_price(self) -> Decimal:
        """Calculate average entry price."""
        if self._total_quantity == 0:
            return Decimal("0")
        return self._total_spent / self._total_quantity

    def calculate_orders(
        self,
        current_price: Decimal,
        open_orders: list[Order],
    ) -> list[Order]:
        """
        Calculate DCA orders based on time or price triggers.
        """
        new_orders: list[Order] = []

        # Check if we have budget left
        if self.remaining_budget < self.amount_per_buy:
            return new_orders

        # Check for take profit
        if self._should_take_profit(current_price):
            return self._create_sell_all_order(current_price)

        # Check time-based trigger
        if self._should_buy_by_time():
            order = self._create_buy_order(current_price)
            new_orders.append(order)

        # Check price-drop trigger
        elif self._should_buy_by_drop(current_price):
            order = self._create_buy_order(current_price)
            new_orders.append(order)

        # Update price tracking
        self._update_price_tracking(current_price)

        return new_orders

    def _should_buy_by_time(self) -> bool:
        """Check if enough time has passed for scheduled buy."""
        if self.interval is None:
            return False

        if self._last_buy_time is None:
            return True

        now = datetime.utcnow()
        intervals = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(weeks=1),
        }

        return now - self._last_buy_time >= intervals[self.interval]

    def _should_buy_by_drop(self, current_price: Decimal) -> bool:
        """Check if price dropped enough to trigger buy."""
        if self.trigger_drop_percent is None:
            return False

        if self._highest_price is None:
            return False

        drop_percent = (self._highest_price - current_price) / self._highest_price * 100
        return drop_percent >= self.trigger_drop_percent

    def _should_take_profit(self, current_price: Decimal) -> bool:
        """Check if take profit target is reached."""
        if self.take_profit_percent is None:
            return False

        if self._total_quantity == 0:
            return False

        profit_percent = (current_price - self.average_entry_price) / self.average_entry_price * 100
        return profit_percent >= self.take_profit_percent

    def _create_buy_order(self, price: Decimal) -> Order:
        """Create a buy order."""
        quantity = self.amount_per_buy / price
        return Order(
            side="buy",
            type="market",
            price=price,
            quantity=quantity,
        )

    def _create_sell_all_order(self, price: Decimal) -> list[Order]:
        """Create order to sell entire position."""
        if self._total_quantity == 0:
            return []

        return [
            Order(
                side="sell",
                type="market",
                price=price,
                quantity=self._total_quantity,
            )
        ]

    def _update_price_tracking(self, current_price: Decimal) -> None:
        """Update price tracking for drop detection."""
        if self._highest_price is None or current_price > self._highest_price:
            self._highest_price = current_price
        self._last_price = current_price

    def on_order_filled(self, order: Order, fill_price: Decimal) -> None:
        """Handle filled order."""
        self._filled_orders.append(order)

        if order.side == "buy":
            self._total_spent += fill_price * order.quantity
            self._total_quantity += order.quantity
            self._last_buy_time = datetime.utcnow()
            # Reset highest price after buy
            self._highest_price = fill_price

        else:  # sell
            # Calculate realized P&L
            cost_basis = self.average_entry_price * order.quantity
            proceeds = fill_price * order.quantity
            self.realized_pnl += proceeds - cost_basis

            # Reset position
            self._total_quantity = Decimal("0")
            self._total_spent = Decimal("0")
            self._highest_price = None

    def should_stop(self) -> bool:
        """
        Check if strategy should stop.

        Stops when:
        - Budget exhausted and no position
        - Position sold (take profit hit)
        """
        return (
            self.remaining_budget < self.amount_per_buy
            and self._total_quantity == 0
        )

    def get_stats(self) -> dict:
        """Get DCA strategy statistics."""
        base_stats = super().get_stats()
        base_stats.update({
            "amount_per_buy": float(self.amount_per_buy),
            "interval": self.interval,
            "trigger_drop_percent": float(self.trigger_drop_percent) if self.trigger_drop_percent else None,
            "remaining_budget": float(self.remaining_budget),
            "average_entry_price": float(self.average_entry_price),
            "total_quantity": float(self._total_quantity),
            "total_spent": float(self._total_spent),
        })
        return base_stats
