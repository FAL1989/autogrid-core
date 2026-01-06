# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

AutoGrid Core is the open-source engine for the platform. It includes:

- **Core Engine (Python):** Grid and DCA strategies using CCXT
- **REST API (FastAPI):** Auth, bots, orders, backtests
- **CLI (Typer):** Command-line management via the API

Cloud-only features (dashboard, Telegram, SaaS ops) live in the private
`AutoGrid` repository.

## Project Structure

```
autogrid-core/
├── api/           # FastAPI application
├── bot/           # Bot engine + strategies
├── autogrid_cli/  # CLI application
├── db/            # Database schema + migrations
└── tests/         # Unit + integration tests
```

## Development Commands

```bash
docker compose -f docker-compose.yml up -d --build
make install
make test
make lint
```

## CLI Commands

```bash
./autogrid --help
python -m autogrid_cli --help

./autogrid auth login
./autogrid auth status
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

### Event-Driven Architecture
- Redis pub/sub for real-time events between components
- Celery for async jobs (DCA triggers, periodic tasks)

## Security Requirements (Critical)

1. **API Keys:** Encrypt before storage. Keep encryption key in env vars.
2. **Permission Validation:** Require trade-only permissions on exchange keys.
3. **Kill Switch / Circuit Breaker:**
   - Max 50 orders/minute
   - Max 5% loss/hour of investment
   - Reject orders >10% from market price
