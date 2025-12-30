"""
WebSocket Manager

Manages WebSocket connections for real-time order updates from exchanges.
Supports Binance and Bybit user data streams.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class WebSocketConfig:
    """WebSocket connection configuration."""

    api_key: str
    api_secret: str
    testnet: bool = False
    ping_interval: int = 30
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 10


class WebSocketHandler(ABC):
    """Abstract base class for exchange-specific WebSocket handlers."""

    def __init__(self, config: WebSocketConfig) -> None:
        self.config = config
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._reconnect_count = 0
        self._callbacks: dict[str, list[Callable]] = {
            "order_update": [],
            "execution": [],
            "balance_update": [],
        }

    @abstractmethod
    async def connect(self) -> None:
        """Establish WebSocket connection."""
        pass

    @abstractmethod
    async def subscribe_user_data(self) -> None:
        """Subscribe to user data stream (orders, executions, balance)."""
        pass

    @abstractmethod
    def _parse_message(self, data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """Parse exchange-specific message format."""
        pass

    def on_order_update(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for order updates."""
        self._callbacks["order_update"].append(callback)

    def on_execution(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for trade executions."""
        self._callbacks["execution"].append(callback)

    def on_balance_update(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register callback for balance updates."""
        self._callbacks["balance_update"].append(callback)

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("WebSocket disconnected")

    async def _listen(self) -> None:
        """Listen for messages and dispatch to callbacks."""
        while self._running and self._ws and not self._ws.closed:
            try:
                msg = await asyncio.wait_for(
                    self._ws.receive(),
                    timeout=self.config.ping_interval + 10,
                )

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    result = self._parse_message(data)
                    if result:
                        event_type, payload = result
                        await self._dispatch(event_type, payload)

                elif msg.type == aiohttp.WSMsgType.PING:
                    await self._ws.pong()

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    logger.warning(f"WebSocket closed/error: {msg}")
                    break

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                if self._ws and not self._ws.closed:
                    await self._ws.ping()

            except Exception as e:
                logger.error(f"WebSocket listen error: {e}")
                break

        # Attempt reconnection
        if self._running:
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._reconnect_count >= self.config.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            self._running = False
            return

        self._reconnect_count += 1
        delay = min(
            self.config.reconnect_delay * (2 ** (self._reconnect_count - 1)),
            60,  # Max 60 seconds
        )
        logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_count})")
        await asyncio.sleep(delay)

        try:
            await self.connect()
            await self.subscribe_user_data()
            self._reconnect_count = 0  # Reset on successful reconnection
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            await self._reconnect()

    async def _dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """Dispatch event to registered callbacks."""
        for callback in self._callbacks.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(payload)
                else:
                    callback(payload)
            except Exception as e:
                logger.error(f"Callback error for {event_type}: {e}")


