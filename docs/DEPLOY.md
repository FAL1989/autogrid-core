# AutoGrid Deploy Checklist (Production)

This document covers the pre-deploy preparation items and the deploy process for AutoGrid.

## 1) GitHub Secrets and Variables

Set these in GitHub: Settings -> Secrets and variables -> Actions.

Use **Secrets** for sensitive values and **Variables** for non-sensitive config.

Recommended secrets:
- ENCRYPTION_KEY (Fernet key)
- JWT_SECRET
- POSTGRES_PASSWORD
- BINANCE_API_KEY
- BINANCE_API_SECRET
- MEXC_API_KEY
- MEXC_API_SECRET
- BYBIT_API_KEY
- BYBIT_API_SECRET
- TELEGRAM_BOT_TOKEN
- TELEGRAM_WEBHOOK_SECRET

Recommended variables:
- API_URL (ex: https://autogrid.falai.agency)
- NEXT_PUBLIC_API_URL (same as API_URL)
- CORS_ORIGINS (ex: https://autogrid.falai.agency)
- BINANCE_TESTNET (true/false)
- BYBIT_TESTNET (true/false)
- LOG_LEVEL (INFO)
- CIRCUIT_BREAKER_ORDERS_LIMIT
- CIRCUIT_BREAKER_MAX_LOSS_PERCENT
- CIRCUIT_BREAKER_PRICE_DEVIATION
- CIRCUIT_BREAKER_COOLDOWN

Optional (if private repo + Codecov):
- CODECOV_TOKEN

## 2) Monitoring (Prometheus/Grafana)

Minimum recommended checks:
- HTTP uptime for:
  - https://autogrid.falai.agency (web)
  - https://autogrid.falai.agency/health (api)
- Container health (docker ps status)
- CPU, memory, disk, and network on the VPS
- Postgres and Redis health

Suggested components (if not already deployed):
- node_exporter (host metrics)
- cAdvisor (container metrics)
- postgres_exporter
- redis_exporter
- blackbox_exporter (HTTP probes)

## 3) Alerts

Create alerts for:
- Web/API down (HTTP != 200 for 2-5 minutes)
- API error rate spike (5xx)
- Redis down
- Postgres down
- Disk usage > 85%
- Memory usage > 90%
- Container restart loops (autogrid-api, autogrid-web, autogrid-celery)
- Bot in error state (optional, via DB or logs)

## 4) Deploy Process (VPS)

Production stack on VPS uses:
- docker-compose.vps.yml
- .env on the server (do not commit)

Steps:
1) SSH to VPS.
2) Update code:
   - git pull
3) Update .env values if needed.
4) Rebuild and restart:
   - docker compose -f docker-compose.vps.yml up -d --build
5) Check containers:
   - docker ps --filter name=autogrid
6) Verify endpoints:
   - curl -I https://autogrid.falai.agency
   - curl -I https://autogrid.falai.agency/openapi.json

## 5) Rollback

If deploy fails:
1) Revert code (git checkout previous commit or tag).
2) Rebuild and restart:
   - docker compose -f docker-compose.vps.yml up -d --build
3) Verify endpoints again.

## 6) Post-Deploy Verification

Minimum checks:
- Login works in web UI
- Bot list loads
- Create / edit bot works
- Trades and balance load
- Start/stop bot works

