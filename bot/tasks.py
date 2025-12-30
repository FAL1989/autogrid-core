"""
Celery Tasks for AutoGrid Bot

Background tasks for trading operations, data fetching, and scheduled jobs.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# Configure Celery
celery_app = Celery(
    "autogrid",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task (for long-running bots)
    task_soft_time_limit=3500,  # Soft limit to allow graceful shutdown
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_concurrency=1,
    worker_pool="solo",
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "check-bot-health-every-minute": {
        "task": "bot.tasks.check_bot_health",
        "schedule": 60.0,  # Every 60 seconds
    },
    "sync-market-data-every-5-minutes": {
        "task": "bot.tasks.sync_market_data",
        "schedule": 300.0,  # Every 5 minutes
    },
    "poll-mexc-orders-every-5s": {
        "task": "bot.tasks.poll_running_mexc_bots",
        "schedule": 5.0,  # Every 5 seconds
    },
    "check-circuit-breakers-every-10s": {
        "task": "bot.tasks.check_circuit_breakers",
        "schedule": 10.0,  # Every 10 seconds
    },
    "tick-running-bots-every-5s": {
        "task": "bot.tasks.tick_running_bots",
        "schedule": 5.0,  # Every 5 seconds
    },
    "sync-bot-metrics-every-30s": {
        "task": "bot.tasks.sync_running_bots_metrics",
        "schedule": 30.0,  # Every 30 seconds
    },
    "reconcile-trades-every-60s": {
        "task": "bot.tasks.reconcile_running_bots_trades",
        "schedule": 300.0,  # Every 5 minutes
    },
    "cleanup-old-data-daily": {
        "task": "bot.tasks.cleanup_old_data",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM UTC
    },
    # DCA Scheduling Tasks
    "dca-hourly-buy": {
        "task": "bot.tasks.dca_hourly_buy",
        "schedule": crontab(minute=0),  # Every hour at :00
    },
    "dca-daily-buy": {
        "task": "bot.tasks.dca_daily_buy",
        "schedule": crontab(hour=9, minute=0),  # Daily at 9:00 UTC
    },
    "dca-weekly-buy": {
        "task": "bot.tasks.dca_weekly_buy",
        "schedule": crontab(day_of_week=0, hour=9, minute=0),  # Sunday 9:00 UTC
    },
    "dca-check-price-drops-every-5m": {
        "task": "bot.tasks.dca_check_price_drops",
        "schedule": 300.0,  # Every 5 minutes
    },
    "dca-check-take-profit-every-5m": {
        "task": "bot.tasks.dca_check_take_profit",
        "schedule": 300.0,  # Every 5 minutes
    },
    "dca-save-state-every-minute": {
        "task": "bot.tasks.dca_save_strategy_state",
        "schedule": 60.0,  # Every minute
    },
}

# Registry of running bots (in-memory per worker)
_running_bots: dict[str, Any] = {}


def _run_async(coro):
    """Run async function in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# =============================================================================
# Bot Lifecycle Tasks
# =============================================================================


@celery_app.task(bind=True, max_retries=3)
def start_trading_bot(self, bot_id: str) -> dict:
    """
    Start a trading bot.

    1. Load bot config from database
    2. Initialize OrderManager and CircuitBreaker
    3. Connect to exchange + WebSocket
    4. Start trading loop
    5. Register in _running_bots

    Args:
        bot_id: The bot ID to start

    Returns:
        Dict with status and any error message
    """
    from api.core.config import get_settings

    logger.info(f"Starting bot {bot_id}")

    try:
        result = _run_async(_start_bot_async(bot_id))
        return result
    except Exception as e:
        logger.error(f"Failed to start bot {bot_id}: {e}")
        # Update bot status to error
        _run_async(_update_bot_status(bot_id, "error", str(e)))
        raise self.retry(exc=e, countdown=10)


