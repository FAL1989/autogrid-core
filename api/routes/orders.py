"""
Order Management Routes

Endpoints for viewing and managing bot orders and trades.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.dependencies import get_current_user
from api.models.orm import User
from api.services.bot_service import BotService
from api.services.order_service import OrderService

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class OrderResponse(BaseModel):
    """Order response."""

    id: UUID
    bot_id: UUID
    exchange_order_id: str | None
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["limit", "market"]
    price: float | None
    quantity: float
    filled_quantity: float
    average_fill_price: float | None
    status: str
    created_at: datetime
    updated_at: datetime
    filled_at: datetime | None

    class Config:
        """Pydantic config."""

        from_attributes = True


class OrderListResponse(BaseModel):
    """Order list response with pagination."""

    orders: list[OrderResponse]
    total: int
    limit: int
    offset: int


class TradeResponse(BaseModel):
    """Trade response."""

    id: UUID
    bot_id: UUID
    order_id: UUID | None
    symbol: str
    side: Literal["buy", "sell"]
    price: float
    quantity: float
    fee: float
    fee_currency: str | None
    realized_pnl: float | None
    timestamp: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class TradeListResponse(BaseModel):
    """Trade list response with pagination."""

    trades: list[TradeResponse]
    total: int
    limit: int
    offset: int


class BotStatisticsResponse(BaseModel):
    """Bot order/trade statistics response."""

    orders: dict
    trades: dict


class CancelOrderResponse(BaseModel):
    """Cancel order response."""

    order_id: UUID
    status: str
    message: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/bots/{bot_id}/orders", response_model=OrderListResponse)
async def list_orders(
    bot_id: UUID,
    order_status: str | None = Query(default=None, description="Filter by status", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrderListResponse:
    """
    List all orders for a bot.

    Supports filtering by status and pagination.
    """
    bot_service = BotService(db)
    order_service = OrderService(db)

    # Verify bot ownership
    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    orders, total = await order_service.list_by_bot(
        bot_id, status=order_status, limit=limit, offset=offset
    )

    order_responses = [
        OrderResponse(
            id=order.id,
            bot_id=order.bot_id,
            exchange_order_id=order.exchange_order_id,
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            price=float(order.price) if order.price else None,
            quantity=float(order.quantity),
            filled_quantity=float(order.filled_quantity),
            average_fill_price=float(order.average_fill_price) if order.average_fill_price else None,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
            filled_at=order.filled_at,
        )
        for order in orders
    ]

    return OrderListResponse(
        orders=order_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/bots/{bot_id}/orders/open", response_model=list[OrderResponse])
async def get_open_orders(
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OrderResponse]:
    """
    Get all open orders for a bot.
    """
    bot_service = BotService(db)
    order_service = OrderService(db)

    # Verify bot ownership
    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    orders = await order_service.get_open_orders(bot_id)

    return [
        OrderResponse(
            id=order.id,
            bot_id=order.bot_id,
            exchange_order_id=order.exchange_order_id,
            symbol=order.symbol,
            side=order.side,
            type=order.type,
            price=float(order.price) if order.price else None,
            quantity=float(order.quantity),
            filled_quantity=float(order.filled_quantity),
            average_fill_price=float(order.average_fill_price) if order.average_fill_price else None,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
            filled_at=order.filled_at,
        )
        for order in orders
    ]


@router.post(
    "/bots/{bot_id}/orders/{order_id}/cancel",
    response_model=CancelOrderResponse,
)
async def cancel_order(
    bot_id: UUID,
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CancelOrderResponse:
    """
    Cancel an open order.

    Note: This only updates the order status in the database.
    The actual exchange order cancellation is handled by the bot engine.
    """
    bot_service = BotService(db)
    order_service = OrderService(db)

    # Verify bot ownership
    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    # Verify order belongs to bot
    order = await order_service.get_by_id(order_id)
    if order is None or order.bot_id != bot_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Cancel order
    cancelled = await order_service.cancel_order(order_id, current_user.id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel order in status: {order.status}",
        )

    return CancelOrderResponse(
        order_id=order_id,
        status="cancelled",
        message="Order cancellation requested",
    )


@router.get("/bots/{bot_id}/trades", response_model=TradeListResponse)
async def list_trades(
    bot_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TradeListResponse:
    """
    List all trades for a bot.
    """
    bot_service = BotService(db)
    order_service = OrderService(db)

    # Verify bot ownership
    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    trades, total = await order_service.list_trades_by_bot(
        bot_id, limit=limit, offset=offset
    )

    trade_responses = [
        TradeResponse(
            id=trade.id,
            bot_id=trade.bot_id,
            order_id=trade.order_id,
            symbol=trade.symbol,
            side=trade.side,
            price=float(trade.price),
            quantity=float(trade.quantity),
            fee=float(trade.fee),
            fee_currency=trade.fee_currency,
            realized_pnl=float(trade.realized_pnl) if trade.realized_pnl else None,
            timestamp=trade.timestamp,
        )
        for trade in trades
    ]

    return TradeListResponse(
        trades=trade_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/bots/{bot_id}/statistics", response_model=BotStatisticsResponse)
async def get_statistics(
    bot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BotStatisticsResponse:
    """
    Get order and trade statistics for a bot.
    """
    bot_service = BotService(db)
    order_service = OrderService(db)

    # Verify bot ownership
    bot = await bot_service.get_by_id_for_user(bot_id, current_user.id)
    if bot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bot not found",
        )

    stats = await order_service.get_bot_statistics(bot_id)
    return BotStatisticsResponse(**stats)
