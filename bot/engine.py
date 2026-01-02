"""
Bot Engine

Main orchestrator for running trading bots.
Manages strategy execution, order placement, and position tracking.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
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

        balance = None
        try:
            balance = await self.exchange.fetch_balance()
        except Exception as e:
            logger.warning(f"Failed to fetch balance for checks: {e}")

        min_notional = None
        min_qty = None
        step_size = None
        if self.exchange:
            try:
                min_notional = await self.exchange.get_min_notional(
                    self.config.symbol
                )
            except Exception as e:
                logger.warning(f"Failed to fetch min_notional: {e}")
            if hasattr(self.exchange, "get_min_qty"):
                try:
                    min_qty = await self.exchange.get_min_qty(self.config.symbol)
                except Exception as e:
                    logger.warning(f"Failed to fetch min_qty: {e}")
            if hasattr(self.exchange, "get_step_size"):
                try:
                    step_size = await self.exchange.get_step_size(self.config.symbol)
                except Exception as e:
                    logger.warning(f"Failed to fetch step size: {e}")

        filtered_orders = self._filter_orders_by_balance(
            new_orders,
            current_price,
            balance,
            min_notional,
            min_qty,
            step_size,
        )

        # Execute orders with risk management and circuit breaker
        for order in filtered_orders:
            await self._execute_order_with_checks(
                order,
                current_price,
                balance,
                skip_min_notional=min_notional is not None,
                skip_balance_check=balance is not None,
            )

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
        balance: dict | None,
        skip_min_notional: bool = False,
        skip_balance_check: bool = False,
    ) -> None:
        """Execute order with circuit breaker and risk checks."""
        if (
            self.order_manager
            and order.grid_level is not None
            and self.order_manager.has_active_grid_order(
                self.config.id, order.side, order.grid_level
            )
        ):
            logger.info(
                "Order skipped (duplicate grid level): %s %s level=%s",
                order.side,
                self.config.symbol,
                order.grid_level,
            )
            return

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

        # Check exchange minimum notional
        if not skip_min_notional:
            if not await self._check_min_notional(order, current_price):
                return

        # Check available balance
        if not skip_balance_check:
            if not self._check_available_balance(order, current_price, balance):
                return

        # Check risk manager
        if not self._check_order(order, current_price):
            return

        # Execute order
        await self._execute_order(order)

        # Record order placement in circuit breaker
        if self.circuit_breaker:
            await self.circuit_breaker.record_order_placed(self.config.id)

    async def _check_min_notional(
        self,
        order: Order,
        current_price: Decimal,
    ) -> bool:
        """Validate order against exchange minimum notional."""
        if not self.exchange or not hasattr(self.exchange, "get_min_notional"):
            return True

        min_notional = await self.exchange.get_min_notional(self.config.symbol)
        if not min_notional:
            return True

        price = order.price or current_price
        if not price or price <= 0:
            return True

        notional = price * order.quantity
        if notional < min_notional:
            logger.warning(
                "Order blocked by min_notional: %s < %s (%s %s @ %s)",
                notional,
                min_notional,
                order.side,
                order.quantity,
                price,
            )
            return False

        return True

    def _check_available_balance(
        self,
        order: Order,
        current_price: Decimal,
        balance: dict | None,
    ) -> bool:
        """Validate order against available balance."""
        if not balance:
            return True

        symbol_parts = self.config.symbol.split("/")
        if len(symbol_parts) != 2:
            return True

        base_asset, quote_asset = symbol_parts[0], symbol_parts[1]
        free_balances = balance.get("free") or {}

        if order.side == "buy":
            price = order.price or current_price
            notional = (price or Decimal("0")) * order.quantity
            free_quote = Decimal(str(free_balances.get(quote_asset, 0) or 0))
            if free_quote < notional:
                logger.warning(
                    "Order blocked by balance: need %s %s, free %s %s",
                    notional,
                    quote_asset,
                    free_quote,
                    quote_asset,
                )
                return False
        else:
            free_base = Decimal(str(free_balances.get(base_asset, 0) or 0))
            if free_base < order.quantity:
                logger.warning(
                    "Order blocked by balance: need %s %s, free %s %s",
                    order.quantity,
                    base_asset,
                    free_base,
                    base_asset,
                )
                return False

        return True

    def _normalize_quantity(
        self,
        quantity: Decimal,
        min_qty: Decimal | None,
        step_size: Decimal | None,
    ) -> Decimal:
        """Normalize quantity to exchange step size and minimums."""
        normalized = quantity
        if step_size and step_size > 0:
            precision = (normalized / step_size).to_integral_value(
                rounding=ROUND_DOWN
            )
            normalized = precision * step_size
        if min_qty and normalized < min_qty:
            return Decimal("0")
        return normalized

    def _filter_orders_by_balance(
        self,
        orders: list[Order],
        current_price: Decimal,
        balance: dict | None,
        min_notional: Decimal | None,
        min_qty: Decimal | None,
        step_size: Decimal | None,
    ) -> list[Order]:
        """Filter and prioritize orders based on available balance."""
        if not balance:
            return orders

        symbol_parts = self.config.symbol.split("/")
        if len(symbol_parts) != 2:
            return orders

        base_asset, quote_asset = symbol_parts[0], symbol_parts[1]
        free_balances = balance.get("free") or {}
        free_quote = Decimal(str(free_balances.get(quote_asset, 0) or 0))
        free_base = Decimal(str(free_balances.get(base_asset, 0) or 0))

        prioritized = sorted(
            orders,
            key=lambda o: abs((o.price or current_price) - current_price),
        )

        accepted: list[Order] = []
        blocked_reasons: list[str] = []

        for order in prioritized:
            price = order.price or current_price
            normalized_qty = self._normalize_quantity(
                order.quantity, min_qty, step_size
            )
            if normalized_qty <= 0:
                blocked_reasons.append("min_qty/step")
                continue
            if normalized_qty != order.quantity:
                order.quantity = normalized_qty

            if order.side == "buy":
                notional = price * order.quantity
                if min_notional and notional < min_notional:
                    blocked_reasons.append("min_notional")
                    continue
                if free_quote < notional:
                    blocked_reasons.append("balance_quote")
                    continue
                free_quote -= notional
            else:
                if free_base < order.quantity:
                    adjusted_qty = self._normalize_quantity(
                        free_base, min_qty, step_size
                    )
                    if adjusted_qty <= 0:
                        blocked_reasons.append("balance_base")
                        continue
                    order.quantity = adjusted_qty
                notional = price * order.quantity
                if min_notional and notional < min_notional:
                    blocked_reasons.append("min_notional")
                    continue
                if free_base < order.quantity:
                    blocked_reasons.append("balance_base")
                    continue
                free_base -= order.quantity

            accepted.append(order)

        if blocked_reasons:
            reason = blocked_reasons[0]
            logger.warning("Order blocked by %s (suppressed repeated warnings)", reason)

        return accepted

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

    async def handle_order_filled(self, order: ManagedOrder) -> Decimal:
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

        filled_quantity = order.filled_quantity
        if (
            order.side == "buy"
            and order.fee_asset
            and order.fee_asset.upper() == symbol_base.upper()
            and order.fee > 0
        ):
            # Net base received after fee (Binance fees often charged in base on buys).
            filled_quantity = max(order.filled_quantity - order.fee, Decimal("0"))

        if order.side == "buy":
            self._position[symbol_base] = current_position + filled_quantity
        else:
            self._position[symbol_base] = current_position - filled_quantity

        # Notify strategy and get realized P&L
        realized_pnl = Decimal("0")
        if order.average_fill_price:
            # Convert ManagedOrder to strategy Order
            strategy_order = Order(
                id=order.id,
                side=order.side,
                type=order.order_type,
                price=order.price,
                quantity=filled_quantity,
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

        return realized_pnl

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
