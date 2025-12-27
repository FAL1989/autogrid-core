"""
Pytest Configuration and Fixtures

Shared fixtures for all tests.
"""

import asyncio
from decimal import Decimal
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from bot.strategies.base import Order


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
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing."""
    from api.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


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


# Database fixtures (for integration tests)


@pytest.fixture
async def db_session():
    """Create database session for testing."""
    # TODO: Implement when database is set up
    # Use test database with rollback after each test
    yield None


# Redis fixtures


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    # TODO: Implement when Redis is set up
    # Use separate test database (db=15)
    yield None
