"""
AutoGrid API - FastAPI Application.

Main entry point for the REST API.
"""

from api.app import create_app
from api.core.config import get_settings

app = create_app()

# =============================================================================
# Cloud API Routes (optional - only loaded when cloud_api is present)
# =============================================================================

# Telegram routes
try:
    from cloud_api.routes import telegram as telegram_routes
except Exception:
    telegram_routes = None

if telegram_routes:
    app.include_router(
        telegram_routes.router, prefix="/api/v1/telegram", tags=["Telegram"]
    )

# Notifications routes
try:
    from cloud_api.routes import notifications as notifications_routes
except Exception:
    notifications_routes = None

if notifications_routes:
    app.include_router(
        notifications_routes.router, prefix="/api/v1/notifications", tags=["Notifications"]
    )

# Stripe routes
try:
    from cloud_api.routes import stripe as stripe_routes
except Exception:
    stripe_routes = None

if stripe_routes:
    app.include_router(
        stripe_routes.router, prefix="/api/v1/stripe", tags=["Stripe"]
    )

# Health routes (cloud-specific with detailed checks)
try:
    from cloud_api.routes import health as cloud_health_routes
except Exception:
    cloud_health_routes = None

if cloud_health_routes:
    app.include_router(
        cloud_health_routes.router, prefix="/api/v1/cloud", tags=["Cloud Health"]
    )

# =============================================================================
# Cloud API Middleware (optional)
# =============================================================================

try:
    from cloud_api.middleware.plan_limits import PlanLimitsMiddleware
    app.add_middleware(PlanLimitsMiddleware)
except Exception:
    pass  # Middleware not available - skip

# =============================================================================
# Startup Events
# =============================================================================

try:
    from cloud_api.services.telegram_service import set_webhook
except Exception:
    set_webhook = None

if set_webhook:

    async def _configure_telegram_webhook() -> None:
        settings = get_settings()
        if settings.telegram_bot_token and settings.telegram_webhook_url:
            await set_webhook(settings.telegram_webhook_url)

    app.add_event_handler("startup", _configure_telegram_webhook)
