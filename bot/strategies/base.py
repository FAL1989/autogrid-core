"""
Base Strategy

Abstract base class for all trading strategies.
Implements the Strategy Pattern for interchangeable trading algorithms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4


@dataclass
class Order:
    """
    Trading order representation.

    Attributes:
        id: Unique order identifier
        side: 'buy' or 'sell'
        type: 'limit' or 'market'
        price: Order price (None for market orders)
        quantity: Order quantity
        status: Current order status
        exchange_id: ID from the exchange after placement
        grid_level: Index of grid level (for grid strategies)
    """

    side: Literal["buy", "sell"]
    type: Literal["limit", "market"]
    quantity: Decimal
    price: Decimal | None = None
    id: UUID = field(default_factory=uuid4)
    status: Literal["pending", "open", "filled", "cancelled", "error"] = "pending"
    exchange_id: str | None = None
    grid_level: int | None = None  # Grid level index for position tracking

    def __repr__(self) -> str:
        return (
            f"Order(side={self.side}, type={self.type}, "
            f"price={self.price}, qty={self.quantity}, status={self.status})"
        )


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    All strategies must implement:
    - calculate_orders: Generate orders based on market data
    - on_order_filled: Handle filled order events
    - should_stop: Check if strategy should terminate

    Example:
        class MyStrategy(BaseStrategy):
            def calculate_orders(self, current_price, open_orders):
                # Your logic here
                return [Order(...)]
    """

    def __init__(self, symbol: str, investment: Decimal) -> None:
        """
        Initialize strategy.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            investment: Total investment amount
        """
        self.symbol = symbol
        self.investment = investment
        self.realized_pnl = Decimal("0")
        self._filled_orders: list[Order] = []

    @abstractmethod
    def calculate_orders(
        self,
        current_price: Decimal,
        open_orders: list[Order],
    ) -> list[Order]:
        """
        Calculate new orders based on current market state.

        Args:
            current_price: Current market price
            open_orders: List of currently open orders

        Returns:
            List of new orders to place
        """
        pass

    @abstractmethod
    def on_order_filled(self, order: Order, fill_price: Decimal) -> None:
        """
        Handle a filled order.

        Update internal state, calculate P&L, and prepare for next orders.

        Args:
            order: The filled order
            fill_price: Actual fill price
        """
        pass

    @abstractmethod
    def should_stop(self) -> bool:
        """
        Check if strategy should stop.

        Returns:
            True if strategy should terminate
        """
        pass

    def get_realized_pnl(self) -> Decimal:
        """Get total realized profit/loss."""
        return self.realized_pnl

    def get_stats(self) -> dict:
        """Get strategy statistics."""
        return {
            "symbol": self.symbol,
            "investment": float(self.investment),
            "realized_pnl": float(self.realized_pnl),
            "total_filled_orders": len(self._filled_orders),
        }
