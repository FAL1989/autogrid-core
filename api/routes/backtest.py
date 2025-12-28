"""
Backtesting Routes

Run historical simulations of trading strategies.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.core.dependencies import get_current_user
from api.models.orm import User

router = APIRouter()


class BacktestRequest(BaseModel):
    """Backtest request."""

    strategy: Literal["grid", "dca"]
    symbol: str = Field(..., pattern=r"^[A-Z]+/[A-Z]+$", examples=["BTC/USDT"])
    start_date: date
    end_date: date
    config: dict


class EquityPoint(BaseModel):
    """Single point in equity curve."""

    date: str
    value: float


class BacktestResult(BaseModel):
    """Backtest result with performance metrics."""

    id: UUID
    strategy: str
    symbol: str
    total_return: float = Field(..., description="Total return as decimal (0.24 = 24%)")
    sharpe_ratio: float = Field(..., description="Risk-adjusted return")
    max_drawdown: float = Field(..., description="Maximum drawdown as decimal")
    win_rate: float = Field(..., description="Winning trades ratio")
    profit_factor: float = Field(..., description="Gross profit / Gross loss")
    total_trades: int
    equity_curve: list[EquityPoint]


@router.post("/", response_model=BacktestResult, status_code=status.HTTP_201_CREATED)
async def run_backtest(
    request: BacktestRequest,
    current_user: User = Depends(get_current_user),
) -> BacktestResult:
    """
    Run a backtest simulation.

    - Fetches historical data for the period
    - Simulates strategy execution
    - Calculates performance metrics
    - Returns results with equity curve
    """
    # TODO: Implement backtesting (associate with current_user)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Backtesting not yet implemented",
    )


@router.get("/{backtest_id}", response_model=BacktestResult)
async def get_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
) -> BacktestResult:
    """
    Get backtest results by ID.
    """
    # TODO: Implement get backtest (ensure belongs to current_user)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Backtest {backtest_id} not found",
    )
