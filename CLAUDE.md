# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoGrid is an open-source cryptocurrency trading bot platform. It consists of:
- **Core Engine (Python):** Grid and DCA trading strategies using CCXT
- **REST API (FastAPI):** Authentication, bot management, backtesting
- **Web Dashboard (Next.js 14 + Tailwind):** Visual interface for configuration
- **Telegram Bot:** Trade execution via chat with 0.5% fee per transaction

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11+, FastAPI, Celery |
| Frontend | Next.js 14, Tailwind CSS, TypeScript |
| Database | PostgreSQL 15 + TimescaleDB (for OHLCV data) |
| Cache/Queue | Redis |
| Exchange API | CCXT (Binance, MEXC, Bybit) |
| Telegram | python-telegram-bot v20+ |

## Project Structure

```
autogrid/
├── api/                 # FastAPI application
│   ├── routes/          # API endpoints
│   ├── models/          # Pydantic schemas
│   └── services/        # Business logic
├── bot/                 # Bot engine
│   ├── strategies/      # Grid, DCA implementations
│   ├── exchange/        # CCXT wrappers
│   └── engine.py        # Main bot loop
├── telegram/            # Telegram bot service
├── web/                 # Next.js frontend
├── db/                  # Migrations, seeds
└── tests/               # Unit + integration tests
```

## Development Commands

```bash
# Setup
docker-compose up              # Start all services
make install                   # Install Python dependencies
make test                      # Run test suite

# Python (bot/api)
black .                        # Format code
isort .                        # Sort imports
flake8                         # Lint
mypy .                         # Type check

# Frontend (web/)
npm run dev                    # Dev server
npm run build                  # Production build
npm run lint                   # ESLint

# CLI
autogrid init                  # Initialize config
autogrid credentials add       # Add exchange API keys
autogrid bot create            # Create new bot
autogrid bot start/stop        # Control bots
autogrid backtest              # Run backtest
```

## Architecture Patterns

### Bot Engine (Strategy Pattern)
```python
class BaseStrategy(ABC):
    @abstractmethod
    def calculate_orders(self, market_data) -> List[Order]

    @abstractmethod
    def on_order_filled(self, order: Order) -> None

    @abstractmethod
    def should_stop(self) -> bool
```

Implemented strategies:
- **GridStrategy:** Places buy/sell orders at fixed price intervals
- **DCAStrategy:** Buys fixed amount at regular intervals or price drops

### Event-Driven Architecture
- Redis pub/sub for real-time events between components
- Celery for async jobs (DCA triggers, report generation, periodic tasks)

## Security Requirements (Critical)

1. **API Keys:** Encrypt with AES-256-GCM before storage. Encryption key in env var, never in DB.
2. **Permission Validation:** Exchange credentials must have trade permission ENABLED and withdraw permission DISABLED. Reject credentials with withdraw access.
3. **Kill Switch / Circuit Breaker:**
   - Max 50 orders/minute
   - Max 5% loss/hour of investment
   - Reject orders >10% from market price
   - On trigger: stop bot, cancel orders, notify user

## Database Schema (Key Tables)

- `users`: id, email, password_hash, plan, telegram_chat_id
- `exchange_credentials`: user_id, exchange, api_key_encrypted, api_secret_encrypted, is_valid
- `bots`: user_id, credential_id, name, strategy (grid/dca), symbol, config (JSONB), status, realized_pnl
- `orders`: bot_id, exchange_order_id, side, type, price, quantity, status, filled_at, fee
- `ohlcv`: TimescaleDB hypertable for market data (time, exchange, symbol, timeframe, OHLCV)

## API Endpoints

- `POST /auth/register` - User registration
- `POST /bots` - Create bot with strategy config
- `GET /bots` - List user's bots
- `POST /bots/{id}/start|stop` - Control bot execution
- `POST /backtest` - Run historical simulation, returns Sharpe ratio, max drawdown, win rate

## Supported Exchanges (MVP)

| Exchange | Rate Limit | Features |
|----------|------------|----------|
| Binance | 1200 req/min | WebSocket, testnet |
| MEXC | 20 req/sec | REST only |
| Bybit | 120 req/sec | WebSocket, testnet |

## Code Standards

- **Python:** Black + isort + flake8 + mypy (strict types)
- **TypeScript:** ESLint + Prettier, strict mode
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, etc.)
- **Tests:** 80% coverage minimum for core modules
- **PRs:** Require 1 approval + passing CI
