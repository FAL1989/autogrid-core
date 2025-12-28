"""
Unit Tests for Bot Service.

Tests for bot CRUD operations and state management.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import Bot, ExchangeCredential, User
from api.services.bot_service import BotService


@pytest.mark.asyncio
class TestBotService:
    """Tests for BotService."""

    async def test_create_bot_success(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Bot should be created with valid data."""
        bot_service = BotService(db_session)

        bot = await bot_service.create(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="My Grid Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={
                "lower_price": 45000.0,
                "upper_price": 55000.0,
                "grid_count": 10,
                "investment": 1000.0,
            },
        )

        assert bot.id is not None
        assert bot.name == "My Grid Bot"
        assert bot.strategy == "grid"
        assert bot.exchange == "binance"
        assert bot.symbol == "BTC/USDT"
        assert bot.status == "stopped"
        assert bot.user_id == test_user.id
        assert bot.credential_id == test_credential.id

    async def test_get_by_id(
        self,
        db_session: AsyncSession,
        test_bot: Bot,
    ) -> None:
        """Bot should be retrievable by ID."""
        bot_service = BotService(db_session)

        bot = await bot_service.get_by_id(test_bot.id)

        assert bot is not None
        assert bot.id == test_bot.id
        assert bot.name == test_bot.name

    async def test_get_by_id_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Non-existent bot should return None."""
        bot_service = BotService(db_session)

        bot = await bot_service.get_by_id(uuid4())

        assert bot is None

    async def test_get_by_id_for_user_success(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bot: Bot,
    ) -> None:
        """Bot should be retrievable when owned by user."""
        bot_service = BotService(db_session)

        bot = await bot_service.get_by_id_for_user(test_bot.id, test_user.id)

        assert bot is not None
        assert bot.id == test_bot.id

    async def test_get_by_id_for_user_wrong_owner(
        self,
        db_session: AsyncSession,
        test_bot: Bot,
    ) -> None:
        """Bot should not be retrievable by different user."""
        bot_service = BotService(db_session)

        bot = await bot_service.get_by_id_for_user(test_bot.id, uuid4())

        assert bot is None

    async def test_list_by_user_empty(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Empty list should be returned when user has no bots."""
        bot_service = BotService(db_session)

        bots, total = await bot_service.list_by_user(test_user.id)

        assert bots == []
        assert total == 0

    async def test_list_by_user_with_bots(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bot: Bot,
    ) -> None:
        """User's bots should be listed."""
        bot_service = BotService(db_session)

        bots, total = await bot_service.list_by_user(test_user.id)

        assert len(bots) == 1
        assert total == 1
        assert bots[0].id == test_bot.id

    async def test_list_by_user_pagination(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bot: Bot,
        running_bot: Bot,
    ) -> None:
        """Pagination should work correctly."""
        bot_service = BotService(db_session)

        # Get first page (limit 1)
        bots, total = await bot_service.list_by_user(test_user.id, limit=1, offset=0)

        assert len(bots) == 1
        assert total == 2

        # Get second page
        bots2, total2 = await bot_service.list_by_user(test_user.id, limit=1, offset=1)

        assert len(bots2) == 1
        assert total2 == 2
        assert bots[0].id != bots2[0].id

    async def test_update_status_success(
        self,
        db_session: AsyncSession,
        test_bot: Bot,
    ) -> None:
        """Bot status should be updated."""
        bot_service = BotService(db_session)

        result = await bot_service.update_status(test_bot.id, "running")

        assert result is True

        # Verify the update
        bot = await bot_service.get_by_id(test_bot.id)
        assert bot is not None
        assert bot.status == "running"

    async def test_update_status_with_error(
        self,
        db_session: AsyncSession,
        test_bot: Bot,
    ) -> None:
        """Bot status with error message should be updated."""
        bot_service = BotService(db_session)

        result = await bot_service.update_status(
            test_bot.id, "error", error_message="Connection failed"
        )

        assert result is True

        bot = await bot_service.get_by_id(test_bot.id)
        assert bot is not None
        assert bot.status == "error"
        assert bot.error_message == "Connection failed"

    async def test_update_status_not_found(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Updating non-existent bot should return False."""
        bot_service = BotService(db_session)

        result = await bot_service.update_status(uuid4(), "running")

        assert result is False

    async def test_get_credential_for_user_success(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Credential should be retrievable when owned by user."""
        bot_service = BotService(db_session)

        credential = await bot_service.get_credential_for_user(
            test_credential.id, test_user.id
        )

        assert credential is not None
        assert credential.id == test_credential.id
        assert credential.exchange == "binance"

    async def test_get_credential_for_user_wrong_owner(
        self,
        db_session: AsyncSession,
        test_credential: ExchangeCredential,
    ) -> None:
        """Credential should not be retrievable by different user."""
        bot_service = BotService(db_session)

        credential = await bot_service.get_credential_for_user(
            test_credential.id, uuid4()
        )

        assert credential is None

    async def test_get_credential_for_user_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Non-existent credential should return None."""
        bot_service = BotService(db_session)

        credential = await bot_service.get_credential_for_user(uuid4(), test_user.id)

        assert credential is None

    async def test_delete_success(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_bot: Bot,
    ) -> None:
        """Bot should be deleted successfully."""
        bot_service = BotService(db_session)

        result = await bot_service.delete(test_bot.id, test_user.id)

        assert result is True

        # Verify deletion
        bot = await bot_service.get_by_id(test_bot.id)
        assert bot is None

    async def test_delete_wrong_owner(
        self,
        db_session: AsyncSession,
        test_bot: Bot,
    ) -> None:
        """Deleting bot by wrong user should fail."""
        bot_service = BotService(db_session)

        result = await bot_service.delete(test_bot.id, uuid4())

        assert result is False

        # Verify bot still exists
        bot = await bot_service.get_by_id(test_bot.id)
        assert bot is not None

    async def test_delete_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Deleting non-existent bot should return False."""
        bot_service = BotService(db_session)

        result = await bot_service.delete(uuid4(), test_user.id)

        assert result is False


@pytest.mark.asyncio
class TestBotStateTransitions:
    """Tests for bot state management."""

    async def test_start_stopped_bot(
        self,
        db_session: AsyncSession,
        test_bot: Bot,
    ) -> None:
        """Stopped bot should be startable."""
        bot_service = BotService(db_session)

        assert test_bot.status == "stopped"

        result = await bot_service.update_status(test_bot.id, "running")

        assert result is True
        bot = await bot_service.get_by_id(test_bot.id)
        assert bot is not None
        assert bot.status == "running"

    async def test_stop_running_bot(
        self,
        db_session: AsyncSession,
        running_bot: Bot,
    ) -> None:
        """Running bot should be stoppable."""
        bot_service = BotService(db_session)

        assert running_bot.status == "running"

        result = await bot_service.update_status(running_bot.id, "stopped")

        assert result is True
        bot = await bot_service.get_by_id(running_bot.id)
        assert bot is not None
        assert bot.status == "stopped"

    async def test_pause_running_bot(
        self,
        db_session: AsyncSession,
        running_bot: Bot,
    ) -> None:
        """Running bot should be pausable."""
        bot_service = BotService(db_session)

        result = await bot_service.update_status(running_bot.id, "paused")

        assert result is True
        bot = await bot_service.get_by_id(running_bot.id)
        assert bot is not None
        assert bot.status == "paused"

    async def test_set_error_status(
        self,
        db_session: AsyncSession,
        running_bot: Bot,
    ) -> None:
        """Bot should be able to enter error state."""
        bot_service = BotService(db_session)

        result = await bot_service.update_status(
            running_bot.id, "error", error_message="Rate limit exceeded"
        )

        assert result is True
        bot = await bot_service.get_by_id(running_bot.id)
        assert bot is not None
        assert bot.status == "error"
        assert bot.error_message == "Rate limit exceeded"
