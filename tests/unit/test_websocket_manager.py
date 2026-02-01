"""
Comprehensive Unit Tests for WebSocket Manager.

Tests for real-time order updates from exchanges covering:
- WebSocket connect success/failure
- Reconnect on disconnect with backoff
- Subscribe to ticker/order updates
- Handle messages (ticker, order update, invalid)
- Unsubscribe and disconnect cleanup
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import WSMsgType

from bot.exchange.websocket_manager import (
    BinanceWebSocket,
    BybitWebSocket,
    WebSocketConfig,
    WebSocketHandler,
    WebSocketManager,
)


class TestWebSocketConfig:
    """Tests for WebSocketConfig dataclass."""

    def test_config_defaults(self) -> None:
        """Config should have sensible defaults."""
        config = WebSocketConfig(
            api_key="test_key",
            api_secret="test_secret",
        )

        assert config.api_key == "test_key"
        assert config.api_secret == "test_secret"
        assert config.testnet is False
        assert config.ping_interval == 30
        assert config.reconnect_delay == 5
        assert config.max_reconnect_attempts == 10

    def test_config_with_testnet(self) -> None:
        """Config should accept testnet flag."""
        config = WebSocketConfig(
            api_key="test_key",
            api_secret="test_secret",
            testnet=True,
        )

        assert config.testnet is True

    def test_config_custom_reconnect_settings(self) -> None:
        """Config should accept custom reconnect settings."""
        config = WebSocketConfig(
            api_key="test_key",
            api_secret="test_secret",
            reconnect_delay=10,
            max_reconnect_attempts=5,
        )

        assert config.reconnect_delay == 10
        assert config.max_reconnect_attempts == 5


@pytest.mark.asyncio
class TestBinanceWebSocket:
    """Tests for Binance WebSocket handler."""

    @pytest.fixture
    def config(self) -> WebSocketConfig:
        """Create test config."""
        return WebSocketConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            testnet=True,
        )

    @pytest.fixture
    def binance_ws(self, config: WebSocketConfig) -> BinanceWebSocket:
        """Create Binance WebSocket handler."""
        return BinanceWebSocket(config)

    async def test_websocket_connect_success(
        self, binance_ws: BinanceWebSocket
    ) -> None:
        """Should successfully connect to Binance WebSocket."""
        mock_ws = AsyncMock()

        # Create proper async context manager mock for POST response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={"listenKey": "test_listen_key"}
        )

        # Create async context manager for session.post
        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)
        mock_session.ws_connect = AsyncMock(return_value=mock_ws)
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await binance_ws.connect()

        assert binance_ws._running is True
        assert binance_ws._listen_key == "test_listen_key"

    async def test_websocket_connect_failure_no_listen_key(
        self, binance_ws: BinanceWebSocket
    ) -> None:
        """Should raise error when listen key cannot be obtained."""
        # Mock failed response
        mock_response = MagicMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")

        # Create async context manager for session.post
        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_post_ctx)
        mock_session.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(RuntimeError, match="Failed to get Binance listen key"):
                await binance_ws.connect()

    def test_parse_message_execution_report(
        self, binance_ws: BinanceWebSocket
    ) -> None:
        """Should parse executionReport message correctly."""
        message = {
            "e": "executionReport",
            "i": 12345,
            "c": "client_order_id",
            "s": "BTCUSDT",
            "S": "BUY",
            "o": "LIMIT",
            "X": "FILLED",
            "p": "50000.00",
            "q": "0.01",
            "z": "0.01",
            "l": "0.01",
            "L": "50000.00",
            "n": "0.00001",
            "N": "BTC",
            "t": 98765,
            "T": 1704067200000,
        }

        result = binance_ws._parse_message(message)

        assert result is not None
        event_type, payload = result
        assert event_type == "order_update"
        assert payload["exchange"] == "binance"
        assert payload["orderId"] == 12345
        assert payload["symbol"] == "BTCUSDT"
        assert payload["side"] == "buy"
        assert payload["status"] == "filled"

    def test_parse_message_balance_update(
        self, binance_ws: BinanceWebSocket
    ) -> None:
        """Should parse outboundAccountPosition message correctly."""
        message = {
            "e": "outboundAccountPosition",
            "B": [
                {"a": "BTC", "f": "1.5", "l": "0.5"},
                {"a": "USDT", "f": "10000", "l": "0"},
            ],
            "u": 1704067200000,
        }

        result = binance_ws._parse_message(message)

        assert result is not None
        event_type, payload = result
        assert event_type == "balance_update"
        assert payload["exchange"] == "binance"
        assert len(payload["balances"]) == 2

    def test_parse_message_unknown_event(
        self, binance_ws: BinanceWebSocket
    ) -> None:
        """Should return None for unknown event types."""
        message = {"e": "unknown_event", "data": {}}

        result = binance_ws._parse_message(message)

        assert result is None

    def test_rest_url_mainnet(self, config: WebSocketConfig) -> None:
        """Should return mainnet REST URL."""
        config.testnet = False
        ws = BinanceWebSocket(config)
        assert ws.rest_url == "https://api.binance.com"

    def test_rest_url_testnet(self, config: WebSocketConfig) -> None:
        """Should return testnet REST URL."""
        config.testnet = True
        ws = BinanceWebSocket(config)
        assert ws.rest_url == "https://testnet.binance.vision"

    async def test_websocket_disconnect_cleanup(
        self, binance_ws: BinanceWebSocket
    ) -> None:
        """Should cleanup resources on disconnect."""
        # Setup mock state
        binance_ws._running = True
        binance_ws._listen_key = "test_key"
        binance_ws._ws = MagicMock()
        binance_ws._ws.closed = False
        binance_ws._ws.close = AsyncMock()
        binance_ws._session = MagicMock()
        binance_ws._session.closed = False
        binance_ws._session.close = AsyncMock()
        binance_ws._session.delete = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        binance_ws._session.delete.return_value.__aenter__ = AsyncMock(
            return_value=mock_response
        )
        binance_ws._session.delete.return_value.__aexit__ = AsyncMock()
        binance_ws._keepalive_task = None

        await binance_ws.disconnect()

        assert binance_ws._running is False
        binance_ws._ws.close.assert_called_once()
        binance_ws._session.close.assert_called_once()


@pytest.mark.asyncio
class TestBybitWebSocket:
    """Tests for Bybit WebSocket handler."""

    @pytest.fixture
    def config(self) -> WebSocketConfig:
        """Create test config."""
        return WebSocketConfig(
            api_key="test_api_key",
            api_secret="test_api_secret",
            testnet=True,
        )

    @pytest.fixture
    def bybit_ws(self, config: WebSocketConfig) -> BybitWebSocket:
        """Create Bybit WebSocket handler."""
        return BybitWebSocket(config)

    def test_ws_url_mainnet(self, config: WebSocketConfig) -> None:
        """Should return mainnet WebSocket URL."""
        config.testnet = False
        ws = BybitWebSocket(config)
        assert ws.ws_url == "wss://stream.bybit.com/v5/private"

    def test_ws_url_testnet(self, config: WebSocketConfig) -> None:
        """Should return testnet WebSocket URL."""
        config.testnet = True
        ws = BybitWebSocket(config)
        assert ws.ws_url == "wss://stream-testnet.bybit.com/v5/private"

    def test_parse_message_order_update(
        self, bybit_ws: BybitWebSocket
    ) -> None:
        """Should parse order topic message correctly."""
        message = {
            "topic": "order",
            "data": [
                {
                    "orderId": "order123",
                    "orderLinkId": "client123",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "orderType": "Limit",
                    "orderStatus": "Filled",
                    "price": "50000",
                    "qty": "0.01",
                    "cumExecQty": "0.01",
                    "avgPrice": "50000",
                    "updatedTime": "1704067200000",
                }
            ],
        }

        result = bybit_ws._parse_message(message)

        assert result is not None
        event_type, payload = result
        assert event_type == "order_update"
        assert payload["exchange"] == "bybit"
        assert payload["orderId"] == "order123"
        assert payload["side"] == "buy"
        assert payload["status"] == "filled"

    def test_parse_message_execution(
        self, bybit_ws: BybitWebSocket
    ) -> None:
        """Should parse execution topic message correctly."""
        message = {
            "topic": "execution",
            "data": [
                {
                    "orderId": "order123",
                    "execId": "exec456",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "execPrice": "50000",
                    "execQty": "0.01",
                    "execFee": "0.00001",
                    "feeCurrency": "BTC",
                    "execTime": "1704067200000",
                }
            ],
        }

        result = bybit_ws._parse_message(message)

        assert result is not None
        event_type, payload = result
        assert event_type == "execution"
        assert payload["exchange"] == "bybit"
        assert payload["execId"] == "exec456"
        assert payload["fee"] == "0.00001"

    def test_generate_signature(self, bybit_ws: BybitWebSocket) -> None:
        """Should generate valid HMAC signature."""
        expires = 1704067200000
        signature = bybit_ws._generate_signature(expires)

        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex digest length


@pytest.mark.asyncio
class TestWebSocketHandler:
    """Tests for WebSocketHandler base class functionality."""

    @pytest.fixture
    def config(self) -> WebSocketConfig:
        """Create test config."""
        return WebSocketConfig(
            api_key="test_key",
            api_secret="test_secret",
            reconnect_delay=1,
            max_reconnect_attempts=3,
        )

    @pytest.fixture
    def handler(self, config: WebSocketConfig) -> BinanceWebSocket:
        """Create a concrete handler for testing base class."""
        return BinanceWebSocket(config)

    def test_register_order_update_callback(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should register order update callback."""
        callback = MagicMock()
        handler.on_order_update(callback)

        assert callback in handler._callbacks["order_update"]

    def test_register_execution_callback(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should register execution callback."""
        callback = MagicMock()
        handler.on_execution(callback)

        assert callback in handler._callbacks["execution"]

    def test_register_balance_update_callback(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should register balance update callback."""
        callback = MagicMock()
        handler.on_balance_update(callback)

        assert callback in handler._callbacks["balance_update"]

    async def test_dispatch_calls_callbacks(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should dispatch event to registered callbacks."""
        callback1 = MagicMock()
        callback2 = AsyncMock()
        handler.on_order_update(callback1)
        handler.on_order_update(callback2)

        payload = {"orderId": "123"}
        await handler._dispatch("order_update", payload)

        callback1.assert_called_once_with(payload)
        callback2.assert_called_once_with(payload)

    async def test_dispatch_handles_callback_error(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should handle callback errors gracefully."""
        callback1 = MagicMock(side_effect=Exception("Callback error"))
        callback2 = MagicMock()
        handler.on_order_update(callback1)
        handler.on_order_update(callback2)

        payload = {"orderId": "123"}
        # Should not raise
        await handler._dispatch("order_update", payload)

        # Second callback should still be called
        callback2.assert_called_once_with(payload)

    async def test_reconnect_with_backoff(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should reconnect with exponential backoff."""
        handler._running = True
        handler._reconnect_count = 0

        # Mock connect to fail
        handler.connect = AsyncMock(side_effect=Exception("Connection failed"))
        handler.subscribe_user_data = AsyncMock()

        # Start reconnect (will fail and try again)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Set max attempts to stop after first try
            handler.config.max_reconnect_attempts = 1
            await handler._reconnect()

        # Should have tried to sleep
        assert mock_sleep.called

    async def test_reconnect_stops_at_max_attempts(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should stop reconnecting after max attempts."""
        handler._running = True
        handler._reconnect_count = handler.config.max_reconnect_attempts

        await handler._reconnect()

        assert handler._running is False


@pytest.mark.asyncio
class TestWebSocketManager:
    """Tests for WebSocketManager class."""

    @pytest.fixture
    def manager(self) -> WebSocketManager:
        """Create WebSocket manager."""
        return WebSocketManager()

    async def test_manager_connect_binance(
        self, manager: WebSocketManager
    ) -> None:
        """Should connect to Binance WebSocket."""
        mock_handler = MagicMock()
        mock_handler.connect = AsyncMock()
        mock_handler.subscribe_user_data = AsyncMock()

        with patch(
            "bot.exchange.websocket_manager.BinanceWebSocket",
            return_value=mock_handler,
        ):
            with patch("api.core.config.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    exchange_rest_timeout_seconds=10
                )
                await manager.connect(
                    exchange_id="binance",
                    api_key="test_key",
                    api_secret="test_secret",
                    testnet=True,
                )

        assert "binance" in manager._handlers
        mock_handler.connect.assert_called_once()
        mock_handler.subscribe_user_data.assert_called_once()

    async def test_manager_connect_bybit(
        self, manager: WebSocketManager
    ) -> None:
        """Should connect to Bybit WebSocket."""
        mock_handler = MagicMock()
        mock_handler.connect = AsyncMock()
        mock_handler.subscribe_user_data = AsyncMock()

        with patch(
            "bot.exchange.websocket_manager.BybitWebSocket",
            return_value=mock_handler,
        ):
            with patch("api.core.config.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    exchange_rest_timeout_seconds=10
                )
                await manager.connect(
                    exchange_id="bybit",
                    api_key="test_key",
                    api_secret="test_secret",
                )

        assert "bybit" in manager._handlers

    async def test_manager_connect_unsupported_exchange(
        self, manager: WebSocketManager
    ) -> None:
        """Should log warning for unsupported exchange."""
        with patch("api.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                exchange_rest_timeout_seconds=10
            )
            await manager.connect(
                exchange_id="unknown_exchange",
                api_key="test_key",
                api_secret="test_secret",
            )

        assert "unknown_exchange" not in manager._handlers

    async def test_manager_disconnect_specific(
        self, manager: WebSocketManager
    ) -> None:
        """Should disconnect specific exchange."""
        mock_handler = MagicMock()
        mock_handler.disconnect = AsyncMock()
        manager._handlers["binance"] = mock_handler

        await manager.disconnect("binance")

        mock_handler.disconnect.assert_called_once()
        assert "binance" not in manager._handlers

    async def test_manager_disconnect_all(
        self, manager: WebSocketManager
    ) -> None:
        """Should disconnect all exchanges."""
        mock_handler1 = MagicMock()
        mock_handler1.disconnect = AsyncMock()
        mock_handler2 = MagicMock()
        mock_handler2.disconnect = AsyncMock()

        manager._handlers["binance"] = mock_handler1
        manager._handlers["bybit"] = mock_handler2

        await manager.disconnect()

        mock_handler1.disconnect.assert_called_once()
        mock_handler2.disconnect.assert_called_once()
        assert len(manager._handlers) == 0

    def test_manager_on_order_update_all_exchanges(
        self, manager: WebSocketManager
    ) -> None:
        """Should register callback for all exchanges."""
        mock_handler1 = MagicMock()
        mock_handler2 = MagicMock()
        manager._handlers["binance"] = mock_handler1
        manager._handlers["bybit"] = mock_handler2

        callback = MagicMock()
        manager.on_order_update(callback)

        mock_handler1.on_order_update.assert_called_once_with(callback)
        mock_handler2.on_order_update.assert_called_once_with(callback)

    def test_manager_on_order_update_specific_exchange(
        self, manager: WebSocketManager
    ) -> None:
        """Should register callback for specific exchange."""
        mock_handler1 = MagicMock()
        mock_handler2 = MagicMock()
        manager._handlers["binance"] = mock_handler1
        manager._handlers["bybit"] = mock_handler2

        callback = MagicMock()
        manager.on_order_update(callback, exchange_id="binance")

        mock_handler1.on_order_update.assert_called_once_with(callback)
        mock_handler2.on_order_update.assert_not_called()

    def test_manager_is_connected(
        self, manager: WebSocketManager
    ) -> None:
        """Should check connection status."""
        mock_handler = MagicMock()
        mock_handler._running = True
        manager._handlers["binance"] = mock_handler

        assert manager.is_connected("binance") is True
        assert manager.is_connected("bybit") is False

    def test_manager_connected_exchanges(
        self, manager: WebSocketManager
    ) -> None:
        """Should return list of connected exchanges."""
        mock_handler1 = MagicMock()
        mock_handler1._running = True
        mock_handler2 = MagicMock()
        mock_handler2._running = False

        manager._handlers["binance"] = mock_handler1
        manager._handlers["bybit"] = mock_handler2

        connected = manager.connected_exchanges

        assert "binance" in connected
        assert "bybit" not in connected


@pytest.mark.asyncio
class TestWebSocketListenLoop:
    """Tests for the listen loop functionality."""

    @pytest.fixture
    def config(self) -> WebSocketConfig:
        """Create test config."""
        return WebSocketConfig(
            api_key="test_key",
            api_secret="test_secret",
            ping_interval=1,
        )

    @pytest.fixture
    def handler(self, config: WebSocketConfig) -> BinanceWebSocket:
        """Create handler for testing."""
        return BinanceWebSocket(config)

    async def test_listen_handles_text_message(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should handle text messages in listen loop."""
        handler._running = True

        # Create mock message
        mock_msg = MagicMock()
        mock_msg.type = WSMsgType.TEXT
        mock_msg.data = json.dumps({"e": "unknown"})

        mock_ws = AsyncMock()
        mock_ws.closed = False

        # Return message once then close
        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_msg
            handler._running = False
            mock_ws.closed = True
            raise asyncio.TimeoutError()

        mock_ws.receive = receive_side_effect
        mock_ws.ping = AsyncMock()

        handler._ws = mock_ws
        handler._reconnect = AsyncMock()

        await handler._listen()

    async def test_listen_handles_ping(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should respond to ping with pong."""
        handler._running = True

        # Create mock ping message
        mock_msg = MagicMock()
        mock_msg.type = WSMsgType.PING

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.pong = AsyncMock()

        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_msg
            handler._running = False
            mock_ws.closed = True
            raise asyncio.TimeoutError()

        mock_ws.receive = receive_side_effect
        mock_ws.ping = AsyncMock()

        handler._ws = mock_ws
        handler._reconnect = AsyncMock()

        await handler._listen()

        mock_ws.pong.assert_called_once()

    async def test_listen_handles_close(
        self, handler: BinanceWebSocket
    ) -> None:
        """Should handle WebSocket close message."""
        handler._running = True

        # Create mock close message
        mock_msg = MagicMock()
        mock_msg.type = WSMsgType.CLOSED

        mock_ws = AsyncMock()
        mock_ws.closed = False

        async def receive_side_effect():
            return mock_msg

        mock_ws.receive = receive_side_effect

        handler._ws = mock_ws
        handler._reconnect = AsyncMock()

        await handler._listen()

        # Should trigger reconnect
        handler._reconnect.assert_called_once()