async def _start_bot_async(
    bot_id: str,
    rehydrate: bool = False,
    broadcast: bool = True,
) -> dict:
    """Async implementation of bot startup."""
    import redis.asyncio as redis_async
    from sqlalchemy import func, select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot, ExchangeCredential
    from api.services.encryption import get_encryption_service
    from bot.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
    from bot.engine import BotConfig, BotEngine
    from bot.exchange.connector import CCXTConnector
    from bot.order_manager import OrderManager
    from bot.strategies.dca import DCAStrategy
    from bot.strategies.grid import GridStrategy

    settings = get_settings()

    # Create database session
    db_engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    db = async_session()

    try:
        # Load bot from database
        stmt = select(Bot).where(Bot.id == UUID(bot_id))
        result = await db.execute(stmt)
        bot = result.scalar_one_or_none()

        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}

        if bot.status == "running" and not rehydrate:
            return {"status": "already_running", "bot_id": bot_id}

        # Load credentials
        if bot.credential_id:
            stmt = select(ExchangeCredential).where(
                ExchangeCredential.id == bot.credential_id
            )
            result = await db.execute(stmt)
            credential = result.scalar_one_or_none()

            if not credential:
                return {"status": "error", "message": "Credentials not found"}

            encryption = get_encryption_service()
            api_key = encryption.decrypt(credential.api_key_encrypted)
            api_secret = encryption.decrypt(credential.api_secret_encrypted)
            is_testnet = credential.is_testnet
        else:
            return {"status": "error", "message": "No credentials configured"}

        config = dict(bot.config or {})

        # Strategy initialization
        strategy_instance = None
        investment_value = Decimal(str(config.get("investment", 0) or 0))
        normalized_config = dict(config)

        if bot.strategy == "grid":
            lower_price = Decimal(str(config["lower_price"]))
            upper_price = Decimal(str(config["upper_price"]))
            grid_count = int(config["grid_count"])
            investment_value = Decimal(str(config.get("investment", 0) or 0))
            strategy_instance = GridStrategy(
                symbol=bot.symbol,
                investment=investment_value,
                lower_price=lower_price,
                upper_price=upper_price,
                grid_count=grid_count,
            )
        elif bot.strategy == "dca":
            amount_per_buy = config.get("amount_per_buy", config.get("amount"))
            if amount_per_buy is None:
                return {"status": "error", "message": "DCA config missing amount"}

            amount_per_buy_value = Decimal(str(amount_per_buy))
            trigger_drop = config.get(
                "trigger_drop_percent",
                config.get("trigger_drop"),
            )
            take_profit = config.get(
                "take_profit_percent",
                config.get("take_profit"),
            )
            interval = config.get("interval")
            investment_value = Decimal(
                str(config.get("investment", amount_per_buy_value) or amount_per_buy_value)
            )

            normalized_config.setdefault("amount_per_buy", float(amount_per_buy_value))
            normalized_config.setdefault("investment", float(investment_value))
            if trigger_drop is not None:
                normalized_config.setdefault("trigger_drop_percent", float(trigger_drop))
            if take_profit is not None:
                normalized_config.setdefault("take_profit_percent", float(take_profit))

            if bot.strategy_state:
                strategy_instance = DCAStrategy.from_state_dict(
                    bot.strategy_state,
                    symbol=bot.symbol,
                    investment=investment_value,
                    amount_per_buy=amount_per_buy_value,
                    interval=interval,
                    trigger_drop_percent=Decimal(str(trigger_drop))
                    if trigger_drop is not None
                    else None,
                    take_profit_percent=Decimal(str(take_profit))
                    if take_profit is not None
                    else None,
                )
            else:
                strategy_instance = DCAStrategy(
                    symbol=bot.symbol,
                    investment=investment_value,
                    amount_per_buy=amount_per_buy_value,
                    interval=interval,
                    trigger_drop_percent=Decimal(str(trigger_drop))
                    if trigger_drop is not None
                    else None,
                    take_profit_percent=Decimal(str(take_profit))
                    if take_profit is not None
                    else None,
                )
        else:
            return {"status": "error", "message": f"Unknown strategy {bot.strategy}"}

        # Create exchange connector
        connector = CCXTConnector(
            exchange_id=bot.exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=is_testnet,
        )
        await connector.connect()

        # Create Redis client for circuit breaker
        redis_client = redis_async.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

        # Create circuit breaker
        cb_config = CircuitBreakerConfig(
            max_orders_per_minute=settings.circuit_breaker_orders_limit,
            max_loss_percent_per_hour=Decimal(
                str(settings.circuit_breaker_max_loss_percent)
            ),
            max_price_deviation_percent=Decimal(
                str(settings.circuit_breaker_price_deviation)
            ),
            cooldown_seconds=settings.circuit_breaker_cooldown,
        )
        circuit_breaker = CircuitBreaker(redis_client, cb_config)

        # Create order manager
        order_manager = OrderManager(
            exchange=connector,
            db_session=db,
        )

        # Load existing orders
        await order_manager.load_orders_from_db(UUID(bot_id))

        engine = BotEngine(
            config=BotConfig(
                id=UUID(bot_id),
                user_id=bot.user_id,
                strategy=strategy_instance,
                exchange=connector,
                symbol=bot.symbol,
                investment=investment_value,
            ),
            order_manager=order_manager,
            circuit_breaker=circuit_breaker,
        )

        order_manager.on_order_filled = engine.handle_order_filled

        # Register bot in running registry
        _running_bots[bot_id] = {
            "connector": connector,
            "order_manager": order_manager,
            "circuit_breaker": circuit_breaker,
            "ws_manager": None,
            "config": normalized_config,
            "symbol": bot.symbol,
            "strategy": bot.strategy,
            "engine": engine,
            "strategy_instance": strategy_instance,
            "db_session": db,
            "db_engine": db_engine,
            "tick_in_progress": False,
        }

        # Seed initial orders for grid bots
        if bot.strategy == "grid":
            await engine._tick()

        # Update bot status
        bot.status = "running"
        bot.error_message = None
        await db.commit()

        if broadcast:
            # Broadcast bot status update via WebSocket
            from api.core.ws_manager import broadcast_bot_status
            await broadcast_bot_status(
                user_id=str(bot.user_id),
                bot_id=bot_id,
                status="running",
                message="Bot started successfully",
            )

        logger.info(f"Bot {bot_id} started successfully")
        return {"status": "running", "bot_id": bot_id}
    except Exception:
        await db.close()
        await db_engine.dispose()
        raise


