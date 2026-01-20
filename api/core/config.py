"""
Application Configuration.

Centralized settings management using pydantic-settings.
All configuration is loaded from environment variables.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/autogrid"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # JWT Configuration
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    jwt_refresh_expire_days: int = 7

    # Security
    encryption_key: str

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False
    cors_origins: str = "http://localhost:3000"

    # Rate Limiting
    rate_limit_requests: int = 5  # requests per minute for auth endpoints
    rate_limit_window: int = 60  # window in seconds

    # Exchange timeouts (seconds / milliseconds)
    exchange_timeout_ms: int = 10000  # CCXT request timeout in ms
    exchange_rest_timeout_seconds: int = 10  # REST timeouts for WS listen-key ops

    # Bot execution timeouts
    bot_tick_timeout_seconds: int = 15
    order_sync_timeout_seconds: int = 10

    # Bot runtime
    bot_runtime_mode: str = "celery"  # celery | engine
    engine_tick_interval_seconds: float = 1.0
    engine_supervisor_interval_seconds: float = 5.0

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_worker_concurrency: int = 1
    celery_worker_pool: str = "solo"
    celery_worker_prefetch_multiplier: int = 1
    celery_task_time_limit: int = 3600
    celery_task_soft_time_limit: int = 3500
    celery_task_acks_late: bool = True
    celery_task_reject_on_worker_lost: bool = True

    # Circuit Breaker
    circuit_breaker_orders_limit: int = 50  # Max orders per minute
    circuit_breaker_max_loss_percent: float = 5.0  # Max loss % per hour
    circuit_breaker_price_deviation: float = 10.0  # Max price deviation %
    circuit_breaker_cooldown: int = 300  # Cooldown in seconds after trip
    circuit_breaker_order_rate_window_seconds: int = 60  # Order rate window
    circuit_breaker_loss_window_seconds: int = 3600  # Loss tracking window
    circuit_breaker_half_open_orders: int = 3  # Orders allowed in HALF_OPEN

    # Logging
    log_level: str = "INFO"

    # Telegram
    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = None
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_link_token_exp_minutes: int = 30

    # Platform fees (for trades via Telegram)
    # Set to 0.0 by default (opt-in). Configure PLATFORM_FEE_PERCENT env var to enable.
    platform_fee_percent: float = 0.0

    @property
    def async_database_url(self) -> str:
        """Convert database URL to async format for asyncpg."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()  # type: ignore[call-arg]
