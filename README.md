# AutoGrid

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)

**The Open Source Trading Bot for Everyone**

AutoGrid is an open-source cryptocurrency trading bot that combines a free, self-hosted bot with optional cloud hosting and Telegram integration. Our positioning: **"The simplest grid bot that actually works"** — aimed at beginners who feel lost in complex platforms and developers seeking transparency and customization.

## Features

- **Grid Bot**: Automated buy/sell orders within configurable price ranges
- **DCA Bot**: Dollar Cost Averaging with customizable triggers
- **Multi-Exchange**: Binance, MEXC, Bybit via CCXT
- **Backtesting**: Historical simulation with Sharpe ratio, drawdown, and more
- **Web Dashboard**: Visual interface to configure strategies without code
- **Telegram Bot**: Execute trades via chat with real-time alerts
- **Open Source**: MIT licensed, fully auditable

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/autogrid/autogrid.git
cd autogrid

# Copy environment variables
cp .env.example .env

# Generate encryption keys
echo "ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env

# Start all services
make dev
```

### Access

- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Web Dashboard**: http://localhost:3000

## Project Structure

```
autogrid/
├── api/              # FastAPI REST API
├── bot/              # Trading bot engine
│   ├── strategies/   # Grid, DCA strategies
│   └── exchange/     # CCXT wrappers
├── web/              # Next.js dashboard
├── telegram/         # Telegram bot
├── db/               # Database migrations
└── tests/            # Test suite
```

## Development

```bash
# Install dependencies
make install

# Run tests
make test

# Run linters
make lint

# Format code
make format
```

## Documentation

- [Technical Design Document](./AutoGrid_TDD_v1.0.md)
- [Product Requirements](./PRD.md)
- [Sprint Backlog](./AutoGrid_Sprint_backlog.md)
- [Contributing Guide](./CONTRIBUTING.md)

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11+, FastAPI, Celery |
| Frontend | Next.js 14, Tailwind CSS |
| Database | PostgreSQL + TimescaleDB |
| Cache | Redis |
| Exchange API | CCXT |

## Security

- API keys are encrypted with AES-256-GCM
- Exchange credentials require trade-only permissions (no withdrawals)
- Built-in kill switch for automatic protection

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This software is for educational purposes only. Do not risk money you cannot afford to lose. Cryptocurrency trading carries significant risk. The developers are not responsible for any financial losses incurred while using this software.

---

Made with :heart: by the AutoGrid community
