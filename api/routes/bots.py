"""
Bot Management Routes

CRUD operations for trading bots.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import User
from api.services.bot_event_service import record_bot_event
from api.services.bot_service import BotService

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class GridConfig(BaseModel):
    """Grid bot configuration."""

    lower_price: float = Field(..., gt=0, description="Lower price boundary")
    upper_price: float = Field(..., gt=0, description="Upper price boundary")
    grid_count: int = Field(..., ge=5, le=100, description="Number of grid lines")
    investment: float = Field(..., gt=0, description="Total investment amount")

    @model_validator(mode="after")
    def validate_price_range(self) -> "GridConfig":
        """Ensure lower_price is less than upper_price."""
        if self.lower_price >= self.upper_price:
            raise ValueError("lower_price must be less than upper_price")
        return self


class DCAConfig(BaseModel):
    """DCA bot configuration."""

    amount: float = Field(..., gt=0, description="Amount per buy")
    interval: Literal["hourly", "daily", "weekly"] = Field(
        ..., description="Buy interval"
    )
    trigger_drop: float | None = Field(
        None, ge=0, le=100, description="Price drop % to trigger extra buy"
    )
    take_profit: float | None = Field(
        None, ge=0, le=1000, description="Take profit %"
    )
    investment: float | None = Field(
        None, gt=0, description="Total investment amount"
    )


class BotCreate(BaseModel):
    """Bot creation request."""

    name: str = Field(..., min_length=1, max_length=100)
    credential_id: UUID
    strategy: Literal["grid", "dca"]
    symbol: str = Field(..., pattern=r"^[A-Z]+/[A-Z]+$", examples=["BTC/USDT"])
    config: GridConfig | DCAConfig


class BotUpdate(BaseModel):
    """Bot update request."""

    name: str | None = Field(None, min_length=1, max_length=100)
    config: dict | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "BotUpdate":
        """Ensure at least one field is provided."""
        if self.name is None and self.config is None:
            raise ValueError("At least one field (name or config) must be provided")
        return self


class BotResponse(BaseModel):
    """Bot response."""

    id: UUID
    credential_id: UUID | None
    name: str
    strategy: str
    exchange: str
    symbol: str
    status: str
    realized_pnl: float
    unrealized_pnl: float
    config: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class BotListResponse(BaseModel):
    """Bot list response with pagination."""

    bots: list[BotResponse]
    total: int
    limit: int
    offset: int


class BotActionResponse(BaseModel):
    """Response for bot start/stop actions."""

    bot_id: UUID
    status: str
    message: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
async def create_bot(
    bot: BotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """
    Create a new trading bot.

    - Validates exchange credentials belong to user
    - Validates strategy configuration
    - Creates bot in database
    """
    bot_service = BotService(db)

    # Validate credential ownership
    credential = await bot_service.get_credential_for_user(
        bot.credential_id, current_user.id
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exchange credential not found",
        )

    # Validate config matches strategy type
    if bot.strategy == "grid" and not isinstance(bot.config, GridConfig):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Grid strategy requires GridConfig",
        )
    if bot.strategy == "dca" and not isinstance(bot.config, DCAConfig):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DCA strategy requires DCAConfig",
        )

    # Create bot
    new_bot = await bot_service.create(
        user_id=current_user.id,
        credential_id=credential.id,
        name=bot.name,
        strategy=bot.strategy,
        exchange=credential.exchange,
        symbol=bot.symbol,
        config=bot.config.model_dump(),
    )

    return BotResponse(
        id=new_bot.id,
        credential_id=new_bot.credential_id,
        name=new_bot.name,
        strategy=new_bot.strategy,
        exchange=new_bot.exchange,
        symbol=new_bot.symbol,
        status=new_bot.status,
        realized_pnl=float(new_bot.realized_pnl),
        unrealized_pnl=float(new_bot.unrealized_pnl),
        config=new_bot.config,
        created_at=new_bot.created_at,
        updated_at=new_bot.updated_at,
    )


@router.get("/", response_model=BotListResponse)
async def list_bots(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotListResponse:
    """
    List all bots for the authenticated user.
    """
    bot_service = BotService(db)

    bots, total = await bot_service.list_by_user(
        current_user.id, limit=limit, offset=offset
    )

    bot_responses = [
        BotResponse(
            id=bot.id,
            credential_id=bot.credential_id,
            name=bot.name,
            strategy=bot.strategy,
            exchange=bot.exchange,
            symbol=bot.symbol,
            status=bot.status,
            realized_pnl=float(bot.realized_pnl),
            unrealized_pnl=float(bot.unrealized_pnl),
            config=bot.config,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
        )
        for bot in bots
    ]

    return BotListResponse(
        bots=bot_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """
    Get bot details by ID.
    """
    bot_service = BotService(db)

    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    return BotResponse(
        id=bot.id,
        credential_id=bot.credential_id,
        name=bot.name,
        strategy=bot.strategy,
        exchange=bot.exchange,
        symbol=bot.symbol,
        status=bot.status,
        realized_pnl=float(bot.realized_pnl),
        unrealized_pnl=float(bot.unrealized_pnl),
        config=bot.config,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
    )


@router.patch("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: UUID,
    update: BotUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotResponse:
    """
    Update bot name and/or configuration.
    """
    bot_service = BotService(db)

    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    if bot.status in {"running", "starting", "stopping"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stop the bot before editing",
        )

    config_payload = None
    if update.config is not None:
        if bot.strategy == "grid":
            config_payload = GridConfig.model_validate(update.config).model_dump()
        elif bot.strategy == "dca":
            config_payload = DCAConfig.model_validate(update.config).model_dump()
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported strategy {bot.strategy}",
            )

    updated = await bot_service.update_bot(
        bot_id=bot_id,
        user_id=current_user.id,
        name=update.name,
        config=config_payload,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    await db.commit()

    return BotResponse(
        id=updated.id,
        credential_id=updated.credential_id,
        name=updated.name,
        strategy=updated.strategy,
        exchange=updated.exchange,
        symbol=updated.symbol,
        status=updated.status,
        realized_pnl=float(updated.realized_pnl),
        unrealized_pnl=float(updated.unrealized_pnl),
        config=updated.config,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.post("/{bot_id}/start", response_model=BotActionResponse)
async def start_bot(
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotActionResponse:
    """
    Start a stopped/paused bot.

    Dispatches a Celery task to start the bot engine asynchronously.
    """
    from bot.tasks import start_trading_bot

    bot_service = BotService(db)

    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    if bot.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bot is already running",
        )

    if bot.status == "starting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bot is already starting",
        )

    if bot.status == "error":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bot is in error state: {bot.error_message}",
        )

    # Update status to starting
    await bot_service.update_status(bot_id, "starting")
    await db.commit()

    # Dispatch Celery task to start the bot
    task = start_trading_bot.delay(str(bot_id))

    return BotActionResponse(
        bot_id=bot_id,
        status="starting",
        message=f"Bot start initiated (task_id: {task.id})",
    )


@router.post("/{bot_id}/stop", response_model=BotActionResponse)
async def stop_bot(
    bot_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotActionResponse:
    """
    Stop a running bot and cancel all open orders.

    Dispatches a Celery task to gracefully stop the bot.
    """
    from bot.tasks import stop_trading_bot

    bot_service = BotService(db)

    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    if bot.status == "stopped":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bot is already stopped",
        )

    if bot.status == "stopping":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bot is already stopping",
        )

    # Update status to stopping
    await bot_service.update_status(bot_id, "stopping")
    metadata = {
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
    await record_bot_event(
        db=db,
        bot_id=bot.id,
        user_id=current_user.id,
        event_type="stop_requested",
        source="api",
        reason="user_request",
        metadata=metadata,
    )
    await db.commit()

    # Dispatch Celery task to stop the bot
    task = stop_trading_bot.delay(
        str(bot_id),
        source="api",
        reason="user_request",
    )

    return BotActionResponse(
        bot_id=bot_id,
        status="stopping",
        message=f"Bot stop initiated (task_id: {task.id})",
    )


@router.delete("/{bot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bot(
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a bot.

    Bot must be stopped before deletion.
    """
    bot_service = BotService(db)

    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    if bot.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a running bot. Stop it first.",
        )

    await bot_service.delete(bot_id, current_user.id)
