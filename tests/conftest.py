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
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.core.database import Base, get_db
from api.models.orm import User
from api.services.jwt import create_token_pair
from api.services.security import hash_password
from bot.strategies.base import Order

# Test database URL (use a separate test database)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/autogrid_test"
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


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


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session with rollback for testing."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing with test database."""
    from api.main import app

    # Override the database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up overrides
    app.dependency_overrides.clear()


# ===========================================
# Authentication Fixtures
# ===========================================


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user in the database."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("TestPassword123!"),
        plan="free",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def test_user_password() -> str:
    """Return the password for the test user."""
    return "TestPassword123!"


@pytest.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    """Create authentication headers with valid access token."""
    access_token, _ = create_token_pair(test_user.id)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def auth_client(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> AsyncClient:
    """Create authenticated async client."""
    async_client.headers.update(auth_headers)
    return async_client


# ===========================================
# Redis Fixtures
# ===========================================


@pytest.fixture
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
