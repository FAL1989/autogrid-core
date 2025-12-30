"""
Bot Engine

Main orchestrator for running trading bots.
Manages strategy execution, order placement, and position tracking.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Protocol
from uuid import UUID

from bot.circuit_breaker import CircuitBreaker
from bot.exchange.connector import ExchangeConnector
from bot.order_manager import ManagedOrder, OrderManager, OrderState
from bot.strategies.base import BaseStrategy, Order

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Bot configuration."""

    id: UUID
    user_id: UUID
    strategy: BaseStrategy
    exchange: ExchangeConnector
    symbol: str
    investment: Decimal


class RiskManager(Protocol):
    """Risk management interface."""

    def check_order(self, order: Order, current_price: Decimal) -> bool:
        """Check if order passes risk checks."""
        ...

    def check_loss_limit(self, pnl: Decimal, investment: Decimal) -> bool:
        """Check if loss limit is exceeded."""
        ...


@dataclass
class BotState:
    """Current bot state."""

    is_running: bool = False
    current_price: Decimal = Decimal("0")
    position: dict[str, Decimal] = field(default_factory=dict)
    total_orders: int = 0
    filled_orders: int = 0
    realized_pnl: Decimal = Decimal("0")


class BotEngine:
    """
    Trading Bot Engine.

    Orchestrates strategy execution with risk management, order handling,
    circuit breaker protection, and real-time updates.
    """

    def __init__(
        self,
        config: BotConfig,
        order_manager: OrderManager | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        risk_manager: RiskManager | None = None,
        on_order_filled: Callable[[ManagedOrder], None] | None = None,
        tick_interval: float = 1.0,
    ) -> None:
        """
        Initialize bot engine.

        Args:
            config: Bot configuration
            order_manager: Order lifecycle manager
            circuit_breaker: Safety circuit breaker
            risk_manager: Risk management handler
            on_order_filled: Callback when order fills
            tick_interval: Seconds between trading ticks
        """
        self.config = config
        self.strategy = config.strategy
        self.exchange = config.exchange
        self.order_manager = order_manager
        self.circuit_breaker = circuit_breaker
        self.risk_manager = risk_manager
        self.on_order_filled = on_order_filled
        self.tick_interval = tick_interval

        # State
        self._state = BotState()
        self._orders: list[Order] = []  # Legacy order tracking
        self._position: dict[str, Decimal] = {}  # symbol -> quantity

    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._state.is_running

    @property
    def state(self) -> BotState:
        """Get current bot state."""
        return self._state

    async def start(self) -> None:
        """
        Start the bot engine.

        - Connects to exchange
        - Checks circuit breaker
        - Initializes strategy
        - Starts main trading loop
        """
        logger.info(f"Starting bot {self.config.id} for {self.config.symbol}")
        self._state.is_running = True

        try:
            # Connect to exchange
            await self.exchange.connect()

            # Main loop
            while self._state.is_running:
                await self._tick()
                await asyncio.sleep(self.tick_interval)

        except Exception as e:
            logger.error(f"Bot {self.config.id} error: {e}")
            try:
                from api.services.telegram_service import notify_error
                asyncio.create_task(
                    notify_error(
                        self.config.user_id,
                        f"Bot {self.config.id} error: {e}",
                    )
                )
            except Exception as exc:
                logger.warning(f"Failed to queue Telegram error notification: {exc}")
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """
        Stop the bot engine.

        - Cancels all open orders
        - Disconnects from exchange
        """
        logger.info(f"Stopping bot {self.config.id}")
        self._state.is_running = False

        # Cancel open orders via OrderManager if available
        if self.order_manager:
            cancelled = await self.order_manager.cancel_all_orders(self.config.id)
            logger.info(f"Cancelled {cancelled} orders")
        else:
            # Legacy order cancellation
            for order in self._orders:
                if order.status == "open" and order.exchange_id:
                    await self.exchange.cancel_order(order.exchange_id, self.config.symbol)

        await self.exchange.disconnect()

    async def _tick(self) -> None:
        """
        Single tick of the trading loop.

        1. Check circuit breaker
        2. Fetch current market data
        3. Let strategy calculate orders
        4. Execute orders with risk checks
        """
        # Check circuit breaker first
        if self.circuit_breaker:
            is_tripped = await self.circuit_breaker.is_tripped(self.config.id)
            if is_tripped:
                await self._handle_circuit_trip()
                return

        # Get current price
        ticker = await self.exchange.fetch_ticker(self.config.symbol)
        current_price = Decimal(str(ticker["last"]))
        self._state.current_price = current_price

        # Get open orders
        open_orders = await self._get_open_orders()

        # Let strategy decide on orders
        new_orders = self.strategy.calculate_orders(
            current_price=current_price,
            open_orders=open_orders,
        )

        # Execute orders with risk management and circuit breaker
        for order in new_orders:
            await self._execute_order_with_checks(order, current_price)

    async def _get_open_orders(self) -> list[Order]:
        """Get currently open orders."""
        if self.order_manager:
            # Convert ManagedOrders to strategy Orders
            managed_orders = await self.order_manager.get_open_orders(self.config.id)
            return [
                Order(
                    id=mo.id,
                    side=mo.side,
                    type=mo.order_type,
                    price=mo.price,
                    quantity=mo.quantity,
                    status="open" if mo.is_active else mo.state.value,
                    exchange_id=mo.exchange_id,
                    grid_level=mo.grid_level,
                )
                for mo in managed_orders
            ]
        return [o for o in self._orders if o.status == "open"]

    async def _execute_order_with_checks(
        self,
        order: Order,
        current_price: Decimal,
    ) -> None:
        """Execute order with circuit breaker and risk checks."""
        # Check circuit breaker
        if self.circuit_breaker:
            allowed, reason = await self.circuit_breaker.check_order_allowed(
                bot_id=self.config.id,
                order_price=order.price,
                current_price=current_price,
                investment=self.config.investment,
            )
            if not allowed:
                logger.warning(f"Order blocked by circuit breaker: {reason}")
                return

        # Check risk manager
        if not self._check_order(order, current_price):
            return

        # Execute order
        await self._execute_order(order)

        # Record order placement in circuit breaker
        if self.circuit_breaker:
            await self.circuit_breaker.record_order_placed(self.config.id)

    def _check_order(self, order: Order, current_price: Decimal) -> bool:
        """Validate order against risk rules."""
        if self.risk_manager is None:
            return True

        # Check order sanity (price within 10% of market)
        if not self.risk_manager.check_order(order, current_price):
            logger.warning(f"Order rejected by risk manager: {order}")
            return False

        return True

    async def _execute_order(self, order: Order) -> None:
        """Execute order on exchange."""
        if self.order_manager:
            # Use OrderManager for full lifecycle management
            managed_order = ManagedOrder(
                id=order.id,
                bot_id=self.config.id,
                symbol=self.config.symbol,
                side=order.side,
                order_type=order.type,
                quantity=order.quantity,
                price=order.price,
                grid_level=order.grid_level,
            )

            try:
                await self.order_manager.submit_order(managed_order)
                self._state.total_orders += 1
                logger.info(f"Order submitted via OrderManager: {managed_order}")
            except Exception as e:
                logger.error(f"Failed to submit order: {e}")
                order.status = "error"
        else:
            # Legacy direct execution
            try:
                result = await self.exchange.create_order(
                    symbol=self.config.symbol,
                    order_type=order.type,
                    side=order.side,
                    amount=float(order.quantity),
                    price=float(order.price) if order.price else None,
                )
                order.exchange_id = result.get("id")
                order.status = "open"
                self._orders.append(order)
                self._state.total_orders += 1
                logger.info(f"Order placed: {order}")

            except Exception as e:
                logger.error(f"Failed to place order: {e}")
                order.status = "error"

    async def handle_order_filled(self, order: ManagedOrder) -> None:
        """
        Handle order fill event from WebSocket or polling.

        Updates position, calculates P&L, and notifies strategy.

        Args:
            order: The filled order
        """
        self._state.filled_orders += 1

        # Update position
        symbol_base = self.config.symbol.split("/")[0]
        current_position = self._position.get(symbol_base, Decimal("0"))

        if order.side == "buy":
            self._position[symbol_base] = current_position + order.filled_quantity
        else:
            self._position[symbol_base] = current_position - order.filled_quantity

        # Notify strategy and get realized P&L
        realized_pnl = Decimal("0")
        if order.average_fill_price:
            # Convert ManagedOrder to strategy Order
            strategy_order = Order(
                id=order.id,
                side=order.side,
                type=order.order_type,
                price=order.price,
                quantity=order.filled_quantity,
                status="filled",
                exchange_id=order.exchange_id,
                grid_level=order.grid_level,
            )
            # Strategy returns realized P&L (0 for buys, profit/loss for sells)
            realized_pnl = self.strategy.on_order_filled(
                strategy_order, order.average_fill_price
            )

            # Update realized P&L from strategy
            self._state.realized_pnl = self.strategy.realized_pnl

            # Broadcast P&L update via WebSocket
            from api.core.ws_manager import broadcast_pnl_update
            await broadcast_pnl_update(
                user_id=str(self.config.user_id),
                bot_id=str(self.config.id),
                realized_pnl=float(self._state.realized_pnl),
                unrealized_pnl=0.0
            )

        # Record P&L in circuit breaker (losses trigger safety checks)
        if self.circuit_breaker and realized_pnl < 0:
            await self.circuit_breaker.record_pnl(self.config.id, realized_pnl)

        # Callback
        if self.on_order_filled:
            self.on_order_filled(order)

        logger.info(
            f"Order filled: {order.id} - "
            f"Position: {self._position.get(symbol_base, 0)} {symbol_base} - "
            f"P&L: {realized_pnl}"
        )

    async def _handle_circuit_trip(self) -> None:
        """Handle circuit breaker trip."""
        logger.warning(f"Circuit breaker tripped for bot {self.config.id}")

        # Cancel all orders
        if self.order_manager:
            await self.order_manager.cancel_all_orders(self.config.id)

        # Stop the bot
        self._state.is_running = False

    def get_stats(self) -> dict:
        """Get bot statistics."""
        return {
            "bot_id": str(self.config.id),
            "symbol": self.config.symbol,
            "is_running": self._state.is_running,
            "current_price": float(self._state.current_price),
            "position": {k: float(v) for k, v in self._position.items()},
            "total_orders": self._state.total_orders,
            "filled_orders": self._state.filled_orders,
            "realized_pnl": float(self._state.realized_pnl),
            "strategy_stats": self.strategy.get_stats(),
        }


async def main() -> None:
    """Main entry point for bot engine."""
    logger.info("Bot engine starting...")
    # TODO: Load bots from database and start them
    logger.info("No bots configured. Exiting.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
