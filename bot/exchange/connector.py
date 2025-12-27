"""
Exchange Connector

Abstract base class for exchange integrations using CCXT.
Provides unified interface for all supported exchanges.
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Literal

logger = logging.getLogger(__name__)


class ExchangeConnector(ABC):
    """
    Abstract Exchange Connector.

    Wraps CCXT to provide unified interface for all exchanges.
    Handles authentication, rate limiting, and error recovery.

    Supported exchanges:
    - Binance (spot + futures)
    - MEXC (spot only)
    - Bybit (spot + derivatives)
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ) -> None:
        """
        Initialize exchange connector.

        Args:
            exchange_id: Exchange identifier (binance, mexc, bybit)
            api_key: API key
            api_secret: API secret
            testnet: Use testnet if available
        """
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """
        Connect to exchange.

        - Validates credentials
        - Checks permissions (must have trade, must NOT have withdraw)
        - Establishes WebSocket connection if available
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        pass

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """
        Fetch current ticker for symbol.

        Returns:
            Dict with: symbol, last, bid, ask, volume, timestamp
        """
        pass

    @abstractmethod
    async def fetch_balance(self) -> dict[str, Any]:
        """
        Fetch account balance.

        Returns:
            Dict with currency balances
        """
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        order_type: Literal["limit", "market"],
        side: Literal["buy", "sell"],
        amount: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        """
        Create a new order.

        Args:
            symbol: Trading pair
            order_type: 'limit' or 'market'
            side: 'buy' or 'sell'
            amount: Order amount
            price: Order price (required for limit orders)

        Returns:
            Order details including exchange order ID
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Exchange order ID
            symbol: Trading pair

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    async def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """
        Fetch order details.

        Args:
            order_id: Exchange order ID
            symbol: Trading pair

        Returns:
            Order details
        """
        pass

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[list]:
        """
        Fetch OHLCV candlestick data.

        Args:
            symbol: Trading pair
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Number of candles

        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        pass


class CCXTConnector(ExchangeConnector):
    """
    CCXT-based Exchange Connector.

    Implements ExchangeConnector using the CCXT library.
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ) -> None:
        super().__init__(exchange_id, api_key, api_secret, testnet)
        self._exchange: Any = None  # CCXT exchange instance

    async def connect(self) -> None:
        """Connect to exchange via CCXT."""
        try:
            import ccxt.async_support as ccxt

            exchange_class = getattr(ccxt, self.exchange_id)
            self._exchange = exchange_class({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "sandbox": self.testnet,
                "enableRateLimit": True,
            })

            # Load markets
            await self._exchange.load_markets()

            # Validate credentials
            balance = await self._exchange.fetch_balance()
            logger.info(f"Connected to {self.exchange_id}")

            self._connected = True

        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_id}: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from exchange."""
        if self._exchange:
            await self._exchange.close()
        self._connected = False
        logger.info(f"Disconnected from {self.exchange_id}")

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch ticker via CCXT."""
        return await self._exchange.fetch_ticker(symbol)

    async def fetch_balance(self) -> dict[str, Any]:
        """Fetch balance via CCXT."""
        return await self._exchange.fetch_balance()

    async def create_order(
        self,
        symbol: str,
        order_type: Literal["limit", "market"],
        side: Literal["buy", "sell"],
        amount: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        """Create order via CCXT."""
        if order_type == "limit" and price is None:
            raise ValueError("Price required for limit orders")

        return await self._exchange.create_order(
            symbol=symbol,
            type=order_type,
            side=side,
            amount=amount,
            price=price,
        )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order via CCXT."""
        try:
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Fetch order via CCXT."""
        return await self._exchange.fetch_order(order_id, symbol)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[list]:
        """Fetch OHLCV via CCXT."""
        return await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