@celery_app.task(bind=True)
def stop_trading_bot(
    self,
    bot_id: str,
    source: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """
    Stop a trading bot.

    1. Cancel all open orders
    2. Disconnect WebSocket
    3. Save final state
    4. Remove from _running_bots

    Args:
        bot_id: The bot ID to stop

    Returns:
        Dict with status and orders cancelled count
    """
    logger.info(f"Stopping bot {bot_id}")

    try:
        result = _run_async(_stop_bot_async(bot_id, source, reason, metadata))
        return result
    except Exception as e:
        logger.error(f"Failed to stop bot {bot_id}: {e}")
        return {"status": "error", "message": str(e)}


async def _stop_bot_async(
    bot_id: str,
    source: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Async implementation of bot shutdown."""
    from sqlalchemy import func, select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot

    settings = get_settings()

    # Get running bot
    bot_data = _running_bots.get(bot_id)
    orders_cancelled = 0

    if bot_data:
        order_manager = bot_data.get("order_manager")
        connector = bot_data.get("connector")
        ws_manager = bot_data.get("ws_manager")
        db_session = bot_data.get("db_session")
        db_engine = bot_data.get("db_engine")

        # Cancel all open orders
        if order_manager:
            orders_cancelled = await order_manager.cancel_all_orders(UUID(bot_id))
            logger.info(f"Cancelled {orders_cancelled} orders for bot {bot_id}")

        # Disconnect WebSocket
        if ws_manager:
            await ws_manager.disconnect()

        # Disconnect exchange
        if connector:
            await connector.disconnect()

        if db_session:
            await db_session.close()
        if db_engine:
            await db_engine.dispose()

        # Remove from registry
        del _running_bots[bot_id]

    # Update database status
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        stmt = select(Bot).where(Bot.id == UUID(bot_id))
        result = await db.execute(stmt)
        bot = result.scalar_one_or_none()

        if bot:
            bot.status = "stopped"
            event_metadata = dict(metadata or {})
            event_metadata["orders_cancelled"] = orders_cancelled
            from api.services.bot_event_service import record_bot_event
            await record_bot_event(
                db=db,
                bot_id=bot.id,
                user_id=bot.user_id,
                event_type="stop_executed",
                source=source or "system",
                reason=reason,
                metadata=event_metadata,
            )
            await db.commit()

            # Broadcast bot status update via WebSocket
            from api.core.ws_manager import broadcast_bot_status
            await broadcast_bot_status(
                user_id=str(bot.user_id),
                bot_id=bot_id,
                status="stopped",
                message=f"Bot stopped, {orders_cancelled} orders cancelled"
            )

    await engine.dispose()

    logger.info(f"Bot {bot_id} stopped")
    return {
        "status": "stopped",
        "bot_id": bot_id,
        "orders_cancelled": orders_cancelled,
    }


@celery_app.task(bind=True)
def tick_running_bots(self) -> dict:
    """
    Execute strategy ticks for running bots.

    Grid bots are ticked regularly to place and manage orders.
    """
    ticked = 0
    skipped = 0
    errors = 0

    if not _running_bots:
        try:
            _run_async(_rehydrate_running_bots())
        except Exception as e:
            logger.error(f"Failed to rehydrate running bots: {e}")

    for bot_id, bot_data in list(_running_bots.items()):
        if bot_data.get("strategy") != "grid":
            continue

        if bot_data.get("tick_in_progress"):
            skipped += 1
            continue

        bot_data["tick_in_progress"] = True
        try:
            _run_async(_tick_bot_async(bot_id, bot_data))
            ticked += 1
        except Exception as e:
            errors += 1
            logger.error(f"Tick failed for bot {bot_id}: {e}")
            _run_async(_update_bot_status(bot_id, "error", str(e)))
            stop_trading_bot.delay(
                bot_id,
                source="tick_error",
                reason=str(e),
            )
        finally:
            bot_data["tick_in_progress"] = False

    return {"status": "ok", "ticked": ticked, "skipped": skipped, "errors": errors}


async def _rehydrate_running_bots() -> dict:
    """Rebuild in-memory running bots state from the database."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot

    settings = get_settings()
    db_engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    db = async_session()

    try:
        result = await db.execute(select(Bot.id).where(Bot.status == "running"))
        bot_ids = [str(row[0]) for row in result.all()]
    finally:
        await db.close()
        await db_engine.dispose()

    rehydrated = 0
    for bot_id in bot_ids:
        if bot_id in _running_bots:
            continue
        result = await _start_bot_async(bot_id, rehydrate=True, broadcast=False)
        if result.get("status") in ("running", "already_running"):
            rehydrated += 1

    if rehydrated:
        logger.info(f"Rehydrated {rehydrated} running bots from DB")

    return {"status": "ok", "rehydrated": rehydrated}

async def _tick_bot_async(bot_id: str, bot_data: dict[str, Any]) -> None:
    """Run a single strategy tick for a bot."""
    order_manager = bot_data.get("order_manager")
    engine = bot_data.get("engine")

    if not order_manager or not engine:
        raise RuntimeError("Missing engine or order manager")

    # Refresh config without stopping the bot
    await _refresh_running_bot_config(bot_id, bot_data)

    # Sync open orders before strategy calculation
    open_orders = await order_manager.get_open_orders(UUID(bot_id))
    for order in open_orders:
        await order_manager.sync_order_status(order.id)

    await engine._tick()

    if engine.strategy.should_stop():
        logger.info(f"Bot {bot_id} requested stop by strategy")
        stop_trading_bot.delay(
            bot_id,
            source="strategy",
            reason="strategy_stop",
        )


def _grid_config_signature(config: dict[str, Any]) -> tuple[Decimal, Decimal, int, Decimal] | None:
    """Build a comparable signature for grid config."""
    try:
        lower_price = Decimal(str(config["lower_price"]))
        upper_price = Decimal(str(config["upper_price"]))
        grid_count = int(config["grid_count"])
        investment_value = Decimal(str(config.get("investment", 0) or 0))
    except (KeyError, ValueError, TypeError):
        return None

    return (lower_price, upper_price, grid_count, investment_value)


async def _refresh_running_bot_config(bot_id: str, bot_data: dict[str, Any]) -> None:
    """Reload bot config from DB if it changed."""
    if bot_data.get("strategy") != "grid":
        return

    engine = bot_data.get("engine")
    if not engine:
        return

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot
    from bot.strategies.grid import GridStrategy

    settings = get_settings()
    db_engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            result = await db.execute(select(Bot).where(Bot.id == UUID(bot_id)))
            bot = result.scalar_one_or_none()
    finally:
        await db_engine.dispose()

    if not bot:
        return

    config = dict(bot.config or {})
    new_signature = _grid_config_signature(config)
    current_signature = _grid_config_signature(bot_data.get("config", {}))

    if not new_signature or new_signature == current_signature:
        return

    lower_price, upper_price, grid_count, investment_value = new_signature

    logger.info(
        "Reloading bot config in-memory: %s (lower=%s upper=%s grids=%s invest=%s)",
        bot_id,
        lower_price,
        upper_price,
        grid_count,
        investment_value,
    )

    new_strategy = GridStrategy(
        symbol=bot.symbol,
        investment=investment_value,
        lower_price=lower_price,
        upper_price=upper_price,
        grid_count=grid_count,
    )

    # Preserve realized P&L for continuity
    if hasattr(engine, "strategy"):
        new_strategy.realized_pnl = engine.strategy.realized_pnl

    engine.strategy = new_strategy
    engine.config.strategy = new_strategy
    engine.config.investment = investment_value

    bot_data["strategy_instance"] = new_strategy
    bot_data["config"] = config


# =============================================================================
# Order Processing Tasks
# =============================================================================


@celery_app.task(bind=True, max_retries=5)
def process_order_fill(self, bot_id: str, order_id: str, fill_data: dict) -> dict:
    """
    Process a filled order.

    1. Update order in database
    2. Calculate P&L
    3. Update bot metrics
    4. Check circuit breaker

    Args:
        bot_id: The bot that owns the order
        order_id: The filled order ID
        fill_data: Fill details from exchange

    Returns:
        Dict with processing result
    """
    logger.info(f"Processing fill for order {order_id} on bot {bot_id}")

    try:
        result = _run_async(_process_order_fill_async(bot_id, order_id, fill_data))
        return result
    except Exception as e:
        logger.error(f"Failed to process order fill: {e}")
        raise self.retry(exc=e, countdown=5)


async def _process_order_fill_async(
    bot_id: str, order_id: str, fill_data: dict
) -> dict:
    """Async implementation of order fill processing."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot, Order as OrderORM, Trade

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Load order
        stmt = select(OrderORM).where(OrderORM.id == UUID(order_id))
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()

        if not order:
            return {"status": "error", "message": "Order not found"}

        filled_quantity_raw = fill_data.get(
            "filledQuantity",
            fill_data.get("filled", fill_data.get("filled_quantity", 0)),
        )
        avg_price_raw = fill_data.get(
            "avgPrice",
            fill_data.get("average", fill_data.get("price")),
        )
        status_raw = str(fill_data.get("status", "filled")).lower()
        if status_raw in ("closed", "filled", "trade"):
            status = "filled"
        elif status_raw in ("canceled", "cancelled", "expired"):
            status = "cancelled"
        else:
            status = status_raw

        # Update order
        order.filled_quantity = Decimal(str(filled_quantity_raw or 0))
        order.average_fill_price = (
            Decimal(str(avg_price_raw))
            if avg_price_raw is not None
            else None
        )
        order.status = status

        exchange_trade_id = (
            fill_data.get("exchangeTradeId")
            or fill_data.get("tradeId")
            or fill_data.get("id")
        )
        realized_pnl_raw = (
            fill_data.get("realizedPnl")
            or fill_data.get("realized_pnl")
        )

        existing_trade = None
        if exchange_trade_id:
            existing_trade = (
                await db.execute(
                    select(Trade).where(
                        Trade.exchange_trade_id == str(exchange_trade_id)
                    )
                )
            ).scalar_one_or_none()
        if existing_trade is None:
            existing_trade = (
                await db.execute(
                    select(Trade).where(
                        Trade.order_id == order.id,
                        Trade.quantity == order.filled_quantity,
                        Trade.price
                        == (order.average_fill_price or order.price or Decimal("0")),
                    )
                )
            ).scalar_one_or_none()
        if existing_trade:
            if (
                realized_pnl_raw is not None
                and existing_trade.realized_pnl is None
            ):
                existing_trade.realized_pnl = Decimal(str(realized_pnl_raw))
            await db.commit()
            return {
                "status": "skipped",
                "order_id": order_id,
                "reason": "trade_exists",
            }

        fee_value = fill_data.get("fee", fill_data.get("commission", 0))
        fee_currency = fill_data.get("feeAsset", fill_data.get("commissionAsset"))
        if isinstance(fee_value, dict):
            fee_currency = fee_value.get("currency") or fee_currency
            fee_value = fee_value.get("cost", 0)

        timestamp_value = (
            fill_data.get("timestamp")
            or fill_data.get("transactTime")
            or fill_data.get("T")
        )
        trade_timestamp = None
        if timestamp_value:
            ts = int(timestamp_value)
            if ts > 1_000_000_000_000:
                ts = ts / 1000
            trade_timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)

        # Create trade record
        trade = Trade(
            bot_id=UUID(bot_id),
            order_id=UUID(order_id),
            exchange_trade_id=str(exchange_trade_id)
            if exchange_trade_id is not None
            else None,
            symbol=order.symbol,
            side=order.side,
            price=order.average_fill_price or order.price or Decimal("0"),
            quantity=order.filled_quantity,
            fee=Decimal(str(fee_value or 0)),
            fee_currency=fee_currency,
            realized_pnl=Decimal(str(realized_pnl_raw))
            if realized_pnl_raw is not None
            else None,
        )
        if trade_timestamp:
            trade.timestamp = trade_timestamp
        db.add(trade)

        await db.commit()

        realized_sum = (
            await db.execute(
                select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(
                    Trade.bot_id == order.bot_id
                )
            )
        ).scalar_one()
        await db.execute(
            update(Bot)
            .where(Bot.id == order.bot_id)
            .values(realized_pnl=Decimal(str(realized_sum)))
        )
        await db.commit()

        # Record P&L in circuit breaker (if loss)
        bot_data = _running_bots.get(bot_id)
        if bot_data:
            circuit_breaker = bot_data.get("circuit_breaker")
            # P&L calculation would go here based on position tracking

    await engine.dispose()

    return {
        "status": "processed",
        "order_id": order_id,
        "filled_quantity": str(order.filled_quantity),
    }


@celery_app.task(bind=True, max_retries=5)
def poll_bot_orders(self, bot_id: str) -> dict:
    """
    Poll order status from exchange (fallback for exchanges without WebSocket).

    Used for MEXC and other exchanges that don't support user data WebSocket.

    Args:
        bot_id: The bot to poll orders for

    Returns:
        Dict with poll results
    """
    try:
        result = _run_async(_poll_orders_async(bot_id))
        return result
    except Exception as e:
        logger.error(f"Failed to poll orders for bot {bot_id}: {e}")
        raise self.retry(exc=e, countdown=5)


async def _poll_orders_async(bot_id: str) -> dict:
    """Async implementation of order polling."""
    bot_data = _running_bots.get(bot_id)
    if not bot_data:
        return {"status": "not_running", "bot_id": bot_id}

    order_manager = bot_data.get("order_manager")
    if not order_manager:
        return {"status": "error", "message": "No order manager"}

    # Get all open orders and sync status
    orders = await order_manager.get_open_orders(UUID(bot_id))
    synced = 0

    for order in orders:
        await order_manager.sync_order_status(order.id)
        synced += 1

    return {"status": "ok", "bot_id": bot_id, "orders_synced": synced}


@celery_app.task(bind=True)
def poll_running_mexc_bots(self) -> dict:
    """
    Poll orders for all running MEXC bots.

    MEXC doesn't support WebSocket for user data, so we need to poll.
    """
    polled = 0
    for bot_id, bot_data in _running_bots.items():
        connector = bot_data.get("connector")
        if connector and connector.exchange_id == "mexc":
            poll_bot_orders.delay(bot_id)
            polled += 1

    return {"status": "ok", "bots_polled": polled}


# =============================================================================
# Trade Reconciliation Tasks
# =============================================================================


@celery_app.task(bind=True, max_retries=3)
def reconcile_running_bots_trades(self) -> dict:
    """
    Reconcile recent trades for all running bots.

    This backfills any missed fills by querying the exchange directly.
    """
    created = 0
    skipped = 0
    errors = 0

    bot_ids = list(_running_bots.keys())
    if not bot_ids:
        try:
            bot_ids = _run_async(_list_recent_bot_ids_async())
        except Exception as e:
            logger.error(f"Failed to list recent bots for reconciliation: {e}")

    for bot_id in bot_ids:
        try:
            result = _run_async(_reconcile_bot_trades_async(bot_id))
            created += int(result.get("created", 0))
            skipped += int(result.get("skipped", 0))
        except Exception as e:
            errors += 1
            logger.error(f"Trade reconcile failed for bot {bot_id}: {e}")

    return {"status": "ok", "created": created, "skipped": skipped, "errors": errors}


async def _list_recent_bot_ids_async(hours: int = 24) -> list[str]:
    """List bot IDs updated within the last N hours."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with async_session() as db:
        result = await db.execute(
            select(Bot.id).where(Bot.updated_at >= since)
        )
        bot_ids = [str(row[0]) for row in result.all()]

    await engine.dispose()
    return bot_ids


async def _reconcile_bot_trades_async(
    bot_id: str,
    since_minutes: int = 1440,
    limit: int = 100,
) -> dict:
    """Fetch recent trades from exchange and persist missing ones."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot, ExchangeCredential, Order as OrderORM, Trade
    from api.services.credential_service import CredentialService
    from bot.exchange.connector import CCXTConnector

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    created = 0
    skipped = 0
    connector = None

    try:
        async with async_session() as db:
            stmt = select(Bot).where(Bot.id == UUID(bot_id))
            result = await db.execute(stmt)
            bot = result.scalar_one_or_none()
            if not bot:
                return {"status": "skipped", "created": 0, "skipped": 1}

            credential = await db.get(ExchangeCredential, bot.credential_id)
            if not credential:
                return {"status": "error", "message": "Credential not found"}

            service = CredentialService(db)
            api_key, api_secret = service.get_decrypted_keys(credential)

            connector = CCXTConnector(
                exchange_id=credential.exchange,
                api_key=api_key,
                api_secret=api_secret,
                testnet=credential.is_testnet,
            )
            await connector.connect()

            since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            since_ms = int(since.timestamp() * 1000)
            trades = await connector.fetch_my_trades(
                bot.symbol,
                since=since_ms,
                limit=limit,
            )

            orders_result = await db.execute(
                select(OrderORM).where(
                    OrderORM.bot_id == bot.id,
                    OrderORM.exchange_order_id.is_not(None),
                )
            )
            orders_by_exchange = {
                str(o.exchange_order_id): o for o in orders_result.scalars().all()
            }

            buy_lots: list[dict[str, Decimal]] = []
            sorted_trades = sorted(
                trades, key=lambda t: t.get("timestamp") or 0
            )
            base_symbol = None
            quote_symbol = None
            if bot.symbol and "/" in bot.symbol:
                base_symbol, quote_symbol = bot.symbol.split("/", 1)

            for trade_data in sorted_trades:
                trade_id = trade_data.get("id")
                exchange_order_id = trade_data.get("order")
                if not exchange_order_id:
                    skipped += 1
                    continue

                order = orders_by_exchange.get(str(exchange_order_id))
                if not order:
                    skipped += 1
                    continue

                price = Decimal(str(trade_data.get("price") or 0))
                quantity = Decimal(
                    str(trade_data.get("amount", trade_data.get("filled", 0)))
                )
                side = trade_data.get("side", order.side)

                fee = trade_data.get("fee")
                fee_cost = Decimal("0")
                fee_currency = None
                if isinstance(fee, dict):
                    fee_cost = Decimal(str(fee.get("cost", 0) or 0))
                    fee_currency = fee.get("currency")
                elif fee is not None:
                    fee_cost = Decimal(str(fee or 0))

                fee_in_quote = Decimal("0")
                if fee_currency and quote_symbol and base_symbol:
                    if fee_currency == quote_symbol:
                        fee_in_quote = fee_cost
                    elif fee_currency == base_symbol:
                        fee_in_quote = fee_cost * price

                realized_pnl = Decimal("0")
                if side == "buy":
                    if quantity > 0:
                        effective_price = price
                        if fee_in_quote > 0:
                            effective_price += fee_in_quote / quantity
                        buy_lots.append({"price": effective_price, "quantity": quantity})
                else:
                    remaining = quantity
                    while remaining > 0 and buy_lots:
                        lot = buy_lots[0]
                        use_qty = min(remaining, lot["quantity"])
                        realized_pnl += (price - lot["price"]) * use_qty
                        lot["quantity"] -= use_qty
                        remaining -= use_qty
                        if lot["quantity"] <= 0:
                            buy_lots.pop(0)
                    if fee_in_quote > 0:
                        realized_pnl -= fee_in_quote

                if trade_id:
                    existing = (
                        await db.execute(
                            select(Trade).where(
                                Trade.exchange_trade_id == str(trade_id)
                            )
                        )
                    ).scalar_one_or_none()
                    if existing:
                        if existing.realized_pnl is None:
                            existing.realized_pnl = realized_pnl
                        skipped += 1
                        continue

                existing = (
                    await db.execute(
                        select(Trade).where(
                            Trade.order_id == order.id,
                            Trade.price == price,
                            Trade.quantity == quantity,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    if existing.realized_pnl is None:
                        existing.realized_pnl = realized_pnl
                    skipped += 1
                    continue

                timestamp_value = trade_data.get("timestamp")
                trade_timestamp = None
                if timestamp_value:
                    ts = int(timestamp_value)
                    if ts > 1_000_000_000_000:
                        ts = ts / 1000
                    trade_timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)

                trade = Trade(
                    bot_id=bot.id,
                    order_id=order.id,
                    exchange_trade_id=str(trade_id) if trade_id else None,
                    symbol=trade_data.get("symbol", bot.symbol),
                    side=side,
                    price=price,
                    quantity=quantity,
                    fee=Decimal(str(fee_cost or 0)),
                    fee_currency=fee_currency,
                    realized_pnl=realized_pnl,
                )
                if trade_timestamp:
                    trade.timestamp = trade_timestamp
                db.add(trade)
                created += 1

            await db.flush()
            realized_sum = (
                await db.execute(
                    select(func.coalesce(func.sum(Trade.realized_pnl), 0)).where(
                        Trade.bot_id == bot.id
                    )
                )
            ).scalar_one()
            bot.realized_pnl = Decimal(str(realized_sum))
            if bot.status != "running":
                bot.unrealized_pnl = Decimal("0")

            await db.commit()
    finally:
        if connector:
            await connector.disconnect()
        await engine.dispose()

    return {"status": "ok", "created": created, "skipped": skipped}


# =============================================================================
# Monitoring Tasks
# =============================================================================


@celery_app.task(bind=True)
def check_circuit_breakers(self) -> dict:
    """
    Check circuit breaker status for all running bots.

    If a circuit breaker is tripped, stop the bot.
    """
    tripped = 0

    for bot_id, bot_data in list(_running_bots.items()):
        try:
            circuit_breaker = bot_data.get("circuit_breaker")
            if circuit_breaker:
                is_tripped = _run_async(circuit_breaker.is_tripped(UUID(bot_id)))
                if is_tripped:
                    logger.warning(f"Circuit breaker tripped for bot {bot_id}")
                    investment_value = Decimal(
                        str(bot_data.get("config", {}).get("investment") or 0)
                    )
                    status = _run_async(
                        circuit_breaker.get_status(UUID(bot_id), investment_value)
                    )
                    reason = (
                        status.trip_reason.value
                        if status.trip_reason
                        else "circuit_breaker_open"
                    )
                    stop_trading_bot.delay(
                        bot_id,
                        source="circuit_breaker",
                        reason=reason,
                        metadata={
                            "orders_last_minute": status.orders_last_minute,
                            "loss_last_hour": str(status.loss_last_hour),
                            "cooldown_remaining": status.cooldown_remaining,
                        },
                    )
                    tripped += 1
        except Exception as e:
            logger.error(f"Error checking circuit breaker for {bot_id}: {e}")

    return {"status": "ok", "bots_tripped": tripped}


@celery_app.task(bind=True, max_retries=3)
def check_bot_health(self) -> dict:
    """
    Check health of all running bots.

    - Verify exchange connections
    - Check for stale orders
    - Update bot metrics
    """
    healthy = 0
    unhealthy = 0

    for bot_id, bot_data in list(_running_bots.items()):
        try:
            connector = bot_data.get("connector")
            if connector and connector.is_connected:
                healthy += 1
            else:
                unhealthy += 1
                logger.warning(f"Bot {bot_id} exchange disconnected")
                # Attempt reconnection
                stop_trading_bot.delay(
                    bot_id,
                    source="health_check",
                    reason="exchange_disconnected",
                )
        except Exception as e:
            logger.error(f"Health check failed for bot {bot_id}: {e}")
            unhealthy += 1

    return {"status": "ok", "healthy": healthy, "unhealthy": unhealthy}


@celery_app.task(bind=True)
def sync_running_bots_metrics(self) -> dict:
    """
    Sync metrics for all running bots.

    Iterates through all running bots and updates their P&L in the database.
    """
    synced = 0
    errors = 0

    for bot_id in list(_running_bots.keys()):
        try:
            sync_bot_metrics.delay(bot_id)
            synced += 1
        except Exception as e:
            logger.error(f"Failed to queue metrics sync for bot {bot_id}: {e}")
            errors += 1

    return {"status": "ok", "synced": synced, "errors": errors}


@celery_app.task(bind=True, max_retries=3)
def sync_bot_metrics(self, bot_id: str) -> dict:
    """
    Sync metrics for a single bot.

    Updates realized and unrealized P&L in the database.

    Args:
        bot_id: The bot ID to sync metrics for

    Returns:
        Dict with sync result
    """
    try:
        result = _run_async(_sync_bot_metrics_async(bot_id))
        return result
    except Exception as e:
        logger.error(f"Failed to sync metrics for bot {bot_id}: {e}")
        raise self.retry(exc=e, countdown=10)


async def _sync_bot_metrics_async(bot_id: str) -> dict:
    """Async implementation of bot metrics sync."""
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot
    from bot.strategies.grid import GridStrategy

    bot_data = _running_bots.get(bot_id)
    if not bot_data:
        return {"status": "not_running", "bot_id": bot_id}

    connector = bot_data.get("connector")
    symbol = bot_data.get("symbol")

    # Get strategy from running bot (if we have a BotEngine)
    # For now, we calculate basic metrics from order manager
    order_manager = bot_data.get("order_manager")
    if not order_manager:
        return {"status": "error", "message": "No order manager"}

    # Get current price for unrealized P&L calculation
    current_price = Decimal("0")
    if connector and symbol:
        try:
            ticker = await connector.fetch_ticker(symbol)
            current_price = Decimal(str(ticker["last"]))
        except Exception as e:
            logger.warning(f"Failed to fetch ticker for {symbol}: {e}")

    # Calculate realized P&L from filled orders
    # This is a simplified calculation - the real P&L comes from the strategy
    realized_pnl = Decimal("0")
    unrealized_pnl = Decimal("0")

    # If we have a GridStrategy, get P&L from it
    engine_data = bot_data.get("engine")
    if engine_data and hasattr(engine_data, "strategy"):
        strategy = engine_data.strategy
        realized_pnl = strategy.realized_pnl

        # Calculate unrealized P&L for grid strategy
        if isinstance(strategy, GridStrategy) and current_price > 0:
            unrealized_pnl = strategy.get_unrealized_pnl(current_price)

    # Update in database
    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        stmt = (
            update(Bot)
            .where(Bot.id == UUID(bot_id))
            .values(
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
            )
        )
        await db.execute(stmt)
        await db.commit()

    await engine.dispose()

    logger.debug(
        f"Synced metrics for bot {bot_id}: "
        f"realized={realized_pnl}, unrealized={unrealized_pnl}"
    )

    return {
        "status": "ok",
        "bot_id": bot_id,
        "realized_pnl": str(realized_pnl),
        "unrealized_pnl": str(unrealized_pnl),
    }


# =============================================================================
# Data Tasks
# =============================================================================


@celery_app.task(bind=True, max_retries=3)
def sync_market_data(self) -> dict:
    """
    Sync OHLCV data from exchanges.

    - Fetch latest candles for active trading pairs
    - Store in TimescaleDB for backtesting
    """
    # TODO: Implement market data sync
    return {"status": "ok", "pairs_synced": 0}


@celery_app.task(bind=True)
def cleanup_old_data(self) -> dict:
    """
    Clean up old data based on retention policy.

    - Remove old trades beyond retention period
    - Compress old OHLCV data
    """
    # TODO: Implement data cleanup
    return {"status": "ok", "records_cleaned": 0}


# =============================================================================
# DCA Tasks
# =============================================================================


@celery_app.task(bind=True, max_retries=5)
def execute_dca_buy(self, bot_id: str) -> dict:
    """
    Execute a scheduled DCA buy for a bot.

    Args:
        bot_id: The bot ID to execute DCA for
    """
    logger.info(f"Executing DCA buy for bot {bot_id}")

    try:
        result = _run_async(_execute_dca_buy_async(bot_id))
        return result
    except Exception as e:
        logger.error(f"DCA buy failed for bot {bot_id}: {e}")
        raise self.retry(exc=e, countdown=30)


async def _execute_dca_buy_async(bot_id: str) -> dict:
    """Async implementation of DCA buy."""
    from bot.order_manager import ManagedOrder, OrderState

    bot_data = _running_bots.get(bot_id)
    if not bot_data:
        return {"status": "not_running", "bot_id": bot_id}

    order_manager = bot_data.get("order_manager")
    connector = bot_data.get("connector")
    circuit_breaker = bot_data.get("circuit_breaker")
    config = bot_data.get("config", {})
    symbol = bot_data.get("symbol")

    if not all([order_manager, connector, symbol]):
        return {"status": "error", "message": "Missing components"}

    # Get current price
    ticker = await connector.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))

    # Check circuit breaker
    allowed, reason = await circuit_breaker.check_order_allowed(
        bot_id=UUID(bot_id),
        order_price=None,  # Market order
        current_price=current_price,
        investment=Decimal(str(config.get("investment", 1000))),
    )

    if not allowed:
        logger.warning(f"DCA blocked by circuit breaker: {reason}")
        return {"status": "blocked", "reason": reason}

    # Create market buy order
    amount = Decimal(str(config.get("amount_per_buy", 100)))
    quantity = amount / current_price

    order = ManagedOrder(
        bot_id=UUID(bot_id),
        symbol=symbol,
        side="buy",
        order_type="market",
        quantity=quantity,
    )

    # Submit order
    await order_manager.submit_order(order)
    await circuit_breaker.record_order_placed(UUID(bot_id))

    return {
        "status": "executed",
        "bot_id": bot_id,
        "order_id": str(order.id),
        "quantity": str(quantity),
        "price": str(current_price),
    }


@celery_app.task(bind=True, max_retries=3)
def dca_hourly_buy(self) -> dict:
    """Execute hourly DCA buys for all active bots with hourly interval."""
    return _run_async(_dca_interval_buy_async("hourly"))


@celery_app.task(bind=True, max_retries=3)
def dca_daily_buy(self) -> dict:
    """Execute daily DCA buys for all active bots with daily interval."""
    return _run_async(_dca_interval_buy_async("daily"))


@celery_app.task(bind=True, max_retries=3)
def dca_weekly_buy(self) -> dict:
    """Execute weekly DCA buys for all active bots with weekly interval."""
    return _run_async(_dca_interval_buy_async("weekly"))


async def _dca_interval_buy_async(interval: str) -> dict:
    """Execute DCA buys for all bots with the given interval."""
    from bot.strategies.dca import DCAStrategy

    executed = 0
    skipped = 0
    failed = 0

    for bot_id, bot_data in list(_running_bots.items()):
        # Skip non-DCA bots
        if bot_data.get("strategy") != "dca":
            continue

        config = bot_data.get("config", {})

        # Check if this bot uses the specified interval
        if config.get("interval") != interval:
            continue

        # Check budget
        amount_per_buy = Decimal(str(config.get("amount_per_buy", 100)))
        investment = Decimal(str(config.get("investment", 1000)))

        # Get strategy state to check remaining budget
        strategy = bot_data.get("strategy_instance")
        if isinstance(strategy, DCAStrategy):
            if strategy.remaining_budget < amount_per_buy:
                logger.info(f"DCA {bot_id}: Budget exhausted, skipping")
                skipped += 1
                continue

        try:
            execute_dca_buy.delay(bot_id)
            executed += 1
        except Exception as e:
            logger.error(f"Failed to queue DCA buy for {bot_id}: {e}")
            failed += 1

    logger.info(f"DCA {interval} buy: executed={executed}, skipped={skipped}, failed={failed}")
    return {"status": "ok", "interval": interval, "executed": executed, "skipped": skipped, "failed": failed}


@celery_app.task(bind=True, max_retries=3)
def dca_check_price_drops(self) -> dict:
    """Check price drop conditions for all DCA bots with trigger_drop_percent."""
    return _run_async(_dca_check_price_drops_async())


async def _dca_check_price_drops_async() -> dict:
    """Check and execute price-drop buys for DCA bots."""
    from bot.strategies.dca import DCAStrategy

    checked = 0
    triggered = 0

    for bot_id, bot_data in list(_running_bots.items()):
        # Skip non-DCA bots
        if bot_data.get("strategy") != "dca":
            continue

        config = bot_data.get("config", {})
        connector = bot_data.get("connector")
        symbol = bot_data.get("symbol")

        # Check if this bot uses price drop trigger
        trigger_drop = config.get("trigger_drop_percent")
        if trigger_drop is None:
            continue

        # Check budget
        amount_per_buy = Decimal(str(config.get("amount_per_buy", 100)))
        strategy = bot_data.get("strategy_instance")

        if isinstance(strategy, DCAStrategy):
            if strategy.remaining_budget < amount_per_buy:
                continue

        checked += 1

        try:
            # Fetch current price
            ticker = await connector.fetch_ticker(symbol)
            current_price = Decimal(str(ticker["last"]))

            # Update price tracking in strategy
            if isinstance(strategy, DCAStrategy):
                strategy._update_price_tracking(current_price)

                # Check if drop triggered
                if strategy._should_buy_by_drop(current_price):
                    execute_dca_buy.delay(bot_id)
                    triggered += 1
                    logger.info(f"DCA {bot_id}: Price drop triggered buy at {current_price}")

        except Exception as e:
            logger.error(f"Price drop check failed for {bot_id}: {e}")

    return {"status": "ok", "checked": checked, "triggered": triggered}


@celery_app.task(bind=True, max_retries=3)
def dca_check_take_profit(self) -> dict:
    """Check take-profit conditions for all DCA bots."""
    return _run_async(_dca_check_take_profit_async())


async def _dca_check_take_profit_async() -> dict:
    """Check and execute take-profit sells for DCA bots."""
    from bot.strategies.dca import DCAStrategy

    checked = 0
    triggered = 0

    for bot_id, bot_data in list(_running_bots.items()):
        # Skip non-DCA bots
        if bot_data.get("strategy") != "dca":
            continue

        config = bot_data.get("config", {})
        connector = bot_data.get("connector")
        symbol = bot_data.get("symbol")

        # Check if this bot uses take profit
        take_profit_percent = config.get("take_profit_percent")
        if take_profit_percent is None:
            continue

        # Check if there's a position to sell
        strategy = bot_data.get("strategy_instance")
        if isinstance(strategy, DCAStrategy):
            if strategy._total_quantity == 0:
                continue

        checked += 1

        try:
            # Fetch current price
            ticker = await connector.fetch_ticker(symbol)
            current_price = Decimal(str(ticker["last"]))

            # Check if take profit triggered
            if isinstance(strategy, DCAStrategy):
                if strategy._should_take_profit(current_price):
                    execute_dca_sell.delay(bot_id, str(current_price))
                    triggered += 1
                    logger.info(f"DCA {bot_id}: Take profit triggered at {current_price}")

        except Exception as e:
            logger.error(f"Take profit check failed for {bot_id}: {e}")

    return {"status": "ok", "checked": checked, "triggered": triggered}


@celery_app.task(bind=True, max_retries=5)
def execute_dca_sell(self, bot_id: str, price: str) -> dict:
    """
    Execute take-profit sell for DCA bot.

    Args:
        bot_id: The bot ID to execute sell for
        price: The trigger price (for logging)
    """
    logger.info(f"Executing DCA take-profit sell for bot {bot_id} at price {price}")

    try:
        result = _run_async(_execute_dca_sell_async(bot_id, Decimal(price)))
        return result
    except Exception as e:
        logger.error(f"DCA sell failed for bot {bot_id}: {e}")
        raise self.retry(exc=e, countdown=30)


async def _execute_dca_sell_async(bot_id: str, price: Decimal) -> dict:
    """Async implementation of DCA take-profit sell."""
    from bot.order_manager import ManagedOrder
    from bot.strategies.dca import DCAStrategy

    bot_data = _running_bots.get(bot_id)
    if not bot_data:
        return {"status": "not_running", "bot_id": bot_id}

    order_manager = bot_data.get("order_manager")
    connector = bot_data.get("connector")
    circuit_breaker = bot_data.get("circuit_breaker")
    symbol = bot_data.get("symbol")
    strategy = bot_data.get("strategy_instance")

    if not all([order_manager, connector, symbol]):
        return {"status": "error", "message": "Missing components"}

    if not isinstance(strategy, DCAStrategy):
        return {"status": "error", "message": "Not a DCA bot"}

    # Get quantity to sell
    quantity = strategy._total_quantity
    if quantity == 0:
        return {"status": "skipped", "message": "No position to sell"}

    # Check circuit breaker
    if circuit_breaker:
        allowed, reason = await circuit_breaker.check_order_allowed(
            bot_id=UUID(bot_id),
            order_price=None,  # Market order
            current_price=price,
            investment=Decimal(str(bot_data.get("config", {}).get("investment", 1000))),
        )
        if not allowed:
            logger.warning(f"DCA sell blocked by circuit breaker: {reason}")
            return {"status": "blocked", "reason": reason}

    # Create market sell order
    order = ManagedOrder(
        bot_id=UUID(bot_id),
        symbol=symbol,
        side="sell",
        order_type="market",
        quantity=quantity,
    )

    # Submit order
    await order_manager.submit_order(order)
    if circuit_breaker:
        await circuit_breaker.record_order_placed(UUID(bot_id))

    return {
        "status": "executed",
        "bot_id": bot_id,
        "order_id": str(order.id),
        "quantity": str(quantity),
        "price": str(price),
        "action": "take_profit_sell",
    }


@celery_app.task(bind=True)
def dca_save_strategy_state(self) -> dict:
    """Save DCA strategy state to database for all running bots."""
    return _run_async(_dca_save_strategy_state_async())


async def _dca_save_strategy_state_async() -> dict:
    """Persist DCA strategy state for all running bots."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.services.bot_service import BotService
    from bot.strategies.dca import DCAStrategy

    saved = 0
    errors = 0

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        bot_service = BotService(db)

        for bot_id, bot_data in list(_running_bots.items()):
            strategy = bot_data.get("strategy_instance")
            if not isinstance(strategy, DCAStrategy):
                continue

            try:
                state = strategy.to_state_dict()
                success = await bot_service.update_strategy_state(UUID(bot_id), state)
                if success:
                    saved += 1
                else:
                    logger.warning(f"Failed to save state for {bot_id}: bot not found")
                    errors += 1
            except Exception as e:
                logger.error(f"Failed to save state for {bot_id}: {e}")
                errors += 1

        await db.commit()

    await engine.dispose()

    logger.debug(f"DCA state save: saved={saved}, errors={errors}")
    return {"status": "ok", "saved": saved, "errors": errors}


# =============================================================================
# Report Tasks
# =============================================================================


@celery_app.task(bind=True)
def generate_bot_report(self, bot_id: str) -> dict:
    """
    Generate performance report for a bot.

    Args:
        bot_id: The bot to generate report for
    """
    # TODO: Implement report generation
    return {"status": "ok", "bot_id": bot_id, "report": {}}


# =============================================================================
# Backtest Tasks
# =============================================================================


@celery_app.task(bind=True)
def run_backtest(
    self,
    strategy: str,
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    config: dict,
) -> dict:
    """
    Run a backtest asynchronously.

    Args:
        strategy: Strategy type (grid/dca)
        symbol: Trading pair
        timeframe: Candle timeframe
        start_date: Backtest start date
        end_date: Backtest end date
        config: Strategy configuration
    """
    # TODO: Implement backtest execution
    return {
        "status": "completed",
        "total_trades": 0,
        "total_pnl": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
    }


async def _update_bot_status(bot_id: str, status: str, error_message: str | None = None) -> None:
    """Update bot status in database."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot

    settings = get_settings()
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        stmt = select(Bot).where(Bot.id == UUID(bot_id))
        result = await db.execute(stmt)
        bot = result.scalar_one_or_none()

        if bot:
            bot.status = status
            bot.error_message = error_message
            await db.commit()

            if status == "error" and error_message:
                try:
                    from api.services.telegram_service import notify_error
                    await notify_error(bot.user_id, error_message)
                except Exception as exc:
                    logger.warning(f"Failed to send Telegram error: {exc}")

    await engine.dispose()
