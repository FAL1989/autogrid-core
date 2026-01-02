"""
Order Manager

Manages order lifecycle with state machine, retry logic, and persistence.
Provides a robust layer between the bot engine and exchange connector.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import Order as OrderORM
from bot.exchange.connector import ExchangeConnector

logger = logging.getLogger(__name__)


class OrderState(Enum):
    """
    Order lifecycle states.

    State machine transitions:
    PENDING -> SUBMITTING -> OPEN -> PARTIALLY_FILLED -> FILLED
                    |-> REJECTED
                    |-> ERROR
    OPEN -> CANCELLING -> CANCELLED
         |-> FILLED
         |-> PARTIALLY_FILLED
         |-> ERROR
    """

    PENDING = "pending"
    SUBMITTING = "submitting"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


# Valid state transitions
ORDER_TRANSITIONS: dict[OrderState, list[OrderState]] = {
    OrderState.PENDING: [OrderState.SUBMITTING, OrderState.CANCELLED],
    OrderState.SUBMITTING: [OrderState.OPEN, OrderState.REJECTED, OrderState.ERROR],
    OrderState.OPEN: [
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELLING,
        OrderState.ERROR,
    ],
    OrderState.PARTIALLY_FILLED: [
        OrderState.FILLED,
        OrderState.CANCELLING,
        OrderState.ERROR,
    ],
    OrderState.CANCELLING: [OrderState.CANCELLED, OrderState.FILLED, OrderState.ERROR],
    # Terminal states - no transitions allowed
    OrderState.FILLED: [],
    OrderState.CANCELLED: [],
    OrderState.REJECTED: [],
    OrderState.ERROR: [],
}


class OrderTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: OrderState, target_state: OrderState):
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            f"Invalid transition from {current_state.value} to {target_state.value}"
        )


@dataclass
class ManagedOrder:
    """
    Order managed by OrderManager with full lifecycle tracking.

    Attributes:
        id: Internal order ID (UUID)
        bot_id: Bot that owns this order
        symbol: Trading pair (e.g., 'BTC/USDT')
        side: 'buy' or 'sell'
        order_type: 'limit' or 'market'
        quantity: Order quantity
        price: Order price (None for market orders)
        state: Current order state
        exchange_id: Exchange-assigned order ID
        filled_quantity: Amount filled so far
        average_fill_price: Weighted average fill price
        retry_count: Number of submission retries
        max_retries: Maximum retry attempts
        last_error: Last error message
        created_at: Order creation timestamp
        submitted_at: When order was sent to exchange
        filled_at: When order was completely filled
        updated_at: Last update timestamp
    """

    bot_id: UUID
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'limit' or 'market'
    quantity: Decimal
    price: Decimal | None = None
    id: UUID = field(default_factory=uuid4)
    state: OrderState = OrderState.PENDING
    exchange_id: str | None = None
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    fee: Decimal = Decimal("0")
    fee_asset: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    last_error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    grid_level: int | None = None  # Grid level index for grid strategies

    @property
    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.state in (
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.ERROR,
        )

    @property
    def is_active(self) -> bool:
        """Check if order is actively in the market."""
        return self.state in (OrderState.OPEN, OrderState.PARTIALLY_FILLED)

    @property
    def remaining_quantity(self) -> Decimal:
        """Get unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def fill_percent(self) -> Decimal:
        """Get fill percentage (0-100)."""
        if self.quantity == 0:
            return Decimal("0")
        return (self.filled_quantity / self.quantity) * 100

    def can_transition_to(self, new_state: OrderState) -> bool:
        """Check if transition to new_state is valid."""
        return new_state in ORDER_TRANSITIONS.get(self.state, [])

    def __repr__(self) -> str:
        return (
            f"ManagedOrder(id={self.id}, {self.side} {self.quantity} {self.symbol} "
            f"@ {self.price}, state={self.state.value})"
        )


