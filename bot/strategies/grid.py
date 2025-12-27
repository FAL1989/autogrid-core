"""
Grid Trading Strategy

Places buy and sell orders at fixed price intervals within a range.
Profits from sideways market volatility.
"""

from decimal import Decimal

from bot.strategies.base import BaseStrategy, Order


class GridStrategy(BaseStrategy):
    """
    Grid Trading Strategy.

    Creates a grid of buy orders below current price and sell orders above.
    When an order is filled, a new order is placed at the opposite side.

    Example:
        If price range is $40,000 - $48,000 with 20 grids:
        - Grid spacing = ($48,000 - $40,000) / 20 = $400
        - Buy orders at $40,000, $40,400, $40,800, ...
        - Sell orders at $44,400, $44,800, $45,200, ...
    """

    def __init__(
        self,
        symbol: str,
        investment: Decimal,
        lower_price: Decimal,
        upper_price: Decimal,
        grid_count: int,
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

        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grid_count = grid_count

        # Calculate grid parameters
        self.grid_spacing = (upper_price - lower_price) / Decimal(grid_count)
        self.amount_per_grid = investment / Decimal(grid_count)

        # Track grid levels
        self._grid_levels: list[Decimal] = []
        self._initialize_grid_levels()

        # Track active orders per level
        self._level_orders: dict[Decimal, Order | None] = {
            level: None for level in self._grid_levels
        }

    def _initialize_grid_levels(self) -> None:
        """Calculate all grid price levels."""
        for i in range(self.grid_count + 1):
            level = self.lower_price + (self.grid_spacing * Decimal(i))
            self._grid_levels.append(level)

    def calculate_orders(
        self,
        current_price: Decimal,
        open_orders: list[Order],
    ) -> list[Order]:
        """
        Calculate grid orders based on current price.

        Places buy orders below current price and sell orders above.
        """
        new_orders: list[Order] = []

        # Track which levels have open orders
        open_order_prices = {
            order.price for order in open_orders if order.price is not None
        }

        for level in self._grid_levels:
            # Skip if order already exists at this level
            if level in open_order_prices:
                continue

            # Skip if level is exactly at current price
            if level == current_price:
                continue

            # Determine order side based on price relation
            if level < current_price:
                # Place buy order below current price
                order = Order(
                    side="buy",
                    type="limit",
                    price=level,
                    quantity=self._calculate_quantity(level),
                )
                new_orders.append(order)

            elif level > current_price:
                # Place sell order above current price (if we have position)
                # TODO: Check if we have position to sell
                pass

        return new_orders

    def _calculate_quantity(self, price: Decimal) -> Decimal:
        """Calculate order quantity for a given price level."""
        return self.amount_per_grid / price

    def on_order_filled(self, order: Order, fill_price: Decimal) -> None:
        """
        Handle filled order - place opposite order.

        When buy is filled, place sell at next grid level up.
        When sell is filled, place buy at next grid level down.
        """
        self._filled_orders.append(order)

        if order.side == "buy":
            # Calculate profit when we eventually sell
            # Profit = grid_spacing * quantity
            potential_profit = self.grid_spacing * order.quantity
            # Will be realized when corresponding sell order fills
        else:
            # Sell filled - realize profit
            # Find the corresponding buy price
            buy_price = fill_price - self.grid_spacing
            profit = (fill_price - buy_price) * order.quantity
            self.realized_pnl += profit

    def should_stop(self) -> bool:
        """
        Check if strategy should stop.

        Stops if price moves outside the grid range.
        """
        # TODO: Implement stop conditions
        # - Price below lower_price
        # - Price above upper_price
        # - Take profit reached
        # - Stop loss triggered
        return False

    def get_stats(self) -> dict:
        """Get grid strategy statistics."""
        base_stats = super().get_stats()
        base_stats.update({
            "lower_price": float(self.lower_price),
            "upper_price": float(self.upper_price),
            "grid_count": self.grid_count,
            "grid_spacing": float(self.grid_spacing),
            "amount_per_grid": float(self.amount_per_grid),
        })
        return base_stats
