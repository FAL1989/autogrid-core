"""
Tests for trade reconciliation functionality.

These tests validate trade reconciliation with exchange.
All exchange calls are mocked - no network access.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestReconcileRunningBotsTrades:
    """Tests for reconcile_running_bots_trades task."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self):
        """Reset global state before each test."""
        import bot.tasks as tasks_module

        tasks_module._running_bots = {}
        yield
        tasks_module._running_bots = {}

    def test_reconciles_all_running_bots(self):
        """Test that reconciliation runs for all bots in _running_bots."""
        import bot.tasks as tasks_module

        bot_id_1 = str(uuid4())
        bot_id_2 = str(uuid4())

        # Add bots to _running_bots
        tasks_module._running_bots[bot_id_1] = {"status": "running"}
        tasks_module._running_bots[bot_id_2] = {"status": "running"}

        reconcile_calls = []

        async def mock_reconcile(bot_id, since_minutes=1440, limit=100):
            reconcile_calls.append(bot_id)
            return {"status": "ok", "created": 1, "skipped": 0}

        def run_coro(coro):
            loop = tasks_module.asyncio.get_event_loop()
            return loop.run_until_complete(coro)

        with patch.object(
            tasks_module, "_reconcile_bot_trades_async", side_effect=mock_reconcile
        ):
            with patch.object(tasks_module, "_run_async", side_effect=run_coro):
                result = tasks_module.reconcile_running_bots_trades()

        assert len(reconcile_calls) == 2
        assert bot_id_1 in reconcile_calls
        assert bot_id_2 in reconcile_calls
        assert result["created"] == 2
        assert result["status"] == "ok"

    def test_reconciles_recent_bots_when_running_bots_empty(self):
        """Test that recent bots are fetched when _running_bots is empty."""
        import bot.tasks as tasks_module

        bot_id = str(uuid4())

        async def mock_list_recent():
            return [bot_id]

        async def mock_reconcile(bot_id, since_minutes=1440, limit=100):
            return {"status": "ok", "created": 1, "skipped": 0}

        def run_coro(coro):
            loop = tasks_module.asyncio.get_event_loop()
            return loop.run_until_complete(coro)

        with patch.object(
            tasks_module, "_list_recent_bot_ids_async", side_effect=mock_list_recent
        ):
            with patch.object(
                tasks_module, "_reconcile_bot_trades_async", side_effect=mock_reconcile
            ):
                with patch.object(tasks_module, "_run_async", side_effect=run_coro):
                    result = tasks_module.reconcile_running_bots_trades()

        assert result["created"] == 1
        assert result["status"] == "ok"

    def test_handles_reconcile_error_gracefully(self):
        """Test that errors in reconciliation are handled gracefully."""
        import bot.tasks as tasks_module

        bot_id_1 = str(uuid4())
        bot_id_2 = str(uuid4())

        tasks_module._running_bots[bot_id_1] = {"status": "running"}
        tasks_module._running_bots[bot_id_2] = {"status": "running"}

        call_count = 0

        async def mock_reconcile(bot_id, since_minutes=1440, limit=100):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Exchange error")
            return {"status": "ok", "created": 1, "skipped": 0}

        def run_coro(coro):
            loop = tasks_module.asyncio.get_event_loop()
            return loop.run_until_complete(coro)

        with patch.object(
            tasks_module, "_reconcile_bot_trades_async", side_effect=mock_reconcile
        ):
            with patch.object(tasks_module, "_run_async", side_effect=run_coro):
                result = tasks_module.reconcile_running_bots_trades()

        # One error, one success
        assert result["errors"] == 1
        assert result["created"] == 1
        assert result["status"] == "ok"

    def test_aggregates_results_from_all_bots(self):
        """Test that results are aggregated correctly."""
        import bot.tasks as tasks_module

        bot_id_1 = str(uuid4())
        bot_id_2 = str(uuid4())

        tasks_module._running_bots[bot_id_1] = {"status": "running"}
        tasks_module._running_bots[bot_id_2] = {"status": "running"}

        results = [
            {"status": "ok", "created": 3, "skipped": 2},
            {"status": "ok", "created": 1, "skipped": 5},
        ]
        result_idx = [0]

        async def mock_reconcile(bot_id, since_minutes=1440, limit=100):
            r = results[result_idx[0]]
            result_idx[0] += 1
            return r

        def run_coro(coro):
            loop = tasks_module.asyncio.get_event_loop()
            return loop.run_until_complete(coro)

        with patch.object(
            tasks_module, "_reconcile_bot_trades_async", side_effect=mock_reconcile
        ):
            with patch.object(tasks_module, "_run_async", side_effect=run_coro):
                result = tasks_module.reconcile_running_bots_trades()

        assert result["created"] == 4  # 3 + 1
        assert result["skipped"] == 7  # 2 + 5


