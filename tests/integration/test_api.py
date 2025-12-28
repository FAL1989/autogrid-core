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
