"""
Pydantic Schemas

Shared data models for API requests and responses.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ===========================================
# Enums
# ===========================================


class UserPlan(str, Enum):
    """User subscription plans."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class BotStatus(str, Enum):
    """Bot execution status."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""

    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    """Order execution status."""

    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    ERROR = "error"


# ===========================================
# Base Schemas
# ===========================================


class TimestampMixin(BaseModel):
    """Mixin for created_at timestamp."""

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ===========================================
# User Schemas
# ===========================================


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr


class UserCreate(UserBase):
    """User creation schema."""

    password: str = Field(..., min_length=8)


class UserResponse(UserBase, TimestampMixin):
    """User response schema."""

    id: UUID
    plan: UserPlan = UserPlan.FREE
    telegram_chat_id: int | None = None

    class Config:
        from_attributes = True


# ===========================================
# Exchange Credential Schemas
# ===========================================


class ExchangeCredentialCreate(BaseModel):
    """Exchange credential creation schema."""

    exchange: Literal["binance", "mexc", "bybit"]
    api_key: str
    api_secret: str


class ExchangeCredentialResponse(BaseModel):
    """Exchange credential response (without secrets)."""

    id: UUID
    exchange: str
    is_valid: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ===========================================
# Order Schemas
# ===========================================


class OrderBase(BaseModel):
    """Base order schema."""

    side: OrderSide
    type: OrderType
    price: Decimal = Field(..., gt=0)
    quantity: Decimal = Field(..., gt=0)


class OrderCreate(OrderBase):
    """Order creation schema."""

    bot_id: UUID


class OrderResponse(OrderBase, TimestampMixin):
    """Order response schema."""

    id: UUID
    bot_id: UUID
    exchange_order_id: str | None = None
    status: OrderStatus
    filled_at: datetime | None = None
    fee: Decimal | None = None

    class Config:
        from_attributes = True


# ===========================================
# OHLCV Schemas
# ===========================================


class OHLCVData(BaseModel):
    """OHLCV candlestick data."""

    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
