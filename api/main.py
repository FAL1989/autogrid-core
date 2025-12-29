"""
AutoGrid API - FastAPI Application

Main entry point for the REST API.
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
from api.routes import auth, backtest, bots, credentials, orders, ws

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events for:
    - Database connection pool
    - Redis connection
    """
    settings = get_settings()

    # Startup
    logger.info("Starting AutoGrid API...")

    # Test database connection
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    # Initialize Redis
    try:
        redis = await init_redis()
        await redis.ping()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Rate limiting will be disabled.")

    logger.info(f"API running in {'debug' if settings.api_debug else 'production'} mode")

    yield

    # Shutdown
    logger.info("Shutting down AutoGrid API...")
    await close_redis()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="AutoGrid API",
    description="Open Source Cryptocurrency Trading Bot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
settings = get_settings()
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(bots.router, prefix="/bots", tags=["Bots"])
app.include_router(backtest.router, prefix="/backtest", tags=["Backtesting"])
app.include_router(credentials.router, prefix="/credentials", tags=["Credentials"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(ws.router, tags=["WebSocket"])


@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    """Root endpoint - API info."""
    return {
        "name": "AutoGrid API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}
