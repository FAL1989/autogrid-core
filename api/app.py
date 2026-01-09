"""
Application factory for the AutoGrid API.

Provides the core API without optional cloud routes.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.core.config import get_settings
from api.core.database import close_db, engine
from api.core.rate_limiter import close_redis, init_redis
from api.routes import auth, backtest, bots, credentials, orders, reports, ws

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info("Starting AutoGrid API...")

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception as exc:
        logger.error(f"Database connection failed: {exc}")
        raise

    try:
        redis = await init_redis()
        await redis.ping()
        logger.info("Redis connection successful")
    except Exception as exc:
        logger.warning(
            "Redis connection failed: %s. Rate limiting will be disabled.", exc
        )

    logger.info(
        "API running in %s mode", "debug" if settings.api_debug else "production"
    )
    yield

    logger.info("Shutting down AutoGrid API...")
    await close_redis()
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create the core API application."""
    app = FastAPI(
        title="AutoGrid API",
        description="Open Source Cryptocurrency Trading Bot API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    settings = get_settings()
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(bots.router, prefix="/api/v1/bots", tags=["Bots"])
    app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtesting"])
    app.include_router(
        credentials.router, prefix="/api/v1/credentials", tags=["Credentials"]
    )
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"])
    app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
    app.include_router(ws.router, tags=["WebSocket"])

    @app.get("/", tags=["Health"])
    async def root() -> dict[str, str]:
        return {
            "name": "AutoGrid API",
            "version": "0.1.0",
            "status": "running",
        }

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/api/v1/health", tags=["Health"])
    async def health_check_v1() -> dict[str, str]:
        return {"status": "healthy"}

    return app
