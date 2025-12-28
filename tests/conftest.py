"""
Pytest Configuration and Fixtures

Shared fixtures for all tests.
"""

import asyncio
import os
from decimal import Decimal
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from api.core.database import Base, get_db
from api.models.orm import Bot, ExchangeCredential, User
from api.services.jwt import create_token_pair
from api.services.security import hash_password
from bot.strategies.base import Order

# Test database URL (use a separate test database)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/autogrid_test"
)


@pytest.fixture
def sample_order() -> Order:
    """Create a sample order for testing."""
    return Order(
        side="buy",
        type="limit",
        price=Decimal("50000"),
        quantity=Decimal("0.1"),
    )


@pytest.fixture
def sample_orders() -> list[Order]:
    """Create multiple sample orders for testing."""
    return [
        Order(side="buy", type="limit", price=Decimal("49000"), quantity=Decimal("0.1")),
        Order(side="buy", type="limit", price=Decimal("48000"), quantity=Decimal("0.1")),
        Order(side="sell", type="limit", price=Decimal("51000"), quantity=Decimal("0.1")),
        Order(side="sell", type="limit", price=Decimal("52000"), quantity=Decimal("0.1")),
    ]


@pytest.fixture
def mock_exchange() -> MagicMock:
    """Create mock exchange connector."""
    mock = MagicMock()
    mock.is_connected = True
    mock.exchange_id = "binance"

    # Async methods
    mock.connect = AsyncMock()
    mock.disconnect = AsyncMock()
    mock.fetch_ticker = AsyncMock(
        return_value={
            "symbol": "BTC/USDT",
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "volume": 1000.0,
        }
    )
    mock.fetch_balance = AsyncMock(
        return_value={
            "USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0},
            "BTC": {"free": 0.5, "used": 0.0, "total": 0.5},
        }
    )
    mock.create_order = AsyncMock(
        return_value={
            "id": "12345",
            "symbol": "BTC/USDT",
            "type": "limit",
            "side": "buy",
            "amount": 0.1,
            "price": 50000.0,
            "status": "open",
        }
    )
    mock.cancel_order = AsyncMock(return_value=True)
    mock.fetch_order = AsyncMock(
        return_value={
            "id": "12345",
            "status": "filled",
            "filled": 0.1,
            "average": 50000.0,
        }
    )
    mock.fetch_ohlcv = AsyncMock(
        return_value=[
            [1704067200000, 50000, 50500, 49500, 50200, 100],
            [1704070800000, 50200, 50800, 50000, 50600, 120],
            [1704074400000, 50600, 51000, 50400, 50800, 80],
        ]
    )

    return mock


@pytest.fixture
def grid_config() -> dict:
    """Sample grid strategy configuration."""
    return {
        "symbol": "BTC/USDT",
        "investment": 1000.0,
        "lower_price": 45000.0,
        "upper_price": 55000.0,
        "grid_count": 20,
    }


@pytest.fixture
def dca_config() -> dict:
    """Sample DCA strategy configuration."""
    return {
        "symbol": "BTC/USDT",
        "investment": 1000.0,
        "amount_per_buy": 100.0,
        "interval": "daily",
        "trigger_drop_percent": 5.0,
        "take_profit_percent": 10.0,
    }


# ===========================================
# Database Fixtures
# ===========================================


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create database session for testing.

    Uses NullPool to avoid connection issues across different event loops.
    Each test gets a fresh connection.
    """
    # Use NullPool to avoid connection pool issues with asyncpg
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session

    # Clean up tables after each test
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing with test database and Redis."""
    import redis.asyncio as redis_async

    from api.core.rate_limiter import get_redis
    from api.main import app

    # Override the database dependency
    async def override_get_db():
        yield db_session

    # Create Redis client for tests (database 15)
    test_redis = redis_async.from_url(
        "redis://localhost:6379/15",
        encoding="utf-8",
        decode_responses=True,
    )

    async def override_get_redis():
        return test_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    await test_redis.flushdb()
    await test_redis.aclose()
    app.dependency_overrides.clear()


# ===========================================
# Authentication Fixtures
# ===========================================


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("TestPassword123!"),
        plan="free",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def test_user_password() -> str:
    """Return the password for the test user."""
    return "TestPassword123!"


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    """Create authentication headers with valid access token."""
    access_token, _ = create_token_pair(test_user.id)
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def auth_client(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> AsyncClient:
    """Create authenticated async client."""
    async_client.headers.update(auth_headers)
    return async_client


# ===========================================
# Bot Fixtures
# ===========================================


@pytest_asyncio.fixture
async def test_credential(db_session: AsyncSession, test_user: User) -> ExchangeCredential:
    """Create a test exchange credential."""
    credential = ExchangeCredential(
        user_id=test_user.id,
        exchange="binance",
        api_key_encrypted="encrypted_test_key",
        api_secret_encrypted="encrypted_test_secret",
        is_testnet=True,
    )
    db_session.add(credential)
    await db_session.flush()
    await db_session.refresh(credential)
    return credential


@pytest_asyncio.fixture
async def test_bot(
    db_session: AsyncSession,
    test_user: User,
    test_credential: ExchangeCredential,
) -> Bot:
    """Create a test bot with stopped status."""
    bot = Bot(
        user_id=test_user.id,
        credential_id=test_credential.id,
        name="Test Grid Bot",
        strategy="grid",
        exchange="binance",
        symbol="BTC/USDT",
        config={
            "lower_price": 45000.0,
            "upper_price": 55000.0,
            "grid_count": 10,
            "investment": 1000.0,
        },
        status="stopped",
    )
    db_session.add(bot)
    await db_session.flush()
    await db_session.refresh(bot)
    return bot


@pytest_asyncio.fixture
async def running_bot(
    db_session: AsyncSession,
    test_user: User,
    test_credential: ExchangeCredential,
) -> Bot:
    """Create a test bot with running status."""
    bot = Bot(
        user_id=test_user.id,
        credential_id=test_credential.id,
        name="Running DCA Bot",
        strategy="dca",
        exchange="binance",
        symbol="ETH/USDT",
        config={
            "amount": 100.0,
            "interval": "daily",
            "trigger_drop": 5.0,
        },
        status="running",
    )
    db_session.add(bot)
    await db_session.flush()
    await db_session.refresh(bot)
    return bot


# ===========================================
# Redis Fixtures
# ===========================================


@pytest_asyncio.fixture
async def redis_client():
    """Create Redis client for testing."""
    import redis.asyncio as redis

    client = redis.from_url(
        "redis://localhost:6379/15",  # Use database 15 for testing
        encoding="utf-8",
        decode_responses=True,
    )

    yield client

    # Clean up test data
    await client.flushdb()
    await client.close()
