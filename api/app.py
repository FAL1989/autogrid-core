"""
Application factory for the AutoGrid API.

Provides the core API without optional cloud routes.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.core.config import get_settings
from api.core.database import close_db, engine
from api.core.middleware import SecurityHeadersMiddleware
from api.core.rate_limiter import _redis_client, close_redis, init_redis
from api.routes import auth, backtest, bots, credentials, orders, portfolio, reports, ws

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

    # Add security headers middleware (runs first, wraps all responses)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS middleware
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
    app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["Portfolio"])
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
    async def health_check() -> JSONResponse:
        """
        Comprehensive health check endpoint.

        Validates database and Redis connectivity.
        Returns component-level status and overall health.
        """
        checks: dict[str, dict] = {}
        overall_status = "healthy"

        # Check database
        db_start = time.time()
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            db_latency_ms = round((time.time() - db_start) * 1000, 2)
            checks["database"] = {
                "status": "ok",
                "latency_ms": db_latency_ms,
            }
        except Exception as exc:
            logger.error(f"Database health check failed: {exc}")
            checks["database"] = {
                "status": "error",
                "error": str(exc),
            }
            overall_status = "degraded"

        # Check Redis
        redis_start = time.time()
        try:
            if _redis_client is not None:
                await _redis_client.ping()
                redis_latency_ms = round((time.time() - redis_start) * 1000, 2)
                # Get memory info if available
                try:
                    info = await _redis_client.info("memory")
                    used_memory = info.get("used_memory_human", "unknown")
                except Exception:
                    used_memory = "unknown"
                checks["redis"] = {
                    "status": "ok",
                    "latency_ms": redis_latency_ms,
                    "used_memory": used_memory,
                }
            else:
                checks["redis"] = {
                    "status": "not_initialized",
                }
                # Redis not being initialized is a warning, not critical
                if overall_status == "healthy":
                    overall_status = "healthy"  # Redis is optional for basic health
        except Exception as exc:
            logger.warning(f"Redis health check failed: {exc}")
            checks["redis"] = {
                "status": "error",
                "error": str(exc),
            }
            # Redis failure degrades status but doesn't make it unhealthy
            if overall_status == "healthy":
                overall_status = "degraded"

        status_code = (
            status.HTTP_200_OK
            if overall_status == "healthy"
            else (
                status.HTTP_503_SERVICE_UNAVAILABLE
                if checks.get("database", {}).get("status") == "error"
                else status.HTTP_200_OK
            )
        )

        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall_status,
                "checks": checks,
            },
        )

    @app.get("/ready", tags=["Health"])
    async def readiness_check() -> JSONResponse:
        """
        Kubernetes readiness probe endpoint.

        Returns 200 if the service is ready to accept traffic.
        Checks database connectivity only (critical dependency).
        """
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"ready": True},
            )
        except Exception as exc:
            logger.error(f"Readiness check failed: {exc}")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"ready": False, "error": str(exc)},
            )

    @app.get("/live", tags=["Health"])
    async def liveness_check() -> dict[str, bool]:
        """
        Kubernetes liveness probe endpoint.

        Returns 200 if the process is alive.
        Minimal check - just confirms the API is responding.
        """
        return {"alive": True}

    @app.get("/api/v1/health", tags=["Health"])
    async def health_check_v1() -> JSONResponse:
        """Versioned health check - same as /health."""
        return await health_check()

    return app
