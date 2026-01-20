"""
Engine runtime supervisor.

Runs trading bots using the engine loop instead of Celery ticks.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.core.config import get_settings
from api.models.orm import Bot
from bot.tasks import (
    _rehydrate_running_bots,
    _running_bots,
    _start_bot_async,
    _stop_bot_async,
    _tick_bot_async,
    _update_bot_status,
)

logger = logging.getLogger(__name__)


class EngineSupervisor:
    """Supervises bot engine loops for all running bots."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.tick_interval = self.settings.engine_tick_interval_seconds
        self.supervisor_interval = self.settings.engine_supervisor_interval_seconds
        self._shutdown = asyncio.Event()
        self._tasks: dict[str, asyncio.Task] = {}

    def request_shutdown(self) -> None:
        """Signal shutdown for the supervisor."""
        self._shutdown.set()

    async def run(self) -> None:
        """Main supervisor loop."""
        await self._startup()

        while not self._shutdown.is_set():
            try:
                await self._sync_bots()
            except Exception as exc:
                logger.error("Engine supervisor sync failed: %s", exc)
            await asyncio.sleep(self.supervisor_interval)

        await self._shutdown_all()

    async def _startup(self) -> None:
        """Load running bots and start loops."""
        await _rehydrate_running_bots()
        for bot_id in list(_running_bots.keys()):
            self._ensure_task(bot_id)

    async def _sync_bots(self) -> None:
        """Start/stop bots based on database status."""
        statuses = await self._fetch_bot_statuses()
        target_running = {
            bot_id
            for bot_id, status in statuses.items()
            if status in ("running", "starting")
        }

        for bot_id in target_running:
            if bot_id not in _running_bots:
                status = statuses.get(bot_id)
                rehydrate = status == "running"
                try:
                    result = await _start_bot_async(
                        bot_id,
                        rehydrate=rehydrate,
                        broadcast=not rehydrate,
                    )
                except Exception as exc:
                    logger.error("Failed to start bot %s: %s", bot_id, exc)
                    await _update_bot_status(bot_id, "error", str(exc))
                    continue

                if result.get("status") not in ("running", "already_running"):
                    logger.warning("Bot %s did not start: %s", bot_id, result)
                    continue

            self._ensure_task(bot_id)

        for bot_id in list(_running_bots.keys()):
            if bot_id not in target_running:
                await self._stop_bot(bot_id, reason="status_change")

    async def _fetch_bot_statuses(self) -> dict[str, str]:
        """Load bot statuses from the database."""
        engine = create_async_engine(self.settings.async_database_url)
        async_session = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session() as db:
            result = await db.execute(select(Bot.id, Bot.status))
            rows = result.all()

        await engine.dispose()

        return {str(row[0]): str(row[1]) for row in rows}

    def _ensure_task(self, bot_id: str) -> None:
        """Ensure a bot loop task is running."""
        task = self._tasks.get(bot_id)
        if task and not task.done():
            return

        self._tasks[bot_id] = asyncio.create_task(
            self._bot_loop(bot_id),
            name=f"bot-loop-{bot_id}",
        )

    async def _bot_loop(self, bot_id: str) -> None:
        """Run the engine tick loop for a single bot."""
        while True:
            bot_data = _running_bots.get(bot_id)
            if not bot_data:
                return

            try:
                await _tick_bot_async(bot_id, bot_data)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("Engine tick failed for bot %s: %s", bot_id, exc)
                await _update_bot_status(bot_id, "error", str(exc))
                await _stop_bot_async(
                    bot_id,
                    source="engine_runtime",
                    reason=str(exc),
                    metadata={"runtime": "engine"},
                )
                return

            await asyncio.sleep(self.tick_interval)

    async def _stop_bot(self, bot_id: str, reason: str) -> None:
        """Stop a running bot and cancel its loop."""
        await _stop_bot_async(
            bot_id,
            source="engine_runtime",
            reason=reason,
            metadata={"runtime": "engine"},
        )

        task = self._tasks.pop(bot_id, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _shutdown_all(self) -> None:
        """Stop all running bots on shutdown."""
        for bot_id in list(_running_bots.keys()):
            await self._stop_bot(bot_id, reason="shutdown")


async def main() -> None:
    """Entry point for engine runtime."""
    settings = get_settings()
    if settings.bot_runtime_mode.lower() != "engine":
        logger.warning(
            "BOT_RUNTIME_MODE=%s; engine runner exiting",
            settings.bot_runtime_mode,
        )
        return

    supervisor = EngineSupervisor()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, supervisor.request_shutdown)

    await supervisor.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
