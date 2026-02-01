"""
Rate Limiting.

Redis-based rate limiting for API endpoints.
Uses sliding window algorithm for accurate rate limiting.

Supports:
- IP-based rate limiting (for auth endpoints)
- User-based rate limiting (for authenticated endpoints)
- Differentiated limits by operation type
"""

from enum import Enum
from typing import Annotated, Callable
from uuid import UUID

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status

from api.core.config import get_settings


class RateLimitTier(Enum):
    """Rate limit tiers for different operation types."""

    AUTH = "auth"  # 5 requests per minute
    ORDERS = "orders"  # 30 requests per minute
    TRADES = "trades"  # 60 requests per minute
    READS = "reads"  # 100 requests per minute


# Default limits per tier (requests per minute)
TIER_LIMITS: dict[RateLimitTier, tuple[int, int]] = {
    RateLimitTier.AUTH: (5, 60),  # 5 requests per 60 seconds
    RateLimitTier.ORDERS: (30, 60),  # 30 requests per 60 seconds
    RateLimitTier.TRADES: (60, 60),  # 60 requests per 60 seconds
    RateLimitTier.READS: (100, 60),  # 100 requests per 60 seconds
}

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
    client_ip = _get_client_ip(request)
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


class RateLimitByUser:
    """
    Rate limiter dependency that limits by authenticated user.

    Can be used as a FastAPI dependency with configurable limits.

    Example:
        @router.post("/orders", dependencies=[Depends(RateLimitByUser(30, 60))])
        async def create_order(...):
            ...

        # Or with tier:
        @router.get("/trades", dependencies=[Depends(RateLimitByUser.for_tier(RateLimitTier.TRADES))])
        async def get_trades(...):
            ...
    """

    def __init__(
        self,
        requests: int,
        window: int,
        tier: RateLimitTier | None = None,
    ) -> None:
        """
        Initialize user-based rate limiter.

        Args:
            requests: Maximum requests allowed in the window.
            window: Time window in seconds.
            tier: Optional tier name for key namespacing.
        """
        self.requests = requests
        self.window = window
        self.tier = tier

    @classmethod
    def for_tier(cls, tier: RateLimitTier) -> "RateLimitByUser":
        """
        Create rate limiter for a specific tier.

        Args:
            tier: The rate limit tier.

        Returns:
            Configured RateLimitByUser instance.
        """
        requests, window = TIER_LIMITS[tier]
        return cls(requests=requests, window=window, tier=tier)

    async def __call__(
        self,
        request: Request,
        redis_client: redis.Redis = Depends(get_redis),
    ) -> None:
        """
        Check rate limit for the current user.

        Args:
            request: FastAPI request object.
            redis_client: Redis client.

        Raises:
            HTTPException 429: If rate limit exceeded.
        """
        # Try to get user_id from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)

        if user_id is None:
            # Fall back to IP-based limiting for unauthenticated requests
            identifier = _get_client_ip(request)
            key_prefix = "rate_limit:ip"
        else:
            identifier = str(user_id)
            key_prefix = "rate_limit:user"

        tier_name = self.tier.value if self.tier else "default"
        key = f"{key_prefix}:{tier_name}:{identifier}"

        limiter = RateLimiter(redis_client)

        if await limiter.is_rate_limited(key, self.requests, self.window):
            ttl = await limiter.get_ttl(key)
            remaining = await limiter.get_remaining(key, self.requests)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {ttl} seconds.",
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(self.requests),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(ttl),
                },
            )


async def rate_limit_user_orders(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis),
) -> None:
    """Rate limit dependency for order endpoints (30/min)."""
    limiter = RateLimitByUser.for_tier(RateLimitTier.ORDERS)
    await limiter(request, redis_client)


async def rate_limit_user_trades(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis),
) -> None:
    """Rate limit dependency for trade endpoints (60/min)."""
    limiter = RateLimitByUser.for_tier(RateLimitTier.TRADES)
    await limiter(request, redis_client)


async def rate_limit_user_reads(
    request: Request,
    redis_client: redis.Redis = Depends(get_redis),
) -> None:
    """Rate limit dependency for read endpoints (100/min)."""
    limiter = RateLimitByUser.for_tier(RateLimitTier.READS)
    await limiter(request, redis_client)


# Type aliases for common rate limit dependencies
RateLimitOrders = Annotated[None, Depends(rate_limit_user_orders)]
RateLimitTrades = Annotated[None, Depends(rate_limit_user_trades)]
RateLimitReads = Annotated[None, Depends(rate_limit_user_reads)]


def _get_client_ip(request: Request) -> str:
    """Resolve client IP address, honoring proxy headers when present."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return "unknown"
