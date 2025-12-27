"""
AutoGrid API - FastAPI Application

Main entry point for the REST API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import auth, backtest, bots

app = FastAPI(
    title="AutoGrid API",
    description="Open Source Cryptocurrency Trading Bot API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(bots.router, prefix="/bots", tags=["Bots"])
app.include_router(backtest.router, prefix="/backtest", tags=["Backtesting"])


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
