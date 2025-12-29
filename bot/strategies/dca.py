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

        Raises:
            ValueError: If parameters are invalid.
        """
        # Validate parameters before calling super().__init__
        if investment <= 0:
            raise ValueError("investment must be positive")
        if amount_per_buy <= 0:
            raise ValueError("amount_per_buy must be positive")
        if amount_per_buy > investment:
            raise ValueError("amount_per_buy cannot exceed investment")
        if trigger_drop_percent is not None and not (Decimal("0") < trigger_drop_percent <= Decimal("100")):
            raise ValueError("trigger_drop_percent must be between 0 and 100")
        if take_profit_percent is not None and take_profit_percent <= 0:
            raise ValueError("take_profit_percent must be positive")
        if interval is None and trigger_drop_percent is None:
            raise ValueError("At least one trigger (interval or trigger_drop) required")

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

        # Check for take profit FIRST (can sell even with no budget)
        if self._should_take_profit(current_price):
            return self._create_sell_all_order(current_price)

        # Check if we have budget left (only needed for buying)
        if self.remaining_budget < self.amount_per_buy:
            return new_orders

        # Check time-based trigger
        if self._should_buy_by_time():
            order = self._create_buy_order(current_price)
            new_orders.append(order)

        # Check price-drop trigger (independent, but avoid duplicate buy)
        if self._should_buy_by_drop(current_price):
            if not any(o.side == "buy" for o in new_orders):
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

    def on_order_filled(self, order: Order, fill_price: Decimal) -> Decimal:
        """
        Handle filled order.

        Args:
            order: The filled order.
            fill_price: The actual fill price.

        Returns:
            Realized P&L from this fill (0 for buys, profit/loss for sells).
        """
        self._filled_orders.append(order)
        realized_pnl = Decimal("0")

        if order.side == "buy":
            self._total_spent += fill_price * order.quantity
            self._total_quantity += order.quantity
            self._last_buy_time = datetime.utcnow()
            # Note: Don't reset _highest_price here to allow drop detection to work properly

        else:  # sell
            # Calculate realized P&L
            cost_basis = self.average_entry_price * order.quantity
            proceeds = fill_price * order.quantity
            realized_pnl = proceeds - cost_basis
            self.realized_pnl += realized_pnl

            # Reset position
            self._total_quantity = Decimal("0")
            self._total_spent = Decimal("0")
            self._highest_price = None

        return realized_pnl

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

    def to_state_dict(self) -> dict:
        """
        Export strategy state for persistence.

        Returns:
            Dictionary with serializable state values.
        """
        return {
            "last_buy_time": self._last_buy_time.isoformat() if self._last_buy_time else None,
            "last_price": str(self._last_price) if self._last_price else None,
            "highest_price": str(self._highest_price) if self._highest_price else None,
            "total_spent": str(self._total_spent),
            "total_quantity": str(self._total_quantity),
            "realized_pnl": str(self.realized_pnl),
        }

    @classmethod
    def from_state_dict(
        cls,
        state: dict,
        symbol: str,
        investment: Decimal,
        amount_per_buy: Decimal,
        interval: Literal["hourly", "daily", "weekly"] | None = None,
        trigger_drop_percent: Decimal | None = None,
        take_profit_percent: Decimal | None = None,
    ) -> "DCAStrategy":
        """
        Restore strategy from persisted state.

        Args:
            state: Previously persisted state dict.
            symbol: Trading pair.
            investment: Total budget.
            amount_per_buy: Amount per buy.
            interval: Time interval for buys.
            trigger_drop_percent: Price drop trigger %.
            take_profit_percent: Take profit %.

        Returns:
            DCAStrategy instance with restored state.
        """
        strategy = cls(
            symbol=symbol,
            investment=investment,
            amount_per_buy=amount_per_buy,
            interval=interval,
            trigger_drop_percent=trigger_drop_percent,
            take_profit_percent=take_profit_percent,
        )

        # Restore state
        if state.get("last_buy_time"):
            strategy._last_buy_time = datetime.fromisoformat(state["last_buy_time"])
        if state.get("last_price"):
            strategy._last_price = Decimal(state["last_price"])
        if state.get("highest_price"):
            strategy._highest_price = Decimal(state["highest_price"])
        strategy._total_spent = Decimal(state.get("total_spent", "0"))
        strategy._total_quantity = Decimal(state.get("total_quantity", "0"))
        strategy.realized_pnl = Decimal(state.get("realized_pnl", "0"))

        return strategy
