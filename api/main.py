"""
AutoGrid API - FastAPI Application.

Main entry point for the REST API.
"""

from api.app import create_app
from api.core.config import get_settings

app = create_app()

try:
    from cloud_api.routes import telegram as telegram_routes
except Exception:
    telegram_routes = None

if telegram_routes:
    app.include_router(telegram_routes.router, prefix="/api/v1/telegram", tags=["Telegram"])

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
