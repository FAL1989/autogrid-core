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

## CLI

The CLI lets you manage bots and backtests via the API without touching the UI.

```bash
# From the repo root
./autogrid --help
python -m autogrid_cli --help

# Authenticate
./autogrid auth login
./autogrid auth status
```

Config is stored in `~/.config/autogrid/config.toml` (permissions 600).
You can override per run with `AUTOGRID_API_URL` and `AUTOGRID_TOKEN`.

### CLI Quickstart

1) Activate your environment and install dependencies:

```bash
# Optional: create a venv if you do not have one yet
python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
```

2) Set the API URL (one time):

```bash
./autogrid config set api-url https://autogrid.falai.agency
# or for a single run
export AUTOGRID_API_URL=https://autogrid.falai.agency
```

3) Login and verify:

```bash
./autogrid auth login
./autogrid auth status
```

4) Add exchange credentials:

```bash
./autogrid credentials add --exchange binance --testnet=false
./autogrid credentials list
```

5) Create and start a grid bot:

```bash
./autogrid bots create \
  --name "MyBot" \
  --credential-id <CREDENTIAL_ID> \
  --strategy grid \
  --symbol BTC/USDT \
  --lower-price 89000 \
  --upper-price 93000 \
  --grid-count 6 \
  --investment 50

./autogrid bots start <BOT_ID>
```

6) Monitor activity:

```bash
./autogrid bots list
./autogrid orders open <BOT_ID>
./autogrid trades list <BOT_ID>
```

### Backtest Example

```bash
cat > backtest-grid.json <<'JSON'
{
  "lower_price": 89000,
  "upper_price": 93000,
  "grid_count": 6,
  "investment": 50
}
JSON

./autogrid backtest run \
  --strategy grid \
  --symbol BTC/USDT \
  --timeframe 1h \
  --start-date 2024-01-01 \
  --end-date 2024-02-01 \
  --config-file backtest-grid.json
```

### Telegram Link

```bash
./autogrid telegram link
./autogrid telegram unlink
```

### Scriptable Output

```bash
./autogrid bots list --json
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
