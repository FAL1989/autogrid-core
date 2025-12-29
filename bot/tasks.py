"""
Celery Tasks for AutoGrid Bot

Background tasks for trading operations, data fetching, and scheduled jobs.
"""

import asyncio
import logging
import os
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
    "sync-bot-metrics-every-30s": {
        "task": "bot.tasks.sync_running_bots_metrics",
        "schedule": 30.0,  # Every 30 seconds
    },
    "cleanup-old-data-daily": {
        "task": "bot.tasks.cleanup_old_data",
        "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM UTC
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


async def _start_bot_async(bot_id: str) -> dict:
    """Async implementation of bot startup."""
    import redis.asyncio as redis_async
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from api.core.config import get_settings
    from api.models.orm import Bot, ExchangeCredential
    from api.services.security import decrypt_api_key
    from bot.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
    from bot.exchange.connector import CCXTConnector
    from bot.exchange.websocket_manager import WebSocketManager
    from bot.order_manager import OrderManager

    settings = get_settings()

    # Create database session
    engine = create_async_engine(settings.async_database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Load bot from database
        stmt = select(Bot).where(Bot.id == UUID(bot_id))
        result = await db.execute(stmt)
        bot = result.scalar_one_or_none()

        if not bot:
            return {"status": "error", "message": f"Bot {bot_id} not found"}

        if bot.status == "running":
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

            api_key = decrypt_api_key(credential.api_key_encrypted)
            api_secret = decrypt_api_key(credential.api_secret_encrypted)
            is_testnet = credential.is_testnet
        else:
            return {"status": "error", "message": "No credentials configured"}

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

        # Create WebSocket manager (if supported)
        ws_manager = None
        if bot.exchange in ("binance", "bybit"):
            ws_manager = WebSocketManager()
            await ws_manager.connect(
                exchange_id=bot.exchange,
                api_key=api_key,
                api_secret=api_secret,
                testnet=is_testnet,
            )

            # Register order update callback
            async def on_order_update(data: dict):
                await order_manager.handle_websocket_update(data)

            ws_manager.on_order_update(on_order_update)

        # Load existing orders
        await order_manager.load_orders_from_db(UUID(bot_id))

        # Register bot in running registry
        _running_bots[bot_id] = {
            "connector": connector,
            "order_manager": order_manager,
            "circuit_breaker": circuit_breaker,
            "ws_manager": ws_manager,
            "config": bot.config,
            "symbol": bot.symbol,
            "strategy": bot.strategy,
        }

        # Update bot status
        bot.status = "running"
        bot.error_message = None
        await db.commit()

        logger.info(f"Bot {bot_id} started successfully")
        return {"status": "running", "bot_id": bot_id}


@celery_app.task(bind=True)
def stop_trading_bot(self, bot_id: str) -> dict:
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
        result = _run_async(_stop_bot_async(bot_id))
        return result
    except Exception as e:
        logger.error(f"Failed to stop bot {bot_id}: {e}")
        return {"status": "error", "message": str(e)}


async def _stop_bot_async(bot_id: str) -> dict:
    """Async implementation of bot shutdown."""
    from sqlalchemy import select
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
            await db.commit()

    await engine.dispose()

    logger.info(f"Bot {bot_id} stopped")
    return {
        "status": "stopped",
        "bot_id": bot_id,
        "orders_cancelled": orders_cancelled,
    }


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
    from sqlalchemy import select
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

        # Update order
        order.filled_quantity = Decimal(str(fill_data.get("filledQuantity", 0)))
        order.average_fill_price = (
            Decimal(str(fill_data["avgPrice"]))
            if fill_data.get("avgPrice")
            else None
        )
        order.status = fill_data.get("status", "filled")

        # Create trade record
        trade = Trade(
            bot_id=UUID(bot_id),
            order_id=UUID(order_id),
            symbol=order.symbol,
            side=order.side,
            price=order.average_fill_price or order.price or Decimal("0"),
            quantity=order.filled_quantity,
            fee=Decimal(str(fill_data.get("fee", 0))),
            fee_currency=fill_data.get("feeAsset"),
        )
        db.add(trade)

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
                    stop_trading_bot.delay(bot_id)
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
                stop_trading_bot.delay(bot_id)
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

    await engine.dispose()
