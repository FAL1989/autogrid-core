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

Production monitoring stack (VPS):
- Location: `/opt/autogrid/monitoring`
- Compose file: `/opt/autogrid/monitoring/docker-compose.monitoring.yml`
- Env file: `/opt/autogrid/monitoring/.env` (currently used for `POSTGRES_PASSWORD`)
- Ports (localhost-only):
  - Prometheus: `127.0.0.1:9091`
  - Grafana: `127.0.0.1:3003` (default admin/admin, change after first login)
  - Alertmanager: `127.0.0.1:9094`
  - Blackbox: `127.0.0.1:9115`
  - Node exporter: `127.0.0.1:9101`
  - cAdvisor: `127.0.0.1:8081`
  - Postgres exporter: `127.0.0.1:9187`
  - Redis exporter: `127.0.0.1:9121`
- Config files:
  - Prometheus: `/opt/autogrid/monitoring/prometheus/prometheus.yml`
  - Prometheus alerts: `/opt/autogrid/monitoring/prometheus/alerts.yml`
  - Blackbox modules: `/opt/autogrid/monitoring/blackbox/blackbox.yml`
  - Alertmanager: `/opt/autogrid/monitoring/alertmanager/alertmanager.yml` (contains Telegram token/chat ID; keep chmod 600)
  - Grafana provisioning: `/opt/autogrid/monitoring/grafana/provisioning/`
  - Grafana dashboard: `/opt/autogrid/monitoring/grafana/dashboards/autogrid-overview.json`
- Blackbox targets (current):  
  - https://autogrid.falai.agency  
  - https://autogrid.falai.agency/login

Minimum recommended checks:
- HTTP uptime for web UI (root + login)
- Container health (docker ps status)
- CPU, memory, disk on the VPS
- Postgres and Redis health

Monitoring commands:
- Status: `docker compose -f /opt/autogrid/monitoring/docker-compose.monitoring.yml ps`
- Start/Update: `docker compose -f /opt/autogrid/monitoring/docker-compose.monitoring.yml up -d`
- Logs: `docker logs <container>`

## 3) Alerts

Active alert rules (Prometheus): `/opt/autogrid/monitoring/prometheus/alerts.yml`
- TargetDown (any scrape target down)
- HTTPProbeFailed (blackbox targets)
- HighCPU (>90% for 10m)
- LowMemory (<10% for 10m)
- LowDiskSpace (<10% for 15m)
- PostgresDown
- RedisDown

Alert routing (Alertmanager):
- Telegram only, configured in `/opt/autogrid/monitoring/alertmanager/alertmanager.yml`
- Keep the file protected (chmod 600). If token/chat ID changes, update the file and restart Alertmanager.

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