class TestReconcileBotTradesAsync:
    """Tests for _reconcile_bot_trades_async function."""

    @pytest.mark.asyncio
    async def test_creates_missing_trades(self):
        """Test that missing trades are created from exchange data."""
        import bot.tasks as tasks_module

        bot_id = uuid4()
        order_id = uuid4()

        # Mock bot
        mock_bot = MagicMock()
        mock_bot.id = bot_id
        mock_bot.credential_id = uuid4()
        mock_bot.symbol = "BTC/USDT"
        mock_bot.status = "running"
        mock_bot.realized_pnl = Decimal("0")

        # Mock credential
        mock_credential = MagicMock()
        mock_credential.exchange = "binance"
        mock_credential.is_testnet = True

        # Mock order
        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.exchange_order_id = "exchange_order_123"
        mock_order.side = "buy"
        mock_order.quantity = Decimal("0.1")
        mock_order.filled_quantity = Decimal("0")
        mock_order.status = "open"

        # Exchange trade data
        exchange_trades = [
            {
                "id": "trade_1",
                "order": "exchange_order_123",
                "side": "buy",
                "price": 50000,
                "amount": 0.1,
                "fee": {"cost": 0.5, "currency": "USDT"},
                "timestamp": 1704067200000,
            }
        ]

        # Mock DB session
        mock_db = AsyncMock()

        # Bot query
        mock_bot_result = MagicMock()
        mock_bot_result.scalar_one_or_none.return_value = mock_bot

        # Credential query
        mock_db.get = AsyncMock(return_value=mock_credential)

        # Orders query
        mock_orders_result = MagicMock()
        mock_orders_scalars = MagicMock()
        mock_orders_scalars.all.return_value = [mock_order]
        mock_orders_result.scalars.return_value = mock_orders_scalars

        # Trade exists queries (return None - trade doesn't exist)
        mock_no_trade = MagicMock()
        mock_no_trade.scalar_one_or_none.return_value = None

        # For sum query
        mock_sum_result = MagicMock()
        mock_sum_result.scalar_one.return_value = Decimal("0")

        # Configure execute to return different mocks for different queries
        execute_returns = [
            mock_bot_result,  # Bot query
            mock_orders_result,  # Orders query
            mock_no_trade,  # Trade by exchange_trade_id
            mock_no_trade,  # Trade by order_id/price/qty
            MagicMock(all=MagicMock(return_value=[])),  # totals query
            mock_sum_result,  # realized_pnl sum
        ]
        execute_idx = [0]

        async def mock_execute(query):
            idx = execute_idx[0]
            execute_idx[0] += 1
            if idx < len(execute_returns):
                return execute_returns[idx]
            return mock_no_trade

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        # Mock connector
        mock_connector = MagicMock()
        mock_connector.connect = AsyncMock()
        mock_connector.disconnect = AsyncMock()
        mock_connector.fetch_my_trades = AsyncMock(return_value=exchange_trades)

        # Mock credential service
        mock_cred_service = MagicMock()
        mock_cred_service.get_decrypted_keys.return_value = ("api_key", "api_secret")

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                with patch(
                    "bot.exchange.connector.CCXTConnector", return_value=mock_connector
                ):
                    with patch(
                        "api.services.credential_service.CredentialService",
                        return_value=mock_cred_service,
                    ):
                        result = await tasks_module._reconcile_bot_trades_async(
                            str(bot_id)
                        )

        # Should have created 1 trade
        assert result["created"] == 1
        assert result["status"] == "ok"
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_skips_existing_trade_by_exchange_id(self):
        """Test that trades with existing exchange_trade_id are skipped."""
        import bot.tasks as tasks_module

        bot_id = uuid4()
        order_id = uuid4()

        mock_bot = MagicMock()
        mock_bot.id = bot_id
        mock_bot.credential_id = uuid4()
        mock_bot.symbol = "BTC/USDT"
        mock_bot.status = "running"
        mock_bot.realized_pnl = Decimal("0")

        mock_credential = MagicMock()
        mock_credential.exchange = "binance"
        mock_credential.is_testnet = True

        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.exchange_order_id = "exchange_order_123"
        mock_order.side = "buy"
        mock_order.quantity = Decimal("0.1")

        # Exchange trade data
        exchange_trades = [
            {
                "id": "existing_trade_id",
                "order": "exchange_order_123",
                "side": "buy",
                "price": 50000,
                "amount": 0.1,
                "timestamp": 1704067200000,
            }
        ]

        # Existing trade in DB
        mock_existing_trade = MagicMock()
        mock_existing_trade.realized_pnl = Decimal("100")  # Already has PnL

        mock_db = AsyncMock()

        mock_bot_result = MagicMock()
        mock_bot_result.scalar_one_or_none.return_value = mock_bot
        mock_db.get = AsyncMock(return_value=mock_credential)

        mock_orders_result = MagicMock()
        mock_orders_scalars = MagicMock()
        mock_orders_scalars.all.return_value = [mock_order]
        mock_orders_result.scalars.return_value = mock_orders_scalars

        # Trade exists by exchange_trade_id
        mock_trade_exists = MagicMock()
        mock_trade_exists.scalar_one_or_none.return_value = mock_existing_trade

        mock_sum_result = MagicMock()
        mock_sum_result.scalar_one.return_value = Decimal("100")

        execute_returns = [
            mock_bot_result,
            mock_orders_result,
            mock_trade_exists,  # Trade found by exchange_trade_id
            mock_sum_result,
        ]
        execute_idx = [0]

        async def mock_execute(query):
            idx = execute_idx[0]
            execute_idx[0] += 1
            if idx < len(execute_returns):
                return execute_returns[idx]
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_connector = MagicMock()
        mock_connector.connect = AsyncMock()
        mock_connector.disconnect = AsyncMock()
        mock_connector.fetch_my_trades = AsyncMock(return_value=exchange_trades)

        mock_cred_service = MagicMock()
        mock_cred_service.get_decrypted_keys.return_value = ("api_key", "api_secret")

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                with patch(
                    "bot.exchange.connector.CCXTConnector", return_value=mock_connector
                ):
                    with patch(
                        "api.services.credential_service.CredentialService",
                        return_value=mock_cred_service,
                    ):
                        result = await tasks_module._reconcile_bot_trades_async(
                            str(bot_id)
                        )

        # Trade should be skipped
        assert result["skipped"] == 1
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_skips_trade_without_order_match(self):
        """Test that trades without matching order are skipped."""
        import bot.tasks as tasks_module

        bot_id = uuid4()

        mock_bot = MagicMock()
        mock_bot.id = bot_id
        mock_bot.credential_id = uuid4()
        mock_bot.symbol = "BTC/USDT"
        mock_bot.status = "running"
        mock_bot.realized_pnl = Decimal("0")

        mock_credential = MagicMock()
        mock_credential.exchange = "binance"
        mock_credential.is_testnet = True

        # Exchange trade with no matching order
        exchange_trades = [
            {
                "id": "trade_1",
                "order": "unknown_order_id",
                "side": "buy",
                "price": 50000,
                "amount": 0.1,
                "timestamp": 1704067200000,
            }
        ]

        mock_db = AsyncMock()

        mock_bot_result = MagicMock()
        mock_bot_result.scalar_one_or_none.return_value = mock_bot
        mock_db.get = AsyncMock(return_value=mock_credential)

        # No orders match
        mock_orders_result = MagicMock()
        mock_orders_scalars = MagicMock()
        mock_orders_scalars.all.return_value = []
        mock_orders_result.scalars.return_value = mock_orders_scalars

        mock_sum_result = MagicMock()
        mock_sum_result.scalar_one.return_value = Decimal("0")

        execute_returns = [
            mock_bot_result,
            mock_orders_result,
            mock_sum_result,
        ]
        execute_idx = [0]

        async def mock_execute(query):
            idx = execute_idx[0]
            execute_idx[0] += 1
            if idx < len(execute_returns):
                return execute_returns[idx]
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_connector = MagicMock()
        mock_connector.connect = AsyncMock()
        mock_connector.disconnect = AsyncMock()
        mock_connector.fetch_my_trades = AsyncMock(return_value=exchange_trades)

        mock_cred_service = MagicMock()
        mock_cred_service.get_decrypted_keys.return_value = ("api_key", "api_secret")

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                with patch(
                    "bot.exchange.connector.CCXTConnector", return_value=mock_connector
                ):
                    with patch(
                        "api.services.credential_service.CredentialService",
                        return_value=mock_cred_service,
                    ):
                        result = await tasks_module._reconcile_bot_trades_async(
                            str(bot_id)
                        )

        # Trade should be skipped (no matching order)
        assert result["skipped"] == 1
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_returns_skipped_when_bot_not_found(self):
        """Test that reconciliation returns skipped when bot not found."""
        import bot.tasks as tasks_module

        bot_id = uuid4()

        mock_db = AsyncMock()

        # Bot not found
        mock_bot_result = MagicMock()
        mock_bot_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_bot_result)

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                result = await tasks_module._reconcile_bot_trades_async(str(bot_id))

        assert result["status"] == "skipped"
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_returns_error_when_credential_not_found(self):
        """Test that reconciliation returns error when credential not found."""
        import bot.tasks as tasks_module

        bot_id = uuid4()

        mock_bot = MagicMock()
        mock_bot.id = bot_id
        mock_bot.credential_id = uuid4()

        mock_db = AsyncMock()

        mock_bot_result = MagicMock()
        mock_bot_result.scalar_one_or_none.return_value = mock_bot

        mock_db.execute = AsyncMock(return_value=mock_bot_result)
        mock_db.get = AsyncMock(return_value=None)  # Credential not found

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                result = await tasks_module._reconcile_bot_trades_async(str(bot_id))

        assert result["status"] == "error"
        assert "Credential not found" in result.get("message", "")


class TestListRecentBotIdsAsync:
    """Tests for _list_recent_bot_ids_async function."""

    @pytest.mark.asyncio
    async def test_returns_bots_updated_within_hours(self):
        """Test that function returns bots updated within specified hours."""
        import bot.tasks as tasks_module

        bot_id_1 = uuid4()
        bot_id_2 = uuid4()

        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = [(bot_id_1,), (bot_id_2,)]

        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                result = await tasks_module._list_recent_bot_ids_async(hours=24)

        assert len(result) == 2
        assert str(bot_id_1) in result
        assert str(bot_id_2) in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_recent_bots(self):
        """Test that function returns empty list when no recent bots."""
        import bot.tasks as tasks_module

        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine:
            mock_engine.return_value.dispose = AsyncMock()
            with patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker:
                mock_session_ctx = MagicMock()
                mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
                mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
                mock_sessionmaker.return_value = lambda: mock_session_ctx

                result = await tasks_module._list_recent_bot_ids_async(hours=24)

        assert result == []
