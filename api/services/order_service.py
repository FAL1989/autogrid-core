"""
Order Service.

Business logic for order operations including CRUD and status management.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import Order, Trade, Bot


class OrderService:
    """Service for order-related operations."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize OrderService.

        Args:
            db: Async database session.
        """
        self.db = db

    async def get_by_id(self, order_id: UUID) -> Order | None:
        """
        Get order by ID.

        Args:
            order_id: The order's UUID.

        Returns:
            Order if found, None otherwise.
        """
        result = await self.db.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(
        self,
        order_id: UUID,
        user_id: UUID,
    ) -> Order | None:
        """
        Get order by ID, ensuring it belongs to a bot owned by the user.

        Args:
            order_id: The order's UUID.
            user_id: The owner's UUID.

        Returns:
            Order if found and owned by user, None otherwise.
        """
        result = await self.db.execute(
            select(Order)
            .join(Bot, Order.bot_id == Bot.id)
            .where(Order.id == order_id, Bot.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_bot(
        self,
        bot_id: UUID,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        """
        List all orders for a bot with pagination.

        Args:
            bot_id: The bot's UUID.
            status: Optional status filter.
            limit: Maximum number of orders to return.
            offset: Number of orders to skip.

        Returns:
            Tuple of (list of orders, total count).
        """
        # Base query
        query = select(Order).where(Order.bot_id == bot_id)
        count_query = select(func.count()).select_from(Order).where(Order.bot_id == bot_id)

        if status:
            query = query.where(Order.status == status)
            count_query = count_query.where(Order.status == status)

        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated orders
        result = await self.db.execute(
            query
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        orders = list(result.scalars().all())

        return orders, total

    async def get_open_orders(self, bot_id: UUID) -> list[Order]:
        """
        Get all open orders for a bot.

        Args:
            bot_id: The bot's UUID.

        Returns:
            List of open orders.
        """
        result = await self.db.execute(
            select(Order).where(
                Order.bot_id == bot_id,
                Order.status.in_(["open", "partially_filled"]),
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        bot_id: UUID,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        exchange_order_id: str | None = None,
    ) -> Order:
        """
        Create a new order.

        Args:
            bot_id: Bot's UUID.
            symbol: Trading pair (e.g., 'BTC/USDT').
            side: Order side ('buy' or 'sell').
            order_type: Order type ('limit' or 'market').
            quantity: Order quantity.
            price: Order price (required for limit orders).
            exchange_order_id: Exchange-assigned order ID.

        Returns:
            The created Order object.
        """
        order = Order(
            bot_id=bot_id,
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=quantity,
            price=price,
            exchange_order_id=exchange_order_id,
            status="pending",
            filled_quantity=Decimal("0"),
        )
        self.db.add(order)
        await self.db.flush()
        await self.db.refresh(order)
        return order

    async def update_status(
        self,
        order_id: UUID,
        status: str,
        filled_quantity: Decimal | None = None,
        average_fill_price: Decimal | None = None,
        exchange_order_id: str | None = None,
    ) -> Order | None:
        """
        Update order status.

        Args:
            order_id: The order's UUID.
            status: New status.
            filled_quantity: Filled amount.
            average_fill_price: Average fill price.
            exchange_order_id: Exchange order ID.

        Returns:
            Updated order or None if not found.
        """
        order = await self.get_by_id(order_id)

        if order is None:
            return None

        order.status = status
        if filled_quantity is not None:
            order.filled_quantity = filled_quantity
        if average_fill_price is not None:
            order.average_fill_price = average_fill_price
        if exchange_order_id is not None:
            order.exchange_order_id = exchange_order_id
        if status == "filled":
            order.filled_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(order)
        return order

    async def cancel_order(self, order_id: UUID, user_id: UUID) -> bool:
        """
        Cancel an order.

        Args:
            order_id: The order's UUID.
            user_id: The owner's UUID (for verification).

        Returns:
            True if cancelled, False if not found or not cancellable.
        """
        order = await self.get_by_id_for_user(order_id, user_id)

        if order is None:
            return False

        if order.status not in ("pending", "open", "partially_filled"):
            return False

        order.status = "cancelled"
        await self.db.flush()
        return True

    # =========================================================================
    # Trade Methods
    # =========================================================================

    async def list_trades_by_bot(
        self,
        bot_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Trade], int]:
        """
        List all trades for a bot with pagination.

        Args:
            bot_id: The bot's UUID.
            limit: Maximum number of trades to return.
            offset: Number of trades to skip.

        Returns:
            Tuple of (list of trades, total count).
        """
        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(Trade).where(Trade.bot_id == bot_id)
        )
        total = count_result.scalar() or 0

        # Get paginated trades
        result = await self.db.execute(
            select(Trade)
            .where(Trade.bot_id == bot_id)
            .order_by(Trade.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        trades = list(result.scalars().all())

        return trades, total

    async def create_trade(
        self,
        bot_id: UUID,
        order_id: UUID | None,
        symbol: str,
        side: str,
        price: Decimal,
        quantity: Decimal,
        fee: Decimal = Decimal("0"),
        fee_currency: str | None = None,
        realized_pnl: Decimal | None = None,
    ) -> Trade:
        """
        Create a trade record.

        Args:
            bot_id: Bot's UUID.
            order_id: Associated order's UUID.
            symbol: Trading pair.
            side: Trade side ('buy' or 'sell').
            price: Execution price.
            quantity: Executed quantity.
            fee: Trading fee.
            fee_currency: Fee currency.
            realized_pnl: Realized P&L (if closing position).

        Returns:
            The created Trade object.
        """
        trade = Trade(
            bot_id=bot_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            fee=fee,
            fee_currency=fee_currency,
            realized_pnl=realized_pnl,
        )
        self.db.add(trade)
        await self.db.flush()
        await self.db.refresh(trade)
        return trade

    async def get_bot_statistics(self, bot_id: UUID) -> dict:
        """
        Get order and trade statistics for a bot.

        Args:
            bot_id: The bot's UUID.

        Returns:
            Dict with statistics.
        """
        # Order counts by status
        order_stats = await self.db.execute(
            select(
                Order.status,
                func.count().label("count"),
            )
            .where(Order.bot_id == bot_id)
            .group_by(Order.status)
        )
        order_counts = {row[0]: row[1] for row in order_stats.all()}

        # Trade statistics
        trade_stats = await self.db.execute(
            select(
                func.count().label("total_trades"),
                func.sum(Trade.quantity).label("total_volume"),
                func.sum(Trade.fee).label("total_fees"),
                func.sum(Trade.realized_pnl).label("total_pnl"),
            ).where(Trade.bot_id == bot_id)
        )
        trade_row = trade_stats.one()

        return {
            "orders": {
                "total": sum(order_counts.values()),
                "by_status": order_counts,
            },
            "trades": {
                "total": trade_row[0] or 0,
                "total_volume": float(trade_row[1] or 0),
                "total_fees": float(trade_row[2] or 0),
                "total_pnl": float(trade_row[3] or 0),
            },
        }
