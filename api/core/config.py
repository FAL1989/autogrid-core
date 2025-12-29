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

    # Rate Limiting
    rate_limit_requests: int = 5  # requests per minute for auth endpoints
    rate_limit_window: int = 60  # window in seconds

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Circuit Breaker
    circuit_breaker_orders_limit: int = 50  # Max orders per minute
    circuit_breaker_max_loss_percent: float = 5.0  # Max loss % per hour
    circuit_breaker_price_deviation: float = 10.0  # Max price deviation %
    circuit_breaker_cooldown: int = 300  # Cooldown in seconds after trip

    # Logging
    log_level: str = "INFO"

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
    return Settings()
