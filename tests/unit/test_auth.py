"""
Unit Tests for Authentication Services.

Tests for password hashing and JWT token handling.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.services.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    verify_token_type,
)
from api.services.security import hash_password, verify_password


class TestPasswordHashing:
    """Tests for password hashing functionality."""

    def test_hash_password_returns_hash(self) -> None:
        """Password hashing should return a bcrypt hash."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix
        assert len(hashed) == 60  # bcrypt hash length

    def test_hash_password_unique_hashes(self) -> None:
        """Each hash should be unique due to random salt."""
        password = "TestPassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2

    def test_verify_password_correct(self) -> None:
        """Correct password should verify successfully."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Incorrect password should fail verification."""
        password = "TestPassword123!"
        wrong_password = "WrongPassword456!"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty(self) -> None:
        """Empty password should fail verification."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

    def test_hash_special_characters(self) -> None:
        """Password with special characters should hash correctly."""
        password = "Test@#$%^&*()123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_hash_unicode_password(self) -> None:
        """Unicode password should hash correctly."""
        password = "TesteSenha123!ção"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True


class TestJWTTokens:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self) -> None:
        """Access token should be created with correct claims."""
        user_id = uuid4()
        token = create_access_token(user_id)

        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long

        # Decode and verify
        payload = decode_token(token)
        assert payload.sub == str(user_id)
        assert payload.type == "access"
        assert payload.exp > datetime.now(timezone.utc)

    def test_create_refresh_token(self) -> None:
        """Refresh token should be created with correct claims."""
        user_id = uuid4()
        token = create_refresh_token(user_id)

        payload = decode_token(token)
        assert payload.sub == str(user_id)
        assert payload.type == "refresh"

    def test_create_token_pair(self) -> None:
        """Token pair should return both access and refresh tokens."""
        user_id = uuid4()
        access_token, refresh_token = create_token_pair(user_id)

        # Verify access token
        access_payload = decode_token(access_token)
        assert access_payload.type == "access"

        # Verify refresh token
        refresh_payload = decode_token(refresh_token)
        assert refresh_payload.type == "refresh"

        # Both should have same user_id
        assert access_payload.sub == refresh_payload.sub == str(user_id)

    def test_access_token_expiry(self) -> None:
        """Access token should expire after configured time."""
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_token(token)

        # Check expiry is in the future but within reasonable bounds
        now = datetime.now(timezone.utc)
        assert payload.exp > now
        assert payload.exp < now + timedelta(hours=48)  # Should be less than 48 hours

    def test_refresh_token_longer_expiry(self) -> None:
        """Refresh token should have longer expiry than access token."""
        user_id = uuid4()
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)

        access_payload = decode_token(access_token)
        refresh_payload = decode_token(refresh_token)

        assert refresh_payload.exp > access_payload.exp

    def test_decode_invalid_token(self) -> None:
        """Decoding invalid token should raise TokenError."""
        with pytest.raises(TokenError):
            decode_token("invalid.token.here")

    def test_decode_malformed_token(self) -> None:
        """Decoding malformed token should raise TokenError."""
        with pytest.raises(TokenError):
            decode_token("not-a-jwt")

    def test_verify_token_type_correct(self) -> None:
        """Verifying correct token type should succeed."""
        user_id = uuid4()
        access_token = create_access_token(user_id)

        payload = verify_token_type(access_token, "access")
        assert payload.type == "access"

    def test_verify_token_type_wrong(self) -> None:
        """Verifying wrong token type should raise TokenError."""
        user_id = uuid4()
        access_token = create_access_token(user_id)

        with pytest.raises(TokenError) as exc_info:
            verify_token_type(access_token, "refresh")

        assert "Expected refresh token" in str(exc_info.value)

    def test_token_contains_issued_at(self) -> None:
        """Token should contain iat (issued at) claim."""
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_token(token)

        assert payload.iat is not None
        assert payload.iat <= datetime.now(timezone.utc)
