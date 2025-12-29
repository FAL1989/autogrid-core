"""
Bot Service.

Business logic for bot operations including CRUD and state management.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import Bot, ExchangeCredential


class BotService:
    """Service for bot-related operations."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize BotService.

        Args:
            db: Async database session.
        """
        self.db = db

    async def get_by_id(self, bot_id: UUID) -> Bot | None:
        """
        Get bot by ID.

        Args:
            bot_id: The bot's UUID.

        Returns:
            Bot if found, None otherwise.
        """
        result = await self.db.execute(
            select(Bot).where(Bot.id == bot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, bot_id: UUID, user_id: UUID) -> Bot | None:
        """
        Get bot by ID, ensuring it belongs to the specified user.

        Args:
            bot_id: The bot's UUID.
            user_id: The owner's UUID.

        Returns:
            Bot if found and owned by user, None otherwise.
        """
        result = await self.db.execute(
            select(Bot).where(Bot.id == bot_id, Bot.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Bot], int]:
        """
        List all bots for a user with pagination.

        Args:
            user_id: The owner's UUID.
            limit: Maximum number of bots to return.
            offset: Number of bots to skip.

        Returns:
            Tuple of (list of bots, total count).
        """
        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(Bot).where(Bot.user_id == user_id)
        )
        total = count_result.scalar() or 0

        # Get paginated bots
        result = await self.db.execute(
            select(Bot)
            .where(Bot.user_id == user_id)
            .order_by(Bot.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        bots = list(result.scalars().all())

        return bots, total

    async def create(
        self,
        user_id: UUID,
        credential_id: UUID,
        name: str,
        strategy: str,
        exchange: str,
        symbol: str,
        config: dict,
    ) -> Bot:
        """
        Create a new bot.

        Args:
            user_id: Owner's UUID.
            credential_id: Exchange credential's UUID.
            name: Bot display name.
            strategy: Strategy type ('grid' or 'dca').
            exchange: Exchange name (e.g., 'binance').
            symbol: Trading pair (e.g., 'BTC/USDT').
            config: Strategy configuration dict.

        Returns:
            The created Bot object.
        """
        bot = Bot(
            user_id=user_id,
            credential_id=credential_id,
            name=name,
            strategy=strategy,
            exchange=exchange,
            symbol=symbol,
            config=config,
            status="stopped",
        )
        self.db.add(bot)
        await self.db.flush()
        await self.db.refresh(bot)
        return bot

    async def update_status(
        self,
        bot_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """
        Update bot status.

        Args:
            bot_id: The bot's UUID.
            status: New status ('stopped', 'running', 'paused', 'error').
            error_message: Optional error message (for 'error' status).

        Returns:
            True if updated, False if bot not found.
        """
        bot = await self.get_by_id(bot_id)

        if bot is None:
            return False

        bot.status = status
        bot.error_message = error_message
        await self.db.flush()
        return True

    async def update_pnl(
        self,
        bot_id: UUID,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal | None = None,
    ) -> bool:
        """
        Update bot P&L values.

        Called periodically by Celery tasks to sync P&L from running bots.

        Args:
            bot_id: The bot's UUID.
            realized_pnl: Total realized profit/loss.
            unrealized_pnl: Current unrealized profit/loss (optional).

        Returns:
            True if updated, False if bot not found.
        """
        stmt = (
            update(Bot)
            .where(Bot.id == bot_id)
            .values(
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl if unrealized_pnl is not None else Decimal("0"),
            )
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0

    async def get_credential_for_user(
        self,
        credential_id: UUID,
        user_id: UUID,
    ) -> ExchangeCredential | None:
        """
        Get exchange credential by ID, ensuring it belongs to the user.

        Args:
            credential_id: The credential's UUID.
            user_id: The owner's UUID.

        Returns:
            ExchangeCredential if found and owned by user, None otherwise.
        """
        result = await self.db.execute(
            select(ExchangeCredential).where(
                ExchangeCredential.id == credential_id,
                ExchangeCredential.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, bot_id: UUID, user_id: UUID) -> bool:
        """
        Delete a bot.

        Args:
            bot_id: The bot's UUID.
            user_id: The owner's UUID (for ownership verification).

        Returns:
            True if deleted, False if bot not found or not owned.
        """
        bot = await self.get_by_id_for_user(bot_id, user_id)

        if bot is None:
            return False

        await self.db.delete(bot)
        await self.db.flush()
        return True

    async def update_strategy_state(
        self,
        bot_id: UUID,
        state: dict,
    ) -> bool:
        """
        Update bot's strategy state.

        Used for persisting DCA strategy state between restarts.

        Args:
            bot_id: The bot's UUID.
            state: Strategy state dictionary.

        Returns:
            True if updated, False if bot not found.
        """
        stmt = (
            update(Bot)
            .where(Bot.id == bot_id)
            .values(strategy_state=state)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount > 0

    async def get_strategy_state(self, bot_id: UUID) -> dict | None:
        """
        Get bot's strategy state.

        Args:
            bot_id: The bot's UUID.

        Returns:
            Strategy state dict if bot found, None otherwise.
        """
        result = await self.db.execute(
            select(Bot.strategy_state).where(Bot.id == bot_id)
        )
        return result.scalar_one_or_none()
