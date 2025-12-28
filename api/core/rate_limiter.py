"""
Rate Limiting.

Redis-based rate limiting for API endpoints.
Uses sliding window algorithm for accurate rate limiting.
"""

from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status

from api.core.config import get_settings

# Global Redis client (initialized on app startup)
_redis_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    """
    Initialize Redis connection.

    Returns:
        Redis client instance.
    """
    global _redis_client
    settings = get_settings()
    _redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    return _redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def get_redis() -> redis.Redis:
    """
    Get Redis client dependency.

    Returns:
        Redis client instance.

    Raises:
        RuntimeError: If Redis is not initialized.
    """
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")
    return _redis_client


class RateLimiter:
    """
    Rate limiter using Redis sliding window.

    Tracks request counts per key within a time window.
    """

    def __init__(self, redis_client: redis.Redis) -> None:
        """
        Initialize RateLimiter.

        Args:
            redis_client: Redis client instance.
        """
        self.redis = redis_client

    async def is_rate_limited(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> bool:
        """
        Check if request should be rate limited.

        Uses a simple counter with TTL for sliding window effect.

        Args:
            key: Unique identifier for the rate limit (e.g., IP address).
            limit: Maximum requests allowed in the window.
            window: Time window in seconds.

        Returns:
            True if rate limited (request should be blocked), False otherwise.
        """
        current = await self.redis.incr(key)

        if current == 1:
            # First request, set expiry
            await self.redis.expire(key, window)

        return current > limit

    async def get_remaining(self, key: str, limit: int) -> int:
        """
        Get remaining requests in current window.

        Args:
            key: Rate limit key.
            limit: Maximum requests allowed.

        Returns:
            Number of remaining requests.
        """
        current = await self.redis.get(key)
        if current is None:
            return limit
        return max(0, limit - int(current))

    async def get_ttl(self, key: str) -> int:
        """
        Get time until rate limit resets.

        Args:
            key: Rate limit key.

        Returns:
            Seconds until reset, or -1 if key doesn't exist.
        """
        ttl = await self.redis.ttl(key)
        return max(0, ttl)


async def rate_limit_auth(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis),
) -> None:
    """
    Rate limit dependency for authentication endpoints.

    Limits requests by client IP address.

    Args:
        request: FastAPI request object.
        redis_client: Redis client.

    Raises:
        HTTPException 429: If rate limit exceeded.
    """
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:auth:{client_ip}"

    limiter = RateLimiter(redis_client)

    if await limiter.is_rate_limited(
        key,
        settings.rate_limit_requests,
        settings.rate_limit_window,
    ):
        ttl = await limiter.get_ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Try again in {ttl} seconds.",
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(settings.rate_limit_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(ttl),
            },
        )


# Type alias for dependency injection
RateLimitAuth = Annotated[None, Depends(rate_limit_auth)]
