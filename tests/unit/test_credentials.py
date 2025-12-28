"""Unit tests for credential service."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from api.services.credential_service import (
    CredentialService,
    CredentialValidationError,
)
from bot.exchange.connector import ValidationResult


class TestCredentialService:
    """Tests for CredentialService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_encryption(self) -> MagicMock:
        """Create mock encryption service."""
        mock = MagicMock()
        mock.encrypt.side_effect = lambda x: f"encrypted_{x}"
        mock.decrypt.side_effect = lambda x: x.replace("encrypted_", "")
        return mock

    @pytest.mark.asyncio
    async def test_create_validates_credentials(
        self, mock_db: AsyncMock, mock_encryption: MagicMock
    ) -> None:
        """Create should validate credentials with exchange."""
        with patch(
            "api.services.credential_service.get_encryption_service",
            return_value=mock_encryption,
        ):
            with patch(
                "api.services.credential_service.CCXTConnector"
            ) as mock_connector_class:
                # Setup mock
                mock_connector = AsyncMock()
                mock_connector.validate_credentials.return_value = ValidationResult(
                    is_valid=True,
                    can_trade=True,
                    can_withdraw=False,
                    markets=["BTC/USDT", "ETH/USDT"],
                )
                mock_connector_class.return_value = mock_connector

                service = CredentialService(mock_db)

                await service.create(
                    user_id=uuid4(),
                    exchange="binance",
                    api_key="test-key",
                    api_secret="test-secret",
                )

                mock_connector.validate_credentials.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_fails_without_trade_permission(
        self, mock_db: AsyncMock, mock_encryption: MagicMock
    ) -> None:
        """Create should fail if trade permission is missing."""
        with patch(
            "api.services.credential_service.get_encryption_service",
            return_value=mock_encryption,
        ):
            with patch(
                "api.services.credential_service.CCXTConnector"
            ) as mock_connector_class:
                mock_connector = AsyncMock()
                mock_connector.validate_credentials.return_value = ValidationResult(
                    is_valid=True,
                    can_trade=False,  # No trade permission
                    can_withdraw=False,
                    markets=[],
                )
                mock_connector_class.return_value = mock_connector

                service = CredentialService(mock_db)

                with pytest.raises(CredentialValidationError) as exc_info:
                    await service.create(
                        user_id=uuid4(),
                        exchange="binance",
                        api_key="test-key",
                        api_secret="test-secret",
                    )

                assert "trade permission" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_fails_with_invalid_credentials(
        self, mock_db: AsyncMock, mock_encryption: MagicMock
    ) -> None:
        """Create should fail if credentials are invalid."""
        with patch(
            "api.services.credential_service.get_encryption_service",
            return_value=mock_encryption,
        ):
            with patch(
                "api.services.credential_service.CCXTConnector"
            ) as mock_connector_class:
                mock_connector = AsyncMock()
                mock_connector.validate_credentials.return_value = ValidationResult(
                    is_valid=False,
                    can_trade=False,
                    can_withdraw=False,
                    markets=[],
                    error="Invalid API key",
                )
                mock_connector_class.return_value = mock_connector

                service = CredentialService(mock_db)

                with pytest.raises(CredentialValidationError) as exc_info:
                    await service.create(
                        user_id=uuid4(),
                        exchange="binance",
                        api_key="invalid-key",
                        api_secret="invalid-secret",
                    )

                assert "Invalid API key" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_encrypts_keys(
        self, mock_db: AsyncMock, mock_encryption: MagicMock
    ) -> None:
        """Create should encrypt API keys before storage."""
        with patch(
            "api.services.credential_service.get_encryption_service",
            return_value=mock_encryption,
        ):
            with patch(
                "api.services.credential_service.CCXTConnector"
            ) as mock_connector_class:
                mock_connector = AsyncMock()
                mock_connector.validate_credentials.return_value = ValidationResult(
                    is_valid=True,
                    can_trade=True,
                    can_withdraw=False,
                    markets=[],
                )
                mock_connector_class.return_value = mock_connector

                service = CredentialService(mock_db)

                await service.create(
                    user_id=uuid4(),
                    exchange="binance",
                    api_key="my-api-key",
                    api_secret="my-api-secret",
                )

                # Verify encryption was called
                mock_encryption.encrypt.assert_any_call("my-api-key")
                mock_encryption.encrypt.assert_any_call("my-api-secret")

    @pytest.mark.asyncio
    async def test_create_allows_withdraw_with_warning(
        self, mock_db: AsyncMock, mock_encryption: MagicMock
    ) -> None:
        """Create should allow credentials with withdraw permission (but mark as unsafe)."""
        with patch(
            "api.services.credential_service.get_encryption_service",
            return_value=mock_encryption,
        ):
            with patch(
                "api.services.credential_service.CCXTConnector"
            ) as mock_connector_class:
                mock_connector = AsyncMock()
                mock_connector.validate_credentials.return_value = ValidationResult(
                    is_valid=True,
                    can_trade=True,
                    can_withdraw=True,  # Withdraw enabled
                    markets=["BTC/USDT"],
                )
                mock_connector_class.return_value = mock_connector

                service = CredentialService(mock_db)

                credential, validation = await service.create(
                    user_id=uuid4(),
                    exchange="binance",
                    api_key="test-key",
                    api_secret="test-secret",
                )

                # Should succeed but mark as not safe
                assert validation.can_withdraw is True
                # The credential should have permissions dict indicating it's not safe
                mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_decrypted_keys(
        self, mock_db: AsyncMock, mock_encryption: MagicMock
    ) -> None:
        """get_decrypted_keys should return decrypted API key and secret."""
        with patch(
            "api.services.credential_service.get_encryption_service",
            return_value=mock_encryption,
        ):
            service = CredentialService(mock_db)

            # Create a mock credential
            mock_credential = MagicMock()
            mock_credential.api_key_encrypted = "encrypted_my-api-key"
            mock_credential.api_secret_encrypted = "encrypted_my-api-secret"

            api_key, api_secret = service.get_decrypted_keys(mock_credential)

            assert api_key == "my-api-key"
            assert api_secret == "my-api-secret"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_valid(self) -> None:
        """Test valid validation result."""
        result = ValidationResult(
            is_valid=True,
            can_trade=True,
            can_withdraw=False,
            markets=["BTC/USDT", "ETH/USDT"],
        )

        assert result.is_valid is True
        assert result.can_trade is True
        assert result.can_withdraw is False
        assert len(result.markets) == 2
        assert result.error is None

    def test_validation_result_invalid(self) -> None:
        """Test invalid validation result."""
        result = ValidationResult(
            is_valid=False,
            can_trade=False,
            can_withdraw=False,
            error="Authentication failed",
        )

        assert result.is_valid is False
        assert result.error == "Authentication failed"
        assert len(result.markets) == 0
