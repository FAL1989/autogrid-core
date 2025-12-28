"""
User Service.

Business logic for user operations including CRUD and authentication.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.orm import User
from api.services.security import hash_password, verify_password


class UserService:
    """Service for user-related operations."""

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize UserService.

        Args:
            db: Async database session.
        """
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        """
        Get user by ID.

        Args:
            user_id: The user's UUID.

        Returns:
            User if found, None otherwise.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """
        Get user by email.

        Args:
            email: The user's email address.

        Returns:
            User if found, None otherwise.
        """
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def create(self, email: str, password: str) -> User:
        """
        Create a new user.

        Args:
            email: User's email address.
            password: Plain text password (will be hashed).

        Returns:
            The created User object.
        """
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        """
        Authenticate user by email and password.

        Args:
            email: User's email address.
            password: Plain text password.

        Returns:
            User if credentials are valid, None otherwise.
        """
        user = await self.get_by_email(email)

        if user is None:
            return None

        if not verify_password(password, user.password_hash):
            return None

        if not user.is_active:
            return None

        return user

    async def update_password(self, user_id: UUID, new_password: str) -> bool:
        """
        Update user's password.

        Args:
            user_id: The user's UUID.
            new_password: New plain text password.

        Returns:
            True if updated, False if user not found.
        """
        user = await self.get_by_id(user_id)

        if user is None:
            return False

        user.password_hash = hash_password(new_password)
        await self.db.flush()
        return True

    async def deactivate(self, user_id: UUID) -> bool:
        """
        Deactivate a user account.

        Args:
            user_id: The user's UUID.

        Returns:
            True if deactivated, False if user not found.
        """
        user = await self.get_by_id(user_id)

        if user is None:
            return False

        user.is_active = False
        await self.db.flush()
        return True

    async def email_exists(self, email: str) -> bool:
        """
        Check if email is already registered.

        Args:
            email: Email address to check.

        Returns:
            True if email exists, False otherwise.
        """
        user = await self.get_by_email(email)
        return user is not None
