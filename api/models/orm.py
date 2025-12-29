"""
SQLAlchemy ORM Models.

Database models matching the schema defined in db/init.sql.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(
        String(20),
        default="free",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    credentials: Mapped[list["ExchangeCredential"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    bots: Mapped[list["Bot"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    backtests: Mapped[list["Backtest"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ExchangeCredential(Base):
    """Exchange API credentials (encrypted)."""

    __tablename__ = "exchange_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    api_key_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    api_secret_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_testnet: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    permissions: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="credentials")
    bots: Mapped[list["Bot"]] = relationship(back_populates="credential")


class Bot(Base):
    """Trading bot configuration."""

    __tablename__ = "bots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exchange_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="stopped",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        nullable=False,
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
        nullable=False,
    )
    strategy_state: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="bots")
    credential: Mapped["ExchangeCredential | None"] = relationship(back_populates="bots")
    orders: Mapped[list["Order"]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
    )
    trades: Mapped[list["Trade"]] = relationship(
        back_populates="bot",
        cascade="all, delete-orphan",
    )


class Backtest(Base):
    """Backtest results."""

    __tablename__ = "backtests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    results: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="backtests")


class Order(Base):
    """Order model for tracking exchange orders."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange_order_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
    )
    average_fill_price: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )
    filled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(back_populates="orders")
    trades: Mapped[list["Trade"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class Trade(Base):
    """Trade execution record (TimescaleDB hypertable)."""

    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
    )
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )
    fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
    )
    fee_currency: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    realized_pnl: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        primary_key=True,
        server_default=text("NOW()"),
    )

    # Composite primary key for TimescaleDB hypertable
    __table_args__ = (
        {"timescaledb_hypertable": {"time_column": "timestamp"}},
    )

    # Relationships
    bot: Mapped["Bot"] = relationship(back_populates="trades")
    order: Mapped["Order | None"] = relationship(back_populates="trades")


class BotMetrics(Base):
    """Bot performance metrics (TimescaleDB hypertable)."""

    __tablename__ = "bot_metrics"

    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    total_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    winning_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    losing_trades: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
    )
    total_volume: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
    )
    total_fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        default=Decimal("0"),
    )
    max_drawdown: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0"),
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        primary_key=True,
        server_default=text("NOW()"),
    )

    # Composite primary key for TimescaleDB hypertable
    __table_args__ = (
        {"timescaledb_hypertable": {"time_column": "timestamp"}},
    )
