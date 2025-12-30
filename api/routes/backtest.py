"""
Backtesting Routes

Run historical simulations of trading strategies.
"""

from datetime import date, datetime, time, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import User
from api.services.backtest_service import BacktestService

router = APIRouter()


class BacktestRequest(BaseModel):
    """Backtest request."""

    strategy: Literal["grid", "dca"]
    symbol: str = Field(..., pattern=r"^[A-Z]+/[A-Z]+$", examples=["BTC/USDT"])
    timeframe: str = Field(..., examples=["1h", "4h", "1d"])
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


class BacktestSummary(BaseModel):
    """Backtest summary for listings."""

    id: UUID
    strategy: str
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    status: str
    created_at: datetime
    completed_at: datetime | None
    total_return: float | None = None
    total_trades: int | None = None


class BacktestListResponse(BaseModel):
    """Backtest list with pagination."""

    backtests: list[BacktestSummary]
    total: int
    limit: int
    offset: int


@router.post("/", response_model=BacktestResult, status_code=status.HTTP_201_CREATED)
async def run_backtest(
    request: BacktestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestResult:
    """
    Run a backtest simulation.

    - Fetches historical data for the period
    - Simulates strategy execution
    - Calculates performance metrics
    - Returns results with equity curve
    """
    service = BacktestService(db)

    start_dt = datetime.combine(request.start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(request.end_date, time.max).replace(tzinfo=timezone.utc)

    try:
        backtest = await service.run_and_store(
            user_id=current_user.id,
            strategy=request.strategy,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_date=start_dt,
            end_date=end_dt,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return _build_result(backtest)


@router.get("/", response_model=BacktestListResponse)
async def list_backtests(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestListResponse:
    """List backtests for the authenticated user."""
    service = BacktestService(db)
    backtests, total = await service.list_for_user(
        user_id=current_user.id, limit=limit, offset=offset
    )

    summaries = []
    for backtest in backtests:
        results = backtest.results or {}
        summaries.append(
            BacktestSummary(
                id=backtest.id,
                strategy=backtest.strategy,
                symbol=backtest.symbol,
                timeframe=backtest.timeframe,
                start_date=backtest.start_date,
                end_date=backtest.end_date,
                status=backtest.status,
                created_at=backtest.created_at,
                completed_at=backtest.completed_at,
                total_return=results.get("total_return"),
                total_trades=results.get("total_trades"),
            )
        )

    return BacktestListResponse(
        backtests=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{backtest_id}", response_model=BacktestResult)
async def get_backtest(
    backtest_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BacktestResult:
    """
    Get backtest results by ID.
    """
    service = BacktestService(db)
    backtest = await service.get_for_user(backtest_id, current_user.id)
    if not backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backtest {backtest_id} not found",
        )
    return _build_result(backtest)


def _build_result(backtest) -> BacktestResult:
    results = backtest.results or {}
    equity_curve = [
        EquityPoint(date=point["date"], value=point["value"])
        for point in results.get("equity_curve", [])
    ]
    return BacktestResult(
        id=backtest.id,
        strategy=backtest.strategy,
        symbol=backtest.symbol,
        total_return=results.get("total_return", 0.0),
        sharpe_ratio=results.get("sharpe_ratio", 0.0),
        max_drawdown=results.get("max_drawdown", 0.0),
        win_rate=results.get("win_rate", 0.0),
        profit_factor=results.get("profit_factor", 0.0),
        total_trades=results.get("total_trades", 0),
        equity_curve=equity_curve,
    )
