"""Unit tests for encryption service."""

import pytest
from cryptography.fernet import Fernet

from api.services.encryption import EncryptionError, EncryptionService


class TestEncryptionService:
    """Tests for EncryptionService."""

    @pytest.fixture
    def encryption_service(self, monkeypatch) -> EncryptionService:
        """Create encryption service with test key."""
        # Generate a valid Fernet key for testing
        test_key = Fernet.generate_key().decode()

        # Mock the settings
        class MockSettings:
            encryption_key = test_key

        monkeypatch.setattr(
            "api.services.encryption.get_settings",
            lambda: MockSettings(),
        )

        # Reset singleton
        import api.services.encryption as enc_module

        enc_module._encryption_service = None

        return EncryptionService()

    def test_encrypt_returns_different_value(
        self, encryption_service: EncryptionService
    ) -> None:
        """Encrypted value should differ from plaintext."""
        plaintext = "my-secret-api-key"
        encrypted = encryption_service.encrypt(plaintext)

        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)

    def test_decrypt_returns_original(
        self, encryption_service: EncryptionService
    ) -> None:
        """Decrypted value should match original."""
        plaintext = "my-secret-api-key"
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_decrypt_invalid_data_raises_error(
        self, encryption_service: EncryptionService
    ) -> None:
        """Decrypting invalid data should raise EncryptionError."""
        with pytest.raises(EncryptionError):
            encryption_service.decrypt("invalid-encrypted-data")

    def test_encrypt_empty_string(
        self, encryption_service: EncryptionService
    ) -> None:
        """Empty string should encrypt and decrypt correctly."""
        plaintext = ""
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_unicode(
        self, encryption_service: EncryptionService
    ) -> None:
        """Unicode strings should encrypt correctly."""
        plaintext = "secret-key-with-unicode-acao-teste"
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_different_encryptions_produce_different_ciphertext(
        self, encryption_service: EncryptionService
    ) -> None:
        """Same plaintext encrypted twice should produce different ciphertext (due to IV)."""
        plaintext = "my-secret-api-key"
        encrypted1 = encryption_service.encrypt(plaintext)
        encrypted2 = encryption_service.encrypt(plaintext)

        # Fernet uses random IV, so ciphertexts should differ
        assert encrypted1 != encrypted2

        # But both should decrypt to same value
        assert encryption_service.decrypt(encrypted1) == plaintext
        assert encryption_service.decrypt(encrypted2) == plaintext

    def test_long_string_encryption(
        self, encryption_service: EncryptionService
    ) -> None:
        """Long strings should encrypt correctly."""
        plaintext = "a" * 10000
        encrypted = encryption_service.encrypt(plaintext)
        decrypted = encryption_service.decrypt(encrypted)

        assert decrypted == plaintext
