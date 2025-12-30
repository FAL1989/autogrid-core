"""
Credential Service.

Business logic for exchange credential operations.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import ExchangeCredential
from api.services.encryption import get_encryption_service
from bot.exchange.connector import CCXTConnector, ValidationResult


class CredentialValidationError(Exception):
    """Raised when credential validation fails."""

    pass


class CredentialService:
    """Service for exchange credential operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize CredentialService."""
        self.db = db
        self.encryption = get_encryption_service()

    async def get_by_id(self, credential_id: UUID) -> ExchangeCredential | None:
        """Get credential by ID."""
        result = await self.db.execute(
            select(ExchangeCredential).where(ExchangeCredential.id == credential_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(
        self,
        credential_id: UUID,
        user_id: UUID,
    ) -> ExchangeCredential | None:
        """Get credential by ID, ensuring it belongs to user."""
        result = await self.db.execute(
            select(ExchangeCredential).where(
                ExchangeCredential.id == credential_id,
                ExchangeCredential.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ExchangeCredential], int]:
        """List all credentials for a user with pagination."""
        # Get total count
        count_result = await self.db.execute(
            select(func.count())
            .select_from(ExchangeCredential)
            .where(ExchangeCredential.user_id == user_id)
        )
        total = count_result.scalar() or 0

        # Get paginated credentials
        result = await self.db.execute(
            select(ExchangeCredential)
            .where(ExchangeCredential.user_id == user_id)
            .order_by(ExchangeCredential.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        credentials = list(result.scalars().all())

        return credentials, total

    async def create(
        self,
        user_id: UUID,
        exchange: str,
        api_key: str,
        api_secret: str,
        is_testnet: bool = False,
    ) -> tuple[ExchangeCredential, ValidationResult]:
        """
        Create a new exchange credential.

        Validates credentials with exchange before saving.
        Encrypts API key and secret before storage.

        Args:
            user_id: Owner's UUID.
            exchange: Exchange identifier (binance, mexc, bybit).
            api_key: Plain API key.
            api_secret: Plain API secret.
            is_testnet: Whether to use testnet.

        Returns:
            Tuple of (created credential, validation result).

        Raises:
            CredentialValidationError: If credentials are invalid or don't have trade permission.
        """
        # Validate credentials with exchange
        connector = CCXTConnector(
            exchange_id=exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=is_testnet,
        )

        validation = await connector.validate_credentials()

        if not validation.is_valid:
            raise CredentialValidationError(
                validation.error or "Invalid credentials"
            )

        if not validation.can_trade:
            raise CredentialValidationError(
                "API key must have trade permission enabled"
            )

        # Encrypt sensitive data
        api_key_encrypted = self.encryption.encrypt(api_key)
        api_secret_encrypted = self.encryption.encrypt(api_secret)

        # Build permissions dict
        permissions = {
            "trade": validation.can_trade,
            "withdraw": validation.can_withdraw,
            "is_safe": not validation.can_withdraw,  # Safe if withdraw is disabled
        }

        # Create credential
        credential = ExchangeCredential(
            user_id=user_id,
            exchange=exchange,
            api_key_encrypted=api_key_encrypted,
            api_secret_encrypted=api_secret_encrypted,
            is_testnet=is_testnet,
            permissions=permissions,
        )

        self.db.add(credential)
        await self.db.flush()
        await self.db.refresh(credential)

        return credential, validation

    def get_decrypted_keys(
        self,
        credential: ExchangeCredential,
    ) -> tuple[str, str]:
        """
        Get decrypted API key and secret for a credential.

        Args:
            credential: The credential to decrypt.

        Returns:
            Tuple of (api_key, api_secret).
        """
        api_key = self.encryption.decrypt(credential.api_key_encrypted)
        api_secret = self.encryption.decrypt(credential.api_secret_encrypted)
        return api_key, api_secret

    async def delete(self, credential_id: UUID, user_id: UUID) -> bool:
        """
        Delete a credential.

        Args:
            credential_id: The credential's UUID.
            user_id: The owner's UUID (for verification).

        Returns:
            True if deleted, False if not found.
        """
        credential = await self.get_by_id_for_user(credential_id, user_id)

        if credential is None:
            return False

        await self.db.delete(credential)
        await self.db.flush()
        return True

    async def refresh_markets(
        self,
        credential_id: UUID,
        user_id: UUID,
    ) -> list[str]:
        """
        Refresh markets for a credential's exchange.

        Args:
            credential_id: The credential's UUID.
            user_id: The owner's UUID.

        Returns:
            List of available market symbols.

        Raises:
            ValueError: If credential not found.
        """
        credential = await self.get_by_id_for_user(credential_id, user_id)

        if credential is None:
            raise ValueError("Credential not found")

        api_key, api_secret = self.get_decrypted_keys(credential)

        connector = CCXTConnector(
            exchange_id=credential.exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=credential.is_testnet,
        )

        await connector.connect()
        try:
            markets = await connector.refresh_markets()
        finally:
            await connector.disconnect()

        return markets

    async def fetch_ticker(
        self,
        credential_id: UUID,
        user_id: UUID,
        symbol: str,
    ) -> dict:
        """
        Fetch current ticker for a symbol using the credential's exchange.

        Args:
            credential_id: The credential's UUID.
            user_id: The owner's UUID.
            symbol: Trading pair symbol (e.g. BTC/USDT).

        Returns:
            CCXT ticker dict.
        """
        credential = await self.get_by_id_for_user(credential_id, user_id)
        if credential is None:
            raise ValueError("Credential not found")

        api_key, api_secret = self.get_decrypted_keys(credential)

        connector = CCXTConnector(
            exchange_id=credential.exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=credential.is_testnet,
        )

        await connector.connect()
        try:
            ticker = await connector.fetch_ticker(symbol)
        finally:
            await connector.disconnect()

        return ticker

    async def fetch_balance(
        self,
        credential_id: UUID,
        user_id: UUID,
    ) -> dict:
        """
        Fetch account balance using the credential's exchange.

        Args:
            credential_id: The credential's UUID.
            user_id: The owner's UUID.

        Returns:
            CCXT balance dict.
        """
        credential = await self.get_by_id_for_user(credential_id, user_id)
        if credential is None:
            raise ValueError("Credential not found")

        api_key, api_secret = self.get_decrypted_keys(credential)

        connector = CCXTConnector(
            exchange_id=credential.exchange,
            api_key=api_key,
            api_secret=api_secret,
            testnet=credential.is_testnet,
        )

        await connector.connect()
        try:
            balance = await connector.fetch_balance()
        finally:
            await connector.disconnect()

        return balance
