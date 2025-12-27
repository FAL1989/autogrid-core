"""
Bot Engine

Main orchestrator for running trading bots.
Manages strategy execution, order placement, and position tracking.
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from bot.exchange.connector import ExchangeConnector
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


class BotEngine:
    """
    Trading Bot Engine.

    Orchestrates strategy execution with risk management and order handling.
    """

    def __init__(
        self,
        config: BotConfig,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self.config = config
        self.strategy = config.strategy
        self.exchange = config.exchange
        self.risk_manager = risk_manager
        self._running = False
        self._orders: list[Order] = []

    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running

    async def start(self) -> None:
        """
        Start the bot engine.

        - Connects to exchange
        - Initializes strategy
        - Starts main trading loop
        """
        logger.info(f"Starting bot {self.config.id} for {self.config.symbol}")
        self._running = True

        try:
            # Connect to exchange
            await self.exchange.connect()

            # Main loop
            while self._running:
                await self._tick()
                await asyncio.sleep(1)  # 1 second interval

        except Exception as e:
            logger.error(f"Bot {self.config.id} error: {e}")
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
        self._running = False

        # Cancel open orders
        for order in self._orders:
            if order.status == "open":
                await self.exchange.cancel_order(order.id, self.config.symbol)

        await self.exchange.disconnect()

    async def _tick(self) -> None:
        """
        Single tick of the trading loop.

        1. Fetch current market data
        2. Let strategy calculate orders
        3. Execute orders with risk checks
        """
        # Get current price
        ticker = await self.exchange.fetch_ticker(self.config.symbol)
        current_price = Decimal(str(ticker["last"]))

        # Let strategy decide on orders
        new_orders = self.strategy.calculate_orders(
            current_price=current_price,
            open_orders=self._orders,
        )

        # Execute orders with risk management
        for order in new_orders:
            if self._check_order(order, current_price):
                await self._execute_order(order)

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
            logger.info(f"Order placed: {order}")

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            order.status = "error"


async def main() -> None:
    """Main entry point for bot engine."""
    logger.info("Bot engine starting...")
    # TODO: Load bots from database and start them
    logger.info("No bots configured. Exiting.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
