"""
Integration Tests for API

Tests for API endpoints with real database.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import ExchangeCredential, User
from api.services.security import hash_password


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for health check endpoint."""

    async def test_health_check(self, async_client: AsyncClient) -> None:
        """Test health check returns ok."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    async def test_register_success(self, async_client: AsyncClient) -> None:
        """Test successful user registration."""
        response = await async_client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123!",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "user_id" in data
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_register_invalid_email(self, async_client: AsyncClient) -> None:
        """Test registration with invalid email."""
        response = await async_client.post(
            "/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePass123!",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_login_success(
        self,
        async_client: AsyncClient,
        test_user: User,
        test_user_password: str,
    ) -> None:
        """Test successful login."""
        response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user.email,
                "password": test_user_password,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"


@pytest.mark.asyncio
class TestBotsEndpoints:
    """Tests for bots management endpoints."""

    async def test_list_bots_requires_auth(self, async_client: AsyncClient) -> None:
        """Test listing bots requires authentication."""
        response = await async_client.get("/bots/")

        assert response.status_code == 401

    async def test_list_bots_empty(self, auth_client: AsyncClient) -> None:
        """Test listing bots when none exist."""
        response = await auth_client.get("/bots/")

        assert response.status_code == 200
        data = response.json()
        assert data["bots"] == []
        assert data["total"] == 0

    async def test_create_grid_bot(
        self,
        auth_client: AsyncClient,
        test_credential: ExchangeCredential,
        grid_config: dict,
    ) -> None:
        """Test creating a grid trading bot."""
        response = await auth_client.post(
            "/bots/",
            json={
                "name": "Test Grid Bot",
                "credential_id": str(test_credential.id),
                "strategy": "grid",
                "symbol": grid_config["symbol"],
                "config": {
                    "lower_price": grid_config["lower_price"],
                    "upper_price": grid_config["upper_price"],
                    "grid_count": grid_config["grid_count"],
                    "investment": grid_config["investment"],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Grid Bot"
        assert data["strategy"] == "grid"
        assert data["status"] == "stopped"

    async def test_create_dca_bot(
        self,
        auth_client: AsyncClient,
        test_credential: ExchangeCredential,
        dca_config: dict,
    ) -> None:
        """Test creating a DCA bot."""
        response = await auth_client.post(
            "/bots/",
            json={
                "name": "Test DCA Bot",
                "credential_id": str(test_credential.id),
                "strategy": "dca",
                "symbol": dca_config["symbol"],
                "config": {
                    "amount": dca_config["amount_per_buy"],
                    "interval": dca_config["interval"],
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test DCA Bot"
        assert data["strategy"] == "dca"


@pytest.mark.asyncio
class TestCredentialsEndpoints:
    """Tests for credentials management endpoints."""

    async def test_list_credentials_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing credentials requires authentication."""
        response = await async_client.get("/credentials/")

        assert response.status_code == 401

    async def test_list_credentials_empty(self, auth_client: AsyncClient) -> None:
        """Test listing credentials when none exist."""
        response = await auth_client.get("/credentials/")

        assert response.status_code == 200
        data = response.json()
        assert data["credentials"] == []
        assert data["total"] == 0

    async def test_get_credential_not_found(self, auth_client: AsyncClient) -> None:
        """Test getting non-existent credential."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await auth_client.get(f"/credentials/{fake_id}")

        assert response.status_code == 404

    async def test_delete_credential_not_found(self, auth_client: AsyncClient) -> None:
        """Test deleting non-existent credential."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await auth_client.delete(f"/credentials/{fake_id}")

        assert response.status_code == 404

    async def test_get_credential_success(
        self,
        auth_client: AsyncClient,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test getting an existing credential."""
        response = await auth_client.get(f"/credentials/{test_credential.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_credential.id)
        assert data["exchange"] == test_credential.exchange
        # Verify secrets are NOT returned
        assert "api_key" not in data
        assert "api_secret" not in data
        assert "api_key_encrypted" not in data
        assert "api_secret_encrypted" not in data

    async def test_list_credentials_with_data(
        self,
        auth_client: AsyncClient,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test listing credentials when one exists."""
        response = await auth_client.get("/credentials/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["credentials"]) == 1
        assert data["credentials"][0]["id"] == str(test_credential.id)

    async def test_delete_credential_success(
        self,
        auth_client: AsyncClient,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test deleting an existing credential."""
        response = await auth_client.delete(f"/credentials/{test_credential.id}")

        assert response.status_code == 204

        # Verify it's gone
        response = await auth_client.get(f"/credentials/{test_credential.id}")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestOrdersEndpoints:
    """Tests for orders management endpoints."""

    async def test_list_orders_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test listing orders requires authentication."""
        from uuid import uuid4

        fake_bot_id = str(uuid4())
        response = await async_client.get(f"/orders/bots/{fake_bot_id}/orders")

        assert response.status_code == 401

    async def test_list_orders_bot_not_found(
        self, auth_client: AsyncClient
    ) -> None:
        """Test listing orders for non-existent bot."""
        from uuid import uuid4

        fake_bot_id = str(uuid4())
        response = await auth_client.get(f"/orders/bots/{fake_bot_id}/orders")

        assert response.status_code == 404

    async def test_list_orders_empty(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test listing orders when none exist."""
        from api.models.orm import Bot

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="stopped",
        )
        db_session.add(bot)
        await db_session.flush()
        await db_session.refresh(bot)

        response = await auth_client.get(f"/orders/bots/{bot.id}/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["orders"] == []
        assert data["total"] == 0

    async def test_list_orders_with_data(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test listing orders when orders exist."""
        from decimal import Decimal

        from api.models.orm import Bot, Order

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="stopped",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create orders
        order1 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0"),
            status="open",
        )
        order2 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="sell",
            type="limit",
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0"),
            status="open",
        )
        db_session.add_all([order1, order2])
        await db_session.flush()

        response = await auth_client.get(f"/orders/bots/{bot.id}/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["orders"]) == 2

    async def test_list_orders_with_status_filter(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test filtering orders by status."""
        from decimal import Decimal

        from api.models.orm import Bot, Order

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="stopped",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create orders with different statuses
        order1 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0"),
            status="open",
        )
        order2 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="sell",
            type="limit",
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0.1"),
            status="filled",
        )
        db_session.add_all([order1, order2])
        await db_session.flush()

        # Filter by open status
        response = await auth_client.get(f"/orders/bots/{bot.id}/orders?status=open")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["orders"][0]["status"] == "open"

    async def test_get_open_orders(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test getting only open orders."""
        from decimal import Decimal

        from api.models.orm import Bot, Order

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="running",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create orders
        order1 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0"),
            status="open",
        )
        order2 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            price=Decimal("48000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0.05"),
            status="partially_filled",
        )
        order3 = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="sell",
            type="limit",
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0.1"),
            status="filled",
        )
        db_session.add_all([order1, order2, order3])
        await db_session.flush()

        response = await auth_client.get(f"/orders/bots/{bot.id}/orders/open")

        assert response.status_code == 200
        data = response.json()
        # Only open and partially_filled should be returned
        assert len(data) == 2
        statuses = [o["status"] for o in data]
        assert "open" in statuses
        assert "partially_filled" in statuses
        assert "filled" not in statuses

    async def test_get_trades_empty(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test getting trades when none exist."""
        from api.models.orm import Bot

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="stopped",
        )
        db_session.add(bot)
        await db_session.flush()

        response = await auth_client.get(f"/orders/bots/{bot.id}/trades")

        assert response.status_code == 200
        data = response.json()
        assert data["trades"] == []
        assert data["total"] == 0

    async def test_get_trades_with_data(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test getting trades when trades exist."""
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal

        from api.models.orm import Bot, Trade

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="running",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create trades with different timestamps
        now = datetime.now(timezone.utc)
        trade1 = Trade(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            fee=Decimal("0.01"),
            fee_currency="USDT",
            timestamp=now - timedelta(seconds=10),
        )
        trade2 = Trade(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="sell",
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            fee=Decimal("0.01"),
            fee_currency="USDT",
            realized_pnl=Decimal("200"),
            timestamp=now,
        )
        db_session.add_all([trade1, trade2])
        await db_session.flush()

        response = await auth_client.get(f"/orders/bots/{bot.id}/trades")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["trades"]) == 2

    async def test_get_statistics(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test getting bot statistics."""
        from datetime import datetime, timedelta, timezone
        from decimal import Decimal

        from api.models.orm import Bot, Order, Trade

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="running",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create orders with different statuses
        orders = [
            Order(bot_id=bot.id, symbol="BTC/USDT", side="buy", type="limit",
                  price=Decimal("49000"), quantity=Decimal("0.1"), filled_quantity=Decimal("0"), status="open"),
            Order(bot_id=bot.id, symbol="BTC/USDT", side="buy", type="limit",
                  price=Decimal("48000"), quantity=Decimal("0.1"), filled_quantity=Decimal("0.1"), status="filled"),
            Order(bot_id=bot.id, symbol="BTC/USDT", side="sell", type="limit",
                  price=Decimal("51000"), quantity=Decimal("0.1"), filled_quantity=Decimal("0.1"), status="filled"),
        ]
        db_session.add_all(orders)

        # Create trades with different timestamps
        now = datetime.now(timezone.utc)
        trades = [
            Trade(bot_id=bot.id, symbol="BTC/USDT", side="buy",
                  price=Decimal("48000"), quantity=Decimal("0.1"), fee=Decimal("0.01"),
                  timestamp=now - timedelta(seconds=10)),
            Trade(bot_id=bot.id, symbol="BTC/USDT", side="sell",
                  price=Decimal("51000"), quantity=Decimal("0.1"), fee=Decimal("0.01"), realized_pnl=Decimal("300"),
                  timestamp=now),
        ]
        db_session.add_all(trades)
        await db_session.flush()

        response = await auth_client.get(f"/orders/bots/{bot.id}/statistics")

        assert response.status_code == 200
        data = response.json()

        # Check orders stats
        assert data["orders"]["total"] == 3
        assert data["orders"]["by_status"]["open"] == 1
        assert data["orders"]["by_status"]["filled"] == 2

        # Check trades stats
        assert data["trades"]["total"] == 2
        assert data["trades"]["total_pnl"] == 300.0

    async def test_cancel_order_not_found(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test cancelling non-existent order."""
        from uuid import uuid4

        from api.models.orm import Bot

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="stopped",
        )
        db_session.add(bot)
        await db_session.flush()

        fake_order_id = str(uuid4())
        response = await auth_client.post(
            f"/orders/bots/{bot.id}/orders/{fake_order_id}/cancel"
        )

        assert response.status_code == 404

    async def test_cancel_order_success(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test successfully cancelling an open order."""
        from decimal import Decimal

        from api.models.orm import Bot, Order

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="running",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create an open order
        order = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0"),
            status="open",
        )
        db_session.add(order)
        await db_session.flush()

        response = await auth_client.post(
            f"/orders/bots/{bot.id}/orders/{order.id}/cancel"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert "Order cancellation requested" in data["message"]

    async def test_cancel_filled_order_fails(
        self,
        auth_client: AsyncClient,
        db_session,
        test_user: User,
        test_credential: ExchangeCredential,
    ) -> None:
        """Test that cancelling a filled order fails."""
        from decimal import Decimal

        from api.models.orm import Bot, Order

        # Create a test bot
        bot = Bot(
            user_id=test_user.id,
            credential_id=test_credential.id,
            name="Test Bot",
            strategy="grid",
            exchange="binance",
            symbol="BTC/USDT",
            config={"lower_price": 45000, "upper_price": 55000, "grid_count": 10, "investment": 1000},
            status="running",
        )
        db_session.add(bot)
        await db_session.flush()

        # Create a filled order
        order = Order(
            bot_id=bot.id,
            symbol="BTC/USDT",
            side="buy",
            type="limit",
            price=Decimal("49000"),
            quantity=Decimal("0.1"),
            filled_quantity=Decimal("0.1"),
            status="filled",
        )
        db_session.add(order)
        await db_session.flush()

        response = await auth_client.post(
            f"/orders/bots/{bot.id}/orders/{order.id}/cancel"
        )

        assert response.status_code == 409  # Conflict
