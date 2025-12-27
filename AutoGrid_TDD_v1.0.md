
# AutoGrid

## Technical Design Document (TDD)

**Architecture • Database • APIs • Infrastructure**

---

- **Version:** 1.0  
- **Date:** December 27, 2025  
- **Author:** Fernando | F.A.L AI Agency  
- **Status:** Draft

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Component Design](#3-component-design)
4. [Database Schema](#4-database-schema)
5. [API Specification](#5-api-specification)
6. [External Integrations](#6-external-integrations)
7. [Security Architecture](#7-security-architecture)
8. [Infrastructure & Deployment](#8-infrastructure--deployment)
9. [Monitoring & Observability](#9-monitoring--observability)
10. [Development Guidelines](#10-development-guidelines)

---

## 1. System Overview

### 1.1 Purpose

AutoGrid is a modular, open-source cryptocurrency trading bot platform. This document describes the technical architecture, database design, API contracts, and infrastructure required to build and deploy the system. 

**Design priorities:**  
- Modularity (swap components easily)
- Security (API keys encrypted, no withdrawal permissions)
- Scalability (horizontal scaling for cloud)
- Developer experience (clear APIs, comprehensive docs)

### 1.2 System Context

The system operates in three deployment modes:
- **Self-Hosted:** User runs on their own infrastructure
- **Cloud Managed:** We host and manage
- **Telegram Bot:** Trades via chat interface

All modes share the same core engine but differ in deployment and monetization.

### 1.3 Key Design Decisions

| Decision                      | Rationale                                                                 |
| ----------------------------- | ------------------------------------------------------------------------- |
| Python for core engine        | Best ecosystem for trading (CCXT, pandas, numpy). Async support via asyncio. |
| PostgreSQL + TimescaleDB      | Time-series optimized for OHLCV data. Hypertables for automatic partitioning. |
| CCXT for exchange connectivity| 100+ exchanges, unified API, actively maintained. Reduces integration effort. |
| Event-driven architecture     | Decouples components. Redis pub/sub for real-time events. Celery for async jobs. |
| Docker-first deployment       | Consistent environments. Easy scaling. Works for self-hosted and cloud.    |

---

## 2. High-Level Architecture

### 2.1 Architecture Diagram (Text Representation)

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Web App  │  │   CLI    │  │ Telegram │  │   API    │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
└───────┼──────────────┼──────────────┼──────────────┼────────────┘
        │              │              │              │             
        └──────────────┴──────────────┴──────────────┘             
                               │                                   
                    ┌─────────▼─────────┐                          
                    │   API GATEWAY     │                          
                    │   (FastAPI)       │                          
                    └─────────┬─────────┘                          
                              │                                    
        ┌─────────────────────┼─────────────────────┐              
        │                     │                     │              
┌───────▼───────┐  ┌──────────▼──────────┐  ┌───────▼───────┐      
│  BOT ENGINE   │  │  DATA COLLECTOR     │  │  SCHEDULER    │      
│  (Strategies) │  │  (Market Data)      │  │  (Celery)     │      
└───────┬───────┘  └──────────┬──────────┘  └───────┬───────┘      
        │                     │                     │              
        └─────────────────────┼─────────────────────┘              
                              │                                    
              ┌───────────────┴───────────────┐                    
              │                               │                    
       ┌──────▼──────┐                 ┌──────▼──────┐             
       │  PostgreSQL │                 │    Redis    │             
       │ +TimescaleDB│                 │ Cache/Queue │             
       └─────────────┘                 └─────────────┘             
```

### 2.2 Component Summary

| Component         | Technology               | Responsibility                                      |
|-------------------|-------------------------|-----------------------------------------------------|
| API Gateway       | FastAPI                 | REST API, WebSocket, authentication, rate limiting  |
| Bot Engine        | Python + CCXT           | Strategy execution, order management, position tracking |
| Data Collector    | Python + WebSocket      | Real-time market data ingestion, OHLCV storage      |
| Scheduler         | Celery + Redis          | Periodic tasks, DCA triggers, report generation     |
| Telegram Service  | python-telegram-bot     | Chat interface, command handling, notifications     |
| Web Frontend      | Next.js + Tailwind      | Dashboard, bot configuration, analytics             |

---

## 3. Component Design

### 3.1 Bot Engine

The Bot Engine is the core trading component. It implements the **Strategy Pattern** to support multiple trading strategies (Grid, DCA, etc.).

#### 3.1.1 Class Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    BotEngine                            │
├─────────────────────────────────────────────────────────┤
│ - strategy: BaseStrategy                                │
│ - exchange: ExchangeConnector                           │
│ - position_manager: PositionManager                     │
│ - risk_manager: RiskManager                             │
├─────────────────────────────────────────────────────────┤
│ + start()                                               │
│ + stop()                                                │
│ + on_tick(price: float)                                 │
│ + execute_order(order: Order)                           │
└─────────────────────────────────────────────────────────┘
```

#### 3.1.2 Strategy Interface

```python
class BaseStrategy(ABC):
    @abstractmethod
    def calculate_orders(self, market_data) -> List[Order]
    
    @abstractmethod
    def on_order_filled(self, order: Order) -> None
    
    @abstractmethod
    def should_stop(self) -> bool
```

#### 3.1.3 Implemented Strategies

| Strategy      | Logic                                                                 |
| ------------- | --------------------------------------------------------------------- |
| GridStrategy  | Places buy/sell orders at fixed price intervals within a range. Profits from volatility. |
| DCAStrategy   | Buys fixed amount at regular intervals or price drops. Reduces average entry price over time. |

### 3.2 Exchange Connector

Wraps CCXT to provide a unified interface for all exchanges. Handles authentication, rate limiting, and error recovery.

#### 3.2.1 Supported Exchanges (MVP)

- **Binance:** Spot + Futures, WebSocket for real-time data
- **MEXC:** Spot only, REST polling (WebSocket limited)
- **Bybit:** Spot + Derivatives, WebSocket supported

#### 3.2.2 Connection Flow

1. User provides API key + secret (encrypted at rest)
2. System validates permissions (must have trade, must NOT have withdraw)
3. Connector establishes WebSocket for price feeds
4. Orders executed via REST API with retry logic

---

## 4. Database Schema

### 4.1 Entity Relationship Overview

PostgreSQL with TimescaleDB extension for time-series data. All timestamps in UTC.

### 4.2 Core Tables

#### 4.2.1 `users`

| Column           | Type         | Description                             |
|------------------|--------------|-----------------------------------------|
| id               | UUID, PK     | Primary key                             |
| email            | VARCHAR(255) | Unique, indexed                         |
| password_hash    | VARCHAR(255) | bcrypt hashed                           |
| plan             | ENUM         | free, starter, pro, enterprise          |
| telegram_chat_id | BIGINT       | Nullable, for Telegram notifications    |
| created_at       | TIMESTAMPTZ  | Default NOW()                           |

#### 4.2.2 `exchange_credentials`

| Column             | Type         | Description                                       |
|--------------------|--------------|---------------------------------------------------|
| id                 | UUID, PK     | Primary key                                       |
| user_id            | UUID, FK     | References `users.id`                             |
| exchange           | VARCHAR(50)  | binance, mexc, bybit, etc.                        |
| api_key_encrypted  | BYTEA        | AES-256 encrypted                                 |
| api_secret_encrypted| BYTEA       | AES-256 encrypted                                 |
| is_valid           | BOOLEAN      | Validated on creation and periodically            |

#### 4.2.3 `bots`

| Column            | Type            | Description                          |
|-------------------|-----------------|--------------------------------------|
| id                | UUID, PK        | Primary key                          |
| user_id           | UUID, FK        | References `users.id`                |
| credential_id     | UUID, FK        | References `exchange_credentials.id` |
| name              | VARCHAR(100)    | User-defined name                    |
| strategy          | ENUM            | grid, dca                            |
| symbol            | VARCHAR(20)     | e.g., BTC/USDT                       |
| config            | JSONB           | Strategy-specific parameters         |
| status            | ENUM            | running, paused, stopped, error      |
| total_investment  | DECIMAL(18,8)   | Initial investment amount            |
| realized_pnl      | DECIMAL(18,8)   | Cumulative realized profit/loss      |

#### 4.2.4 `orders`

| Column             | Type           | Description                              |
|--------------------|----------------|------------------------------------------|
| id                 | UUID, PK       | Primary key                              |
| bot_id             | UUID, FK       | References `bots.id`                     |
| exchange_order_id  | VARCHAR(100)   | ID from exchange                         |
| side               | ENUM           | buy, sell                                |
| type               | ENUM           | limit, market                            |
| price              | DECIMAL(18,8)  | Order price                              |
| quantity           | DECIMAL(18,8)  | Order quantity                           |
| status             | ENUM           | pending, open, filled, cancelled, error  |
| filled_at          | TIMESTAMPTZ    | When order was filled                    |
| fee                | DECIMAL(18,8)  | Trading fee paid                         |

#### 4.2.5 `ohlcv` (TimescaleDB Hypertable)

| Column             | Type           | Description                    |
|--------------------|----------------|--------------------------------|
| time               | TIMESTAMPTZ    | Candle timestamp (partition key)|
| exchange           | VARCHAR(50)    | Exchange name                  |
| symbol             | VARCHAR(20)    | Trading pair                   |
| timeframe          | VARCHAR(10)    | 1m, 5m, 15m, 1h, 4h, 1d        |
| open, high, low, close | DECIMAL(18,8)| Price data                   |
| volume             | DECIMAL(24,8)  | Trading volume                 |

---

## 5. API Specification

### 5.1 Authentication

- JWT-based authentication
- Tokens expire in 24 hours
- Refresh tokens valid for 7 days

#### 5.1.1 `POST /auth/register`

**Request:**
```json
{ "email": "user@example.com", "password": "securepass123" }
```

**Response:**
```json
{ "user_id": "uuid", "access_token": "jwt", "refresh_token": "jwt" }
```

### 5.2 Bot Endpoints

#### 5.2.1 `POST /bots`

Create a new bot. Requires valid exchange credentials.

**Request:**
```json
{
  "name": "My Grid Bot",
  "credential_id": "uuid",
  "strategy": "grid",
  "symbol": "BTC/USDT",
  "config": {
    "lower_price": 40000,
    "upper_price": 48000,
    "grid_count": 20,
    "investment": 1000
  }
}
```

#### 5.2.2 `GET /bots`

List all bots for the authenticated user.

**Response:**
```json
{ "bots": [{ "id": "uuid", "name": "...", "status": "running", ... }] }
```

#### 5.2.3 `POST /bots/{id}/start`

Start a stopped/paused bot.

#### 5.2.4 `POST /bots/{id}/stop`

Stop a running bot. Cancels all open orders.

### 5.3 Backtest Endpoints

#### 5.3.1 `POST /backtest`

**Request:**
```json
{
  "strategy": "grid",
  "symbol": "BTC/USDT",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "config": { ... }
}
```

**Response:**
```json
{
  "total_return": 0.24,
  "sharpe_ratio": 1.82,
  "max_drawdown": -0.084,
  "win_rate": 0.685,
  "total_trades": 342,
  "equity_curve": [...]
}
```

---

## 6. External Integrations

### 6.1 Exchange APIs (via CCXT)

| Exchange | Rate Limit        | Notes                                         |
|----------|-------------------|-----------------------------------------------|
| Binance  | 1200 req/min      | WebSocket for real-time. Testnet available.   |
| MEXC     | 20 req/sec        | REST only for orders. Limited WebSocket.      |
| Bybit    | 120 req/sec       | Full WebSocket support. Testnet available.    |

### 6.2 Telegram Bot API

- Library: `python-telegram-bot` v20+
- Webhook: HTTPS endpoint for receiving updates
- Rate Limit: 30 messages/second globally

### 6.3 Payment Processing

- Stripe: Credit card payments, subscription management
- Crypto Payments: Optional, via Coinbase Commerce or NOWPayments

---

## 7. Security Architecture

### 7.1 API Key Encryption

1. User provides API key + secret
2. System encrypts with AES-256-GCM
3. Encryption key stored in environment variable (not in DB)
4. Decryption only happens in memory, never logged

### 7.2 Permission Validation

When user adds exchange credentials, we verify:
- Trade permission is enabled
- Withdraw permission is **DISABLED**
- IP whitelist is configured (recommended)

If withdraw permission is detected, we reject the credentials.

### 7.3 Kill Switch / Circuit Breaker

Automatic protection against runaway bots:

- Max orders per minute: 50 (configurable)
- Max loss per hour: 5% of investment (configurable)
- Price sanity check: Reject orders >10% from market price
- On trigger: Stop bot, cancel orders, notify user via Telegram/email

---

## 8. Infrastructure & Deployment

### 8.1 Docker Compose (Development)

```yaml
services:
  api:
    build: ./api
    ports: ['8000:8000']
  bot-engine:
    build: ./bot-engine
  celery:
    build: ./celery
  postgres:
    image: timescale/timescaledb:latest-pg15
  redis:
    image: redis:7-alpine
```

### 8.2 Production Architecture (Cloud)

| Service           | Provider                     | Spec / Notes                                 |
|-------------------|-----------------------------|----------------------------------------------|
| API + Bot Engine  | DigitalOcean App Platform    | 2 vCPU, 4GB RAM, auto-scaling                |
| Database          | DigitalOcean Managed DB      | PostgreSQL 15, 2GB RAM, daily backups        |
| Redis             | DigitalOcean Managed Redis   | 1GB, for cache + Celery broker               |
| CDN               | Cloudflare                   | DDoS protection, SSL, caching                |

### 8.3 Estimated Monthly Cost

- **MVP (self-hosted):** $0 (user's infra)
- **Cloud (0-50 users):** ~$50/month
- **Cloud (50-200 users):** ~$150/month
- **Cloud (200+ users):** ~$300-500/month

---

## 9. Monitoring & Observability

### 9.1 Metrics

- Prometheus + Grafana: API latency, bot count, orders/minute
- Business Metrics: Active users, MRR, trades executed

### 9.2 Logging

- Structured JSON logs: Easy parsing and filtering
- Log levels: DEBUG (dev), INFO (prod), ERROR (alerts)
- Sensitive data: NEVER log API keys, passwords, or full order details

### 9.3 Alerting

- PagerDuty/Opsgenie: Critical alerts (bot failures, DB down)
- Slack: Warning alerts (high error rate, slow API)
- Email digest: Daily summary of key metrics

---

## 10. Development Guidelines

### 10.1 Repository Structure

```
autogrid/
├── api/                 # FastAPI application
│   ├── routes/          # API endpoints
│   ├── models/          # Pydantic schemas
│   └── services/        # Business logic
├── bot/                 # Bot engine
│   ├── strategies/      # Grid, DCA, etc.
│   ├── exchange/        # CCXT wrappers
│   └── engine.py        # Main bot loop
├── telegram/            # Telegram bot
├── web/                 # Next.js frontend
├── db/                  # Migrations, seeds
├── tests/               # Unit + integration
├── docker-compose.yml
└── README.md
```

### 10.2 Code Standards

- Python: Black formatter, isort, flake8, mypy for type checking
- JavaScript: ESLint + Prettier, TypeScript preferred
- Commits: Conventional Commits (feat:, fix:, docs:, etc.)
- PRs: Require 1 approval, passing CI, no merge conflicts

### 10.3 Testing Requirements

- Unit tests: 80% coverage minimum for core modules
- Integration tests: API endpoints, database operations
- E2E tests: Critical flows (create bot, execute trade)

### 10.4 CI/CD Pipeline

1. Lint: Run formatters and linters
2. Test: Run unit and integration tests
3. Build: Build Docker images
4. Deploy (staging): Auto-deploy on merge to develop
5. Deploy (prod): Manual trigger on merge to main

---

**— END OF DOCUMENT —**

_AutoGrid TDD v1.0 | December 2025_

