"""
Encryption Service.

Provides Fernet encryption for sensitive data like API keys.
"""

from cryptography.fernet import Fernet, InvalidToken

from api.core.config import get_settings


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""

    pass


class EncryptionService:
    """
    Service for encrypting/decrypting sensitive data using Fernet.

    Fernet guarantees that a message encrypted using it cannot be
    manipulated or read without the key.
    """

    def __init__(self) -> None:
        """Initialize with encryption key from settings."""
        settings = get_settings()
        # Fernet requires a 32-byte base64-encoded key
        self._fernet = Fernet(settings.encryption_key.encode())

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt.

        Returns:
            Base64-encoded encrypted string.
        """
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted string.

        Args:
            ciphertext: Base64-encoded encrypted string.

        Returns:
            Decrypted plaintext string.

        Raises:
            EncryptionError: If decryption fails (invalid key or corrupted data).
        """
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise EncryptionError(
                "Failed to decrypt data. Invalid key or corrupted data."
            ) from e


# Singleton instance
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Get or create singleton EncryptionService."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
