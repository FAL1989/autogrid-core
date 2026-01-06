# AutoGrid Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**Open-source trading engine + API + CLI for AutoGrid.**

This repository is the core platform (bot engine, REST API, CLI). The cloud
dashboard and Telegram integrations live in the separate private repo
`AutoGrid` (cloud).

## Features

- Grid and DCA strategies
- Multi-exchange via CCXT (Binance, MEXC, Bybit)
- Backtesting
- REST API (FastAPI)
- CLI for bots, orders, trades, and backtests

## Quick Start (Docker)

1) Create a `.env` with required keys:

```bash
ENCRYPTION_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
cat > .env <<EOF
ENCRYPTION_KEY=$ENCRYPTION_KEY
JWT_SECRET=$JWT_SECRET
EOF
```

2) Start the stack:

```bash
docker compose -f docker-compose.yml up -d --build
```

3) Access the API:

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

## CLI

```bash
./autogrid --help
python -m autogrid_cli --help
```

Config is stored (permissions 600) at:
- Linux: `~/.config/autogrid/config.toml` (or `$XDG_CONFIG_HOME/autogrid/config.toml`)
- macOS: `~/Library/Application Support/autogrid/config.toml`
- Windows: `%AppData%\\autogrid\\config.toml`

Overrides:
- `AUTOGRID_CONFIG_FILE` (config.toml path)
- `AUTOGRID_PROFILE` (config profile name)
- `AUTOGRID_API_URL` and `AUTOGRID_TOKEN`

Example `config.toml`:

```toml
[cli]
profile = "prod"

[profile.prod]
api_url = "https://autogrid.falai.agency"
```

## Project Structure

```
autogrid-core/
├── api/           # FastAPI application
├── bot/           # Bot engine + strategies
├── autogrid_cli/  # CLI application
├── db/            # Database bootstrap + migrations
└── tests/         # Unit + integration tests
```

## Development

```bash
make install
make dev
make test
make lint
make format
```

## Documentation

- `docs/DEPLOY.md` (self-hosted deploy notes)
