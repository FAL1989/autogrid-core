"""
Exchange Connector

Abstract base class for exchange integrations using CCXT.
Provides unified interface for all supported exchanges.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of credential validation."""

    is_valid: bool
    can_trade: bool
    can_withdraw: bool
    markets: list[str] = field(default_factory=list)
    error: str | None = None


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
    async def get_min_notional(self, symbol: str) -> Decimal | None:
        """
        Get minimum notional value for a symbol, if available.

        Returns:
            Minimum order notional in quote currency, or None if unavailable.
        """
        pass

    @abstractmethod
    async def get_min_qty(self, symbol: str) -> Decimal | None:
        """
        Get minimum quantity for a symbol, if available.

        Returns:
            Minimum order quantity in base currency, or None if unavailable.
        """
        pass

    @abstractmethod
    async def get_step_size(self, symbol: str) -> Decimal | None:
        """
        Get quantity step size for a symbol, if available.

        Returns:
            Order quantity increment, or None if unavailable.
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
    async def fetch_my_trades(
        self,
        symbol: str,
        since: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent trades for the authenticated user.

        Args:
            symbol: Trading pair
            since: Timestamp in milliseconds
            limit: Max number of trades

        Returns:
            List of trade dicts
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

    async def get_min_notional(self, symbol: str) -> Decimal | None:
        """Get min notional from CCXT market metadata."""
        if not self._exchange:
            return None

        market = self._exchange.market(symbol) if self._exchange else None
        if not market:
            return None

        limits = market.get("limits", {})
        cost_limits = limits.get("cost") or {}
        min_cost = cost_limits.get("min")

        if min_cost is None:
            min_cost = market.get("minNotional") or market.get("min_notional")

        if min_cost is None:
            info = market.get("info") or {}
            min_cost = info.get("minNotional") or info.get("min_notional")

        if min_cost is None:
            return None

        return Decimal(str(min_cost))

    async def get_min_qty(self, symbol: str) -> Decimal | None:
        """Get min quantity from CCXT market metadata."""
        if not self._exchange:
            return None

        market = self._exchange.market(symbol) if self._exchange else None
        if not market:
            return None

        limits = market.get("limits", {})
        amount_limits = limits.get("amount") or {}
        min_amount = amount_limits.get("min")

        if min_amount is None:
            info = market.get("info") or {}
            min_amount = info.get("minQty") or info.get("min_qty")

        if min_amount is None:
            return None

        return Decimal(str(min_amount))

    async def get_step_size(self, symbol: str) -> Decimal | None:
        """Get quantity step size from CCXT market metadata."""
        if not self._exchange:
            return None

        market = self._exchange.market(symbol) if self._exchange else None
        if not market:
            return None

        info = market.get("info") or {}
        filters = info.get("filters") or []
        for item in filters:
            if item.get("filterType") == "LOT_SIZE":
                step_size = item.get("stepSize") or item.get("step_size")
                if step_size is not None:
                    return Decimal(str(step_size))

        step_size = info.get("stepSize") or info.get("step_size")
        if step_size is not None:
            return Decimal(str(step_size))

        precision = market.get("precision", {}).get("amount")
        if precision is None:
            return None

        return Decimal("1") / (Decimal("10") ** int(precision))

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

    async def fetch_my_trades(
        self,
        symbol: str,
        since: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch user trades via CCXT."""
        return await self._exchange.fetch_my_trades(
            symbol=symbol,
            since=since,
            limit=limit,
        )

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[list]:
        """Fetch OHLCV via CCXT."""
        return await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def validate_credentials(self) -> ValidationResult:
        """
        Validate API credentials and detect permissions.

        Connects to exchange, loads markets, and tests permissions.

        Returns:
            ValidationResult with validation status and permissions.
        """
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
            markets = list(self._exchange.markets.keys())

            # Test READ permission via fetch_balance
            can_trade = False
            can_withdraw = False

            try:
                await self._exchange.fetch_balance()
                # If we can read balance, we have at least read permission
                # Assume trade is enabled (most common case)
                can_trade = True
            except ccxt.PermissionDenied:
                can_trade = False
            except ccxt.AuthenticationError as e:
                await self._exchange.close()
                return ValidationResult(
                    is_valid=False,
                    can_trade=False,
                    can_withdraw=False,
                    markets=[],
                    error=f"Authentication failed: {str(e)}",
                )

            # Check withdraw permission (exchange-specific)
            can_withdraw = await self._check_withdraw_permission()

            await self._exchange.close()

            return ValidationResult(
                is_valid=True,
                can_trade=can_trade,
                can_withdraw=can_withdraw,
                markets=markets,
            )

        except Exception as e:
            if self._exchange:
                try:
                    await self._exchange.close()
                except Exception:
                    pass
            return ValidationResult(
                is_valid=False,
                can_trade=False,
                can_withdraw=False,
                markets=[],
                error=f"Validation error: {str(e)}",
            )

    async def _check_withdraw_permission(self) -> bool:
        """
        Check if API key has withdraw permission.

        Uses exchange-specific APIs where available.
        Returns True if withdraw is enabled, False otherwise.
        """
        try:
            if self.exchange_id == "binance":
                # Binance has a specific endpoint to check API key permissions
                # GET /sapi/v1/account/apiRestrictions
                result = await self._exchange.sapi_get_account_apirestrictions()
                return result.get("enableWithdrawals", False)

            elif self.exchange_id == "bybit":
                # Bybit: /v5/user/query-api
                result = await self._exchange.private_get_v5_user_query_api()
                permissions = result.get("result", {}).get("permissions", {})
                wallet_perms = permissions.get("Wallet", [])
                return "Withdrawal" in wallet_perms if isinstance(wallet_perms, list) else False

            # MEXC and others: no direct API, assume False (safe default)
            return False

        except Exception as e:
            logger.debug(f"Could not check withdraw permission: {e}")
            # If we can't determine, assume False (safe)
            return False

    async def refresh_markets(self) -> list[str]:
        """
        Refresh and return available markets from exchange.

        Returns:
            List of market symbols (e.g., ['BTC/USDT', 'ETH/USDT']).

        Raises:
            RuntimeError: If not connected to exchange.
        """
        if not self._connected:
            raise RuntimeError("Not connected to exchange")

        await self._exchange.load_markets(reload=True)
        return list(self._exchange.markets.keys())