class OrderManager:
    """
    Manages order lifecycle with state machine, retry, and persistence.

    Features:
    - State machine with validated transitions
    - Retry with exponential backoff
    - Database persistence
    - WebSocket update handling
    - Order synchronization with exchange
    """

    def __init__(
        self,
        exchange: ExchangeConnector,
        db_session: AsyncSession,
        on_order_filled: Callable[[ManagedOrder], None] | None = None,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 30.0,
    ) -> None:
        """
        Initialize OrderManager.

        Args:
            exchange: Exchange connector for order operations
            db_session: Database session for persistence
            on_order_filled: Callback when order fills
            base_retry_delay: Base delay for exponential backoff (seconds)
            max_retry_delay: Maximum retry delay (seconds)
        """
        self.exchange = exchange
        self.db_session = db_session
        self.on_order_filled = on_order_filled
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay

        # In-memory order cache (keyed by order ID)
        self._orders: dict[UUID, ManagedOrder] = {}
        # Exchange ID to internal ID mapping
        self._exchange_id_map: dict[str, UUID] = {}
        # Bot ID to user ID cache for WebSocket broadcasts
        self._bot_user_cache: dict[UUID, UUID] = {}

    async def submit_order(self, order: ManagedOrder) -> ManagedOrder:
        """
        Submit order to exchange with retry logic.

        Args:
            order: Order to submit

        Returns:
            Updated order with exchange ID and state

        Raises:
            OrderTransitionError: If order cannot be submitted from current state
        """
        if not order.can_transition_to(OrderState.SUBMITTING):
            raise OrderTransitionError(order.state, OrderState.SUBMITTING)

        self._transition_state(order, OrderState.SUBMITTING)
        order.submitted_at = datetime.now(timezone.utc)

        try:
            result = await self._retry_with_backoff(
                self._submit_to_exchange,
                order,
            )

            order.exchange_id = result.get("id")
            if order.exchange_id:
                self._exchange_id_map[order.exchange_id] = order.id

            # Update state based on exchange response
            status = result.get("status", "open")
            if status == "open":
                self._transition_state(order, OrderState.OPEN)
            elif status == "closed":
                self._transition_state(order, OrderState.FILLED)
                order.filled_quantity = order.quantity
                order.filled_at = datetime.now(timezone.utc)
            elif status == "canceled":
                self._transition_state(order, OrderState.CANCELLED)

            # Cache and persist
            self._orders[order.id] = order
            await self._persist_order(order)

            logger.info(
                f"Order submitted: {order.id} -> exchange_id={order.exchange_id}"
            )
            return order

        except Exception as e:
            order.last_error = str(e)
            self._transition_state(order, OrderState.ERROR)
            await self._persist_order(order)
            logger.error(f"Order submission failed: {order.id} - {e}")
            raise

    async def cancel_order(self, order_id: UUID) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Internal order ID

        Returns:
            True if cancelled successfully
        """
        order = self._orders.get(order_id)
        if not order:
            logger.warning(f"Order not found for cancellation: {order_id}")
            return False

        if not order.can_transition_to(OrderState.CANCELLING):
            logger.warning(
                f"Cannot cancel order {order_id} in state {order.state.value}"
            )
            return False

        self._transition_state(order, OrderState.CANCELLING)

        try:
            if order.exchange_id:
                success = await self.exchange.cancel_order(
                    order.exchange_id, order.symbol
                )
                if success:
                    self._transition_state(order, OrderState.CANCELLED)
                    await self._persist_order(order)
                    logger.info(f"Order cancelled: {order_id}")
                    return True

            # No exchange_id means order never reached exchange
            self._transition_state(order, OrderState.CANCELLED)
            await self._persist_order(order)
            return True

        except Exception as e:
            order.last_error = str(e)
            self._transition_state(order, OrderState.ERROR)
            await self._persist_order(order)
            logger.error(f"Order cancellation failed: {order_id} - {e}")
            return False

    async def sync_order_status(self, order_id: UUID) -> ManagedOrder | None:
        """
        Synchronize order status with exchange.

        Fetches latest order state from exchange and updates local state.

        Args:
            order_id: Internal order ID

        Returns:
            Updated order or None if not found
        """
        order = self._orders.get(order_id)
        if not order or not order.exchange_id:
            return None

        try:
            result = await self.exchange.fetch_order(order.exchange_id, order.symbol)
            await self._process_exchange_update(order, result)
            return order

        except Exception as e:
            logger.error(f"Failed to sync order {order_id}: {e}")
            return order

    async def handle_websocket_update(self, data: dict[str, Any]) -> None:
        """
        Handle WebSocket order update from exchange.

        Args:
            data: WebSocket message with order update
        """
        exchange_id = data.get("orderId") or data.get("i") or data.get("id")
        if not exchange_id:
            logger.debug(f"WebSocket update missing order ID: {data}")
            return

        exchange_id = str(exchange_id)
        order_id = self._exchange_id_map.get(exchange_id)
        if not order_id:
            logger.debug(f"Unknown exchange order: {exchange_id}")
            return

        order = self._orders.get(order_id)
        if not order:
            return

        await self._process_exchange_update(order, data)

    async def get_order(self, order_id: UUID) -> ManagedOrder | None:
        """Get order by internal ID."""
        return self._orders.get(order_id)

    async def get_open_orders(self, bot_id: UUID | None = None) -> list[ManagedOrder]:
        """
        Get all active orders.

        Args:
            bot_id: Optional filter by bot ID

        Returns:
            List of active orders
        """
        orders = [o for o in self._orders.values() if o.is_active]
        if bot_id:
            orders = [o for o in orders if o.bot_id == bot_id]
        return orders

    def has_active_grid_order(
        self,
        bot_id: UUID,
        side: str,
        grid_level: int,
    ) -> bool:
        """Check for an active order on the same grid level."""
        for order in self._orders.values():
            if (
                order.bot_id == bot_id
                and order.side == side
                and order.grid_level == grid_level
                and order.state
                in (
                    OrderState.PENDING,
                    OrderState.SUBMITTING,
                    OrderState.OPEN,
                    OrderState.PARTIALLY_FILLED,
                )
            ):
                return True
        return False

    async def get_orders_by_bot(
        self,
        bot_id: UUID,
        states: list[OrderState] | None = None,
    ) -> list[ManagedOrder]:
        """
        Get all orders for a bot.

        Args:
            bot_id: Bot ID to filter by
            states: Optional list of states to filter by

        Returns:
            List of matching orders
        """
        orders = [o for o in self._orders.values() if o.bot_id == bot_id]
        if states:
            orders = [o for o in orders if o.state in states]
        return orders

    async def cancel_all_orders(self, bot_id: UUID) -> int:
        """
        Cancel all active orders for a bot.

        Args:
            bot_id: Bot ID

        Returns:
            Number of orders cancelled
        """
        orders = await self.get_orders_by_bot(
            bot_id,
            states=[OrderState.OPEN, OrderState.PARTIALLY_FILLED],
        )

        cancelled = 0
        for order in orders:
            if await self.cancel_order(order.id):
                cancelled += 1

        return cancelled

    async def load_orders_from_db(self, bot_id: UUID) -> list[ManagedOrder]:
        """
        Load orders from database into memory.

        Args:
            bot_id: Bot ID to load orders for

        Returns:
            List of loaded orders
        """
        stmt = select(OrderORM).where(
            OrderORM.bot_id == bot_id,
            OrderORM.status.in_(["open", "partially_filled", "pending", "submitting"]),
        )
        result = await self.db_session.execute(stmt)
        db_orders = result.scalars().all()

        loaded = []
        for db_order in db_orders:
            order = self._orm_to_managed(db_order)
            self._orders[order.id] = order
            if order.exchange_id:
                self._exchange_id_map[order.exchange_id] = order.id
            loaded.append(order)

        logger.info(f"Loaded {len(loaded)} orders for bot {bot_id}")
        return loaded

    def _transition_state(self, order: ManagedOrder, new_state: OrderState) -> None:
        """
        Transition order to new state with validation.

        Args:
            order: Order to transition
            new_state: Target state

        Raises:
            OrderTransitionError: If transition is invalid
        """
        if not order.can_transition_to(new_state):
            raise OrderTransitionError(order.state, new_state)

        old_state = order.state
        order.state = new_state
        order.updated_at = datetime.now(timezone.utc)

        logger.debug(
            f"Order {order.id} transitioned: {old_state.value} -> {new_state.value}"
        )

    async def _submit_to_exchange(self, order: ManagedOrder) -> dict[str, Any]:
        """Submit order to exchange."""
        return await self.exchange.create_order(
            symbol=order.symbol,
            order_type=order.order_type,
            side=order.side,
            amount=float(order.quantity),
            price=float(order.price) if order.price else None,
        )

    async def _retry_with_backoff(
        self,
        operation: Callable,
        order: ManagedOrder,
    ) -> Any:
        """
        Execute operation with exponential backoff retry.

        Args:
            operation: Async function to execute
            order: Order being processed

        Returns:
            Operation result

        Raises:
            Exception: If all retries exhausted
        """
        last_exception: Exception | None = None

        while order.retry_count <= order.max_retries:
            try:
                return await operation(order)

            except Exception as e:
                last_exception = e
                order.retry_count += 1
                order.last_error = str(e)

                if order.retry_count > order.max_retries:
                    break

                # Calculate delay with exponential backoff
                delay = min(
                    self.base_retry_delay * (2 ** (order.retry_count - 1)),
                    self.max_retry_delay,
                )
                logger.warning(
                    f"Retry {order.retry_count}/{order.max_retries} for order "
                    f"{order.id} in {delay}s: {e}"
                )
                await asyncio.sleep(delay)

        raise last_exception or Exception("Unknown error during retry")

    async def _persist_order(self, order: ManagedOrder) -> None:
        """Persist order state to database."""
        try:
            # Check if order exists
            stmt = select(OrderORM).where(OrderORM.id == order.id)
            result = await self.db_session.execute(stmt)
            db_order = result.scalar_one_or_none()

            if db_order:
                # Update existing
                db_order.exchange_order_id = order.exchange_id
                db_order.status = order.state.value
                db_order.filled_quantity = order.filled_quantity
                db_order.average_fill_price = order.average_fill_price
                db_order.filled_at = order.filled_at
                db_order.grid_level = order.grid_level
            else:
                # Create new
                db_order = OrderORM(
                    id=order.id,
                    bot_id=order.bot_id,
                    exchange_order_id=order.exchange_id,
                    symbol=order.symbol,
                    side=order.side,
                    type=order.order_type,
                    price=order.price,
                    quantity=order.quantity,
                    filled_quantity=order.filled_quantity,
                    average_fill_price=order.average_fill_price,
                    status=order.state.value,
                    filled_at=order.filled_at,
                    grid_level=order.grid_level,
                )
                self.db_session.add(db_order)

            await self.db_session.commit()

        except Exception as e:
            logger.error(f"Failed to persist order {order.id}: {e}")
            await self.db_session.rollback()

    def _extract_fee(self, data: dict[str, Any]) -> tuple[Decimal, str | None]:
        """Extract fee amount and asset from exchange payloads."""
        fee_asset = data.get("feeAsset", data.get("commissionAsset"))
        fee_value: Any = data.get("fee", data.get("commission"))
        if fee_value is None:
            fee_value = data.get("fees")

        if isinstance(fee_value, dict):
            fee_asset = (
                fee_value.get("currency")
                or fee_value.get("asset")
                or fee_asset
            )
            fee_value = fee_value.get(
                "cost", fee_value.get("commission", fee_value.get("fee", 0))
            )
        elif isinstance(fee_value, list):
            total = Decimal("0")
            list_asset = None
            for item in fee_value:
                if isinstance(item, dict):
                    cost = item.get(
                        "cost", item.get("commission", item.get("fee", 0))
                    )
                    try:
                        total += Decimal(str(cost))
                    except Exception:
                        pass
                    item_asset = (
                        item.get("currency")
                        or item.get("asset")
                        or item.get("commissionAsset")
                    )
                    if item_asset and list_asset is None:
                        list_asset = item_asset
                else:
                    try:
                        total += Decimal(str(item))
                    except Exception:
                        pass
            fee_value = total
            if list_asset:
                fee_asset = list_asset

        try:
            fee_decimal = Decimal(str(fee_value or 0))
        except Exception:
            fee_decimal = Decimal("0")

        return fee_decimal, str(fee_asset) if fee_asset else None

    async def _process_exchange_update(
        self,
        order: ManagedOrder,
        data: dict[str, Any],
    ) -> None:
        """
        Process order update from exchange.

        Updates order state based on exchange data.

        Args:
            order: Order to update
            data: Exchange order data
        """
        # Extract fill information (handle different exchange formats)
        filled = Decimal(str(data.get("filled", data.get("z", 0))))
        average_price = data.get("average", data.get("ap", data.get("avgPrice")))
        status = data.get("status", data.get("X", "")).lower()
        fee_value, fee_asset = self._extract_fee(data)
        order.fee = fee_value
        if fee_asset:
            order.fee_asset = fee_asset

        # Normalize status
        if status in ("closed", "filled", "trade"):
            status = "filled"
        elif status in ("canceled", "cancelled", "expired"):
            status = "cancelled"
        elif status == "rejected":
            status = "rejected"

        # Update fill information
        if filled > order.filled_quantity:
            order.filled_quantity = filled
            if average_price:
                order.average_fill_price = Decimal(str(average_price))

        # Determine new state
        if status == "filled" or filled >= order.quantity:
            if order.can_transition_to(OrderState.FILLED):
                self._transition_state(order, OrderState.FILLED)
                order.filled_at = datetime.now(timezone.utc)

                # Broadcast order update via WebSocket
                from api.core.ws_manager import broadcast_order_update
                user_id = await self._cache_bot_user(order.bot_id)
                await broadcast_order_update(
                    user_id=str(user_id),
                    bot_id=str(order.bot_id),
                    order={
                        "id": str(order.id),
                        "status": order.state.value,
                        "filled_quantity": float(order.filled_quantity),
                        "average_fill_price": float(order.average_fill_price or 0)
                    }
                )
                try:
                    from api.services.telegram_service import notify_order_filled
                    asyncio.create_task(
                        notify_order_filled(
                            user_id,
                            order.symbol,
                            order.side,
                            order.filled_quantity,
                            order.average_fill_price or order.price or Decimal("0"),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to queue Telegram fill notification: {e}")

                if self.on_order_filled:
                    if asyncio.iscoroutinefunction(self.on_order_filled):
                        await self.on_order_filled(order)
                    else:
                        self.on_order_filled(order)

                try:
                    from bot.tasks import process_order_fill
                    fill_payload = {
                        "filledQuantity": str(
                            data.get("filledQuantity", order.filled_quantity)
                        ),
                        "avgPrice": str(
                            data.get("avgPrice", order.average_fill_price or 0)
                        ),
                        "status": "filled",
                        "fee": str(fee_value),
                        "feeAsset": fee_asset,
                        "tradeId": data.get("tradeId") or data.get("id"),
                        "timestamp": data.get("timestamp"),
                        "realizedPnl": data.get("realizedPnl")
                        or data.get("realized_pnl")
                        or data.get("pnl"),
                    }
                    process_order_fill.delay(
                        str(order.bot_id),
                        str(order.id),
                        fill_payload,
                    )
                except Exception as e:
                    logger.warning(f"Failed to enqueue fill persistence: {e}")

        elif status == "cancelled":
            if order.can_transition_to(OrderState.CANCELLED):
                self._transition_state(order, OrderState.CANCELLED)

        elif status == "rejected":
            if order.can_transition_to(OrderState.REJECTED):
                self._transition_state(order, OrderState.REJECTED)

        elif filled > Decimal("0") and order.state == OrderState.OPEN:
            if order.can_transition_to(OrderState.PARTIALLY_FILLED):
                self._transition_state(order, OrderState.PARTIALLY_FILLED)

        await self._persist_order(order)

    def _orm_to_managed(self, db_order: OrderORM) -> ManagedOrder:
        """Convert ORM order to ManagedOrder."""
        # Map status string to OrderState
        state_map = {
            "pending": OrderState.PENDING,
            "submitting": OrderState.SUBMITTING,
            "open": OrderState.OPEN,
            "partially_filled": OrderState.PARTIALLY_FILLED,
            "filled": OrderState.FILLED,
            "cancelling": OrderState.CANCELLING,
            "cancelled": OrderState.CANCELLED,
            "rejected": OrderState.REJECTED,
            "error": OrderState.ERROR,
        }

        return ManagedOrder(
            id=db_order.id,
            bot_id=db_order.bot_id,
            symbol=db_order.symbol,
            side=db_order.side,
            order_type=db_order.type,
            quantity=db_order.quantity,
            price=db_order.price,
            state=state_map.get(db_order.status, OrderState.ERROR),
            exchange_id=db_order.exchange_order_id,
            filled_quantity=db_order.filled_quantity,
            average_fill_price=db_order.average_fill_price,
            created_at=db_order.created_at,
            filled_at=db_order.filled_at,
            updated_at=db_order.updated_at,
            grid_level=db_order.grid_level,
        )

    async def _cache_bot_user(self, bot_id: UUID) -> UUID:
        """
        Cache and return user_id for a given bot_id.

        Args:
            bot_id: The bot ID to lookup

        Returns:
            The user_id that owns the bot
        """
        if bot_id not in self._bot_user_cache:
            from api.models.orm import Bot
            stmt = select(Bot.user_id).where(Bot.id == bot_id)
            result = await self.db_session.execute(stmt)
            user_id = result.scalar_one()
            self._bot_user_cache[bot_id] = user_id
        return self._bot_user_cache[bot_id]
