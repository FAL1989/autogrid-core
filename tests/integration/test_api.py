"""
Integration Tests for API

Tests for API endpoints with mocked dependencies.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for health check endpoint."""

    async def test_health_check(self, async_client: AsyncClient) -> None:
        """Test health check returns ok."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


@pytest.mark.asyncio
class TestAuthEndpoints:
    """Tests for authentication endpoints."""

    async def test_register_success(self, async_client: AsyncClient) -> None:
        """Test successful user registration."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"] == "test@example.com"

    async def test_register_invalid_email(self, async_client: AsyncClient) -> None:
        """Test registration with invalid email."""
        response = await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "password": "SecurePass123!",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_login_success(self, async_client: AsyncClient) -> None:
        """Test successful login."""
        # First register
        await async_client.post(
            "/api/v1/auth/register",
            json={
                "email": "login@example.com",
                "password": "SecurePass123!",
            },
        )

        # Then login
        response = await async_client.post(
            "/api/v1/auth/login",
            json={
                "email": "login@example.com",
                "password": "SecurePass123!",
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

    async def test_list_bots_empty(self, async_client: AsyncClient) -> None:
        """Test listing bots when none exist."""
        response = await async_client.get("/api/v1/bots")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    async def test_create_grid_bot(self, async_client: AsyncClient, grid_config: dict) -> None:
        """Test creating a grid trading bot."""
        response = await async_client.post(
            "/api/v1/bots",
            json={
                "name": "Test Grid Bot",
                "strategy": "grid",
                "exchange": "binance",
                "symbol": grid_config["symbol"],
                "config": {
                    "lower_price": grid_config["lower_price"],
                    "upper_price": grid_config["upper_price"],
                    "grid_count": grid_config["grid_count"],
                    "investment": grid_config["investment"],
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Grid Bot"
        assert data["strategy"] == "grid"

    async def test_create_dca_bot(self, async_client: AsyncClient, dca_config: dict) -> None:
        """Test creating a DCA bot."""
        response = await async_client.post(
            "/api/v1/bots",
            json={
                "name": "Test DCA Bot",
                "strategy": "dca",
                "exchange": "binance",
                "symbol": dca_config["symbol"],
                "config": {
                    "investment": dca_config["investment"],
                    "amount_per_buy": dca_config["amount_per_buy"],
                    "interval": dca_config["interval"],
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test DCA Bot"
        assert data["strategy"] == "dca"
