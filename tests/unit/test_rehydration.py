"""
Tests for bot rehydration functionality.

These tests validate the behavior of bot rehydration after worker restart.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestMaybeRehydrateRunningBots:
    """Tests for _maybe_rehydrate_running_bots function."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self):
        """Reset global state before each test."""
        import bot.tasks as tasks_module

        tasks_module._rehydrate_attempted = False
        tasks_module._running_bots = {}
        yield
        tasks_module._rehydrate_attempted = False
        tasks_module._running_bots = {}

    @pytest.mark.asyncio
    async def test_rehydrate_sets_attempted_flag(self):
        """Test that _maybe_rehydrate_running_bots sets _rehydrate_attempted flag."""
        import bot.tasks as tasks_module

        # Mock _rehydrate_running_bots to avoid DB access
        with patch.object(
            tasks_module,
            "_rehydrate_running_bots",
            new_callable=AsyncMock,
            return_value={"status": "ok", "rehydrated": 0},
        ):
            # Flag should be False initially
            assert tasks_module._rehydrate_attempted is False

            # Call the function
            result = await tasks_module._maybe_rehydrate_running_bots()

            # Flag should be True after call
            assert tasks_module._rehydrate_attempted is True
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_rehydrate_skips_if_already_attempted(self):
        """Test that _maybe_rehydrate_running_bots skips if already attempted."""
        import bot.tasks as tasks_module

        # Set flag to True (simulating already attempted)
        tasks_module._rehydrate_attempted = True

        # Create a mock that should NOT be called
        mock_rehydrate = AsyncMock(return_value={"status": "ok", "rehydrated": 1})
        with patch.object(tasks_module, "_rehydrate_running_bots", mock_rehydrate):
            result = await tasks_module._maybe_rehydrate_running_bots()

            # Should return skipped without calling _rehydrate_running_bots
            assert result["status"] == "skipped"
            assert result["rehydrated"] == 0
            mock_rehydrate.assert_not_called()

    @pytest.mark.asyncio
    async def test_rehydrate_resets_flag_on_error(self):
        """Test that flag is reset if rehydration fails."""
        import bot.tasks as tasks_module

        # Mock _rehydrate_running_bots to raise an error
        with patch.object(
            tasks_module,
            "_rehydrate_running_bots",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection failed"),
        ):
            assert tasks_module._rehydrate_attempted is False

            with pytest.raises(Exception, match="DB connection failed"):
                await tasks_module._maybe_rehydrate_running_bots()

            # Flag should be reset to False on error
            assert tasks_module._rehydrate_attempted is False


class TestRehydrateRunningBots:
    """Tests for _rehydrate_running_bots function."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self):
        """Reset global state before each test."""
        import bot.tasks as tasks_module

        tasks_module._rehydrate_attempted = False
        tasks_module._running_bots = {}
        yield
        tasks_module._rehydrate_attempted = False
        tasks_module._running_bots = {}

    @pytest.mark.asyncio
    async def test_rehydrate_loads_running_bots_from_db(self):
        """Test that rehydration loads bots with status='running' from DB."""
        import bot.tasks as tasks_module

        bot_id_1 = str(uuid4())
        bot_id_2 = str(uuid4())

        # Mock DB to return 2 running bots
        mock_result = MagicMock()
        mock_result.all.return_value = [(bot_id_1,), (bot_id_2,)]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.close = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        # Mock _start_bot_async to track calls
        start_calls = []

        async def mock_start_bot(bot_id, rehydrate=False, broadcast=True):
            start_calls.append(
                {"bot_id": bot_id, "rehydrate": rehydrate, "broadcast": broadcast}
            )
            return {"status": "running"}

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ):
            with patch(
                "sqlalchemy.orm.sessionmaker", return_value=lambda: mock_session
            ):
                with patch.object(
                    tasks_module, "_start_bot_async", side_effect=mock_start_bot
                ):
                    result = await tasks_module._rehydrate_running_bots()

        # Should have called _start_bot_async for each bot
        assert len(start_calls) == 2
        assert start_calls[0]["bot_id"] == bot_id_1
        assert start_calls[0]["rehydrate"] is True
        assert start_calls[0]["broadcast"] is False
        assert start_calls[1]["bot_id"] == bot_id_2
        assert result["status"] == "ok"
        assert result["rehydrated"] == 2

    @pytest.mark.asyncio
    async def test_rehydrate_skips_already_running_bots(self):
        """Test that rehydration skips bots already in _running_bots."""
        import bot.tasks as tasks_module

        bot_id_existing = str(uuid4())
        bot_id_new = str(uuid4())

        # Pre-populate _running_bots with one bot
        tasks_module._running_bots[bot_id_existing] = {"status": "running"}

        # Mock DB to return both bots
        mock_result = MagicMock()
        mock_result.all.return_value = [(bot_id_existing,), (bot_id_new,)]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.close = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        start_calls = []

        async def mock_start_bot(bot_id, rehydrate=False, broadcast=True):
            start_calls.append(bot_id)
            return {"status": "running"}

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ):
            with patch(
                "sqlalchemy.orm.sessionmaker", return_value=lambda: mock_session
            ):
                with patch.object(
                    tasks_module, "_start_bot_async", side_effect=mock_start_bot
                ):
                    result = await tasks_module._rehydrate_running_bots()

        # Should only call _start_bot_async for the new bot
        assert len(start_calls) == 1
        assert start_calls[0] == bot_id_new
        assert result["rehydrated"] == 1

    @pytest.mark.asyncio
    async def test_rehydrate_handles_invalid_credentials(self):
        """Test that rehydration handles bots with invalid credentials."""
        import bot.tasks as tasks_module

        bot_id = str(uuid4())

        mock_result = MagicMock()
        mock_result.all.return_value = [(bot_id,)]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.close = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        # Mock _start_bot_async to return error status
        async def mock_start_bot(bot_id, rehydrate=False, broadcast=True):
            return {"status": "error", "error": "Invalid credentials"}

        with patch(
            "sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine
        ):
            with patch(
                "sqlalchemy.orm.sessionmaker", return_value=lambda: mock_session
            ):
                with patch.object(
                    tasks_module, "_start_bot_async", side_effect=mock_start_bot
                ):
                    result = await tasks_module._rehydrate_running_bots()

        # Bot with error should not be counted as rehydrated
        assert result["rehydrated"] == 0
        assert result["status"] == "ok"