class BinanceWebSocket(WebSocketHandler):
    """
    Binance User Data Stream WebSocket handler.

    Subscribes to executionReport events for order updates.
    Uses listenKey from REST API for authentication.
    """

    MAINNET_REST = "https://api.binance.com"
    TESTNET_REST = "https://testnet.binance.vision"
    MAINNET_WS = "wss://stream.binance.com:9443/ws"
    TESTNET_WS = "wss://testnet.binance.vision/ws"

    def __init__(self, config: WebSocketConfig) -> None:
        super().__init__(config)
        self._listen_key: str | None = None
        self._keepalive_task: asyncio.Task | None = None

    @property
    def rest_url(self) -> str:
        return self.TESTNET_REST if self.config.testnet else self.MAINNET_REST

    @property
    def ws_url(self) -> str:
        return self.TESTNET_WS if self.config.testnet else self.MAINNET_WS

    async def connect(self) -> None:
        """Connect to Binance user data stream."""
        self._session = aiohttp.ClientSession()

        # Get listen key from REST API
        self._listen_key = await self._get_listen_key()
        if not self._listen_key:
            raise RuntimeError("Failed to get Binance listen key")

        # Connect to WebSocket
        ws_url = f"{self.ws_url}/{self._listen_key}"
        self._ws = await self._session.ws_connect(ws_url)
        self._running = True

        # Start keepalive task (ping every 30 minutes)
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        logger.info(f"Connected to Binance WebSocket (testnet={self.config.testnet})")

    async def subscribe_user_data(self) -> None:
        """No subscription needed - listen key auto-subscribes to user data."""
        # Start listening
        asyncio.create_task(self._listen())

    async def disconnect(self) -> None:
        """Close Binance WebSocket and cleanup."""
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass

        if self._listen_key:
            await self._delete_listen_key()

        await super().disconnect()

    def _parse_message(self, data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """Parse Binance WebSocket message."""
        event_type = data.get("e")

        if event_type == "executionReport":
            # Order update
            return "order_update", {
                "exchange": "binance",
                "orderId": data.get("i"),  # Order ID
                "clientOrderId": data.get("c"),
                "symbol": data.get("s"),
                "side": data.get("S", "").lower(),
                "orderType": data.get("o", "").lower(),
                "status": data.get("X", "").lower(),
                "price": data.get("p"),
                "quantity": data.get("q"),
                "filledQuantity": data.get("z"),
                "lastFilledQuantity": data.get("l"),
                "avgPrice": data.get("ap") or data.get("L"),  # Average or last fill price
                "commission": data.get("n"),
                "commissionAsset": data.get("N"),
                "fee": data.get("n"),
                "feeAsset": data.get("N"),
                "tradeId": data.get("t"),
                "timestamp": data.get("T"),
            }

        elif event_type == "outboundAccountPosition":
            # Balance update
            return "balance_update", {
                "exchange": "binance",
                "balances": [
                    {
                        "asset": b.get("a"),
                        "free": b.get("f"),
                        "locked": b.get("l"),
                    }
                    for b in data.get("B", [])
                ],
                "timestamp": data.get("u"),
            }

        return None

    async def _get_listen_key(self) -> str | None:
        """Get listen key from Binance REST API."""
        url = f"{self.rest_url}/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self.config.api_key}

        try:
            async with self._session.post(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("listenKey")
                else:
                    logger.error(f"Failed to get listen key: {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"Error getting listen key: {e}")
            return None

    async def _keepalive_loop(self) -> None:
        """Keep listen key alive by sending ping every 30 minutes."""
        while self._running and self._listen_key:
            await asyncio.sleep(30 * 60)  # 30 minutes
            await self._ping_listen_key()

    async def _ping_listen_key(self) -> None:
        """Ping to keep listen key alive."""
        if not self._listen_key:
            return

        url = f"{self.rest_url}/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self.config.api_key}
        params = {"listenKey": self._listen_key}

        try:
            async with self._session.put(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Listen key ping failed: {await resp.text()}")
        except Exception as e:
            logger.error(f"Error pinging listen key: {e}")

    async def _delete_listen_key(self) -> None:
        """Delete listen key on disconnect."""
        if not self._listen_key or not self._session:
            return

        url = f"{self.rest_url}/api/v3/userDataStream"
        headers = {"X-MBX-APIKEY": self.config.api_key}
        params = {"listenKey": self._listen_key}

        try:
            async with self._session.delete(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    logger.debug("Listen key deleted")
        except Exception:
            pass  # Best effort


class BybitWebSocket(WebSocketHandler):
    """
    Bybit Private WebSocket handler.

    Subscribes to order and execution events.
    Uses HMAC signature for authentication.
    """

    MAINNET_WS = "wss://stream.bybit.com/v5/private"
    TESTNET_WS = "wss://stream-testnet.bybit.com/v5/private"

    @property
    def ws_url(self) -> str:
        return self.TESTNET_WS if self.config.testnet else self.MAINNET_WS

    async def connect(self) -> None:
        """Connect to Bybit private WebSocket."""
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.ws_url)
        self._running = True

        # Authenticate
        await self._authenticate()

        logger.info(f"Connected to Bybit WebSocket (testnet={self.config.testnet})")

    async def subscribe_user_data(self) -> None:
        """Subscribe to order and execution topics."""
        subscribe_msg = {
            "op": "subscribe",
            "args": ["order", "execution"],
        }
        await self._ws.send_json(subscribe_msg)

        # Start listening
        asyncio.create_task(self._listen())

    def _parse_message(self, data: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """Parse Bybit WebSocket message."""
        topic = data.get("topic")

        if topic == "order":
            # Order updates
            for order in data.get("data", []):
                return "order_update", {
                    "exchange": "bybit",
                    "orderId": order.get("orderId"),
                    "clientOrderId": order.get("orderLinkId"),
                    "symbol": order.get("symbol"),
                    "side": order.get("side", "").lower(),
                    "orderType": order.get("orderType", "").lower(),
                    "status": order.get("orderStatus", "").lower(),
                    "price": order.get("price"),
                    "quantity": order.get("qty"),
                    "filledQuantity": order.get("cumExecQty"),
                    "avgPrice": order.get("avgPrice"),
                    "timestamp": order.get("updatedTime"),
                }

        elif topic == "execution":
            # Trade executions
            for exec in data.get("data", []):
                return "execution", {
                    "exchange": "bybit",
                    "orderId": exec.get("orderId"),
                    "execId": exec.get("execId"),
                    "symbol": exec.get("symbol"),
                    "side": exec.get("side", "").lower(),
                    "price": exec.get("execPrice"),
                    "quantity": exec.get("execQty"),
                    "fee": exec.get("execFee"),
                    "feeAsset": exec.get("feeCurrency"),
                    "timestamp": exec.get("execTime"),
                }

        return None

    async def _authenticate(self) -> None:
        """Authenticate with Bybit using HMAC signature."""
        expires = int(time.time() * 1000) + 10000  # 10 seconds from now
        signature = self._generate_signature(expires)

        auth_msg = {
            "op": "auth",
            "args": [self.config.api_key, expires, signature],
        }
        await self._ws.send_json(auth_msg)

        # Wait for auth response
        msg = await self._ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if data.get("success"):
                logger.debug("Bybit authentication successful")
            else:
                raise RuntimeError(f"Bybit auth failed: {data}")

    def _generate_signature(self, expires: int) -> str:
        """Generate HMAC signature for authentication."""
        param_str = f"GET/realtime{expires}"
        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            param_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class WebSocketManager:
    """
    Manages WebSocket connections for multiple exchanges.

    Provides unified interface for real-time order updates.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, WebSocketHandler] = {}

    async def connect(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ) -> None:
        """
        Connect to exchange WebSocket.

        Args:
            exchange_id: Exchange identifier (binance, bybit)
            api_key: API key
            api_secret: API secret
            testnet: Use testnet endpoint
        """
        config = WebSocketConfig(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )

        if exchange_id == "binance":
            handler = BinanceWebSocket(config)
        elif exchange_id == "bybit":
            handler = BybitWebSocket(config)
        else:
            logger.warning(f"WebSocket not supported for {exchange_id}")
            return

        await handler.connect()
        await handler.subscribe_user_data()
        self._handlers[exchange_id] = handler

    async def disconnect(self, exchange_id: str | None = None) -> None:
        """
        Disconnect from exchange WebSocket.

        Args:
            exchange_id: Specific exchange to disconnect, or None for all
        """
        if exchange_id:
            handler = self._handlers.pop(exchange_id, None)
            if handler:
                await handler.disconnect()
        else:
            for handler in self._handlers.values():
                await handler.disconnect()
            self._handlers.clear()

    def on_order_update(
        self,
        callback: Callable[[dict[str, Any]], None],
        exchange_id: str | None = None,
    ) -> None:
        """
        Register callback for order updates.

        Args:
            callback: Function to call with order data
            exchange_id: Specific exchange, or None for all
        """
        handlers = (
            [self._handlers[exchange_id]]
            if exchange_id and exchange_id in self._handlers
            else self._handlers.values()
        )
        for handler in handlers:
            handler.on_order_update(callback)

    def on_execution(
        self,
        callback: Callable[[dict[str, Any]], None],
        exchange_id: str | None = None,
    ) -> None:
        """
        Register callback for trade executions.

        Args:
            callback: Function to call with execution data
            exchange_id: Specific exchange, or None for all
        """
        handlers = (
            [self._handlers[exchange_id]]
            if exchange_id and exchange_id in self._handlers
            else self._handlers.values()
        )
        for handler in handlers:
            handler.on_execution(callback)

    def is_connected(self, exchange_id: str) -> bool:
        """Check if connected to exchange WebSocket."""
        handler = self._handlers.get(exchange_id)
        return handler is not None and handler._running

    @property
    def connected_exchanges(self) -> list[str]:
        """List of connected exchanges."""
        return [
            exchange_id
            for exchange_id, handler in self._handlers.items()
            if handler._running
        ]
