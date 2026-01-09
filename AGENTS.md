# Repository Guidelines (autogrid-core)

## Scope and Role
- This repo is the core of AutoGrid: API, trading engine, strategies, CLI, and tests.
- Cloud UI and cloud-only API extensions live in the AutoGrid repo and consume GHCR images built from this repo.

## Architecture (Core)
- API layer (FastAPI):
  - Auth, bots, orders, credentials, trades, backtest endpoints.
  - Database access via SQLAlchemy async.
- Bot runtime:
  - Celery worker executes bot ticks and reconciliation.
  - Celery beat schedules periodic tasks.
- Trading engine:
  - Order generation, risk checks, and state transitions.
  - Strategies live in `bot/strategies/` (grid and DCA).
- Exchange integration:
  - CCXT connector for REST.
  - Websocket manager for fills and order updates.
- CLI:
  - `autogrid_cli/` uses the API; no direct DB access.

### Data Flow (Core)
- HTTP request -> FastAPI route -> service -> DB.
- Bot tick -> strategy calculates orders -> order manager -> exchange connector -> order updates -> DB.
- Websocket updates -> order manager -> DB -> stats/PnL updates.
- Reconciliation task -> exchange trades -> DB -> PnL recalculated.

## Project Structure and Module Organization
- `api/` holds the FastAPI backend (routes, services, models, core config).
- `bot/` contains the trading engine, strategies (`bot/strategies/`), and exchange connectors (`bot/exchange/`).
- `autogrid_cli/` contains the CLI application and entrypoint.
- `db/` stores database setup files (for example `db/init.sql`).
- `tests/` is split into `tests/unit/` and `tests/integration/`.

## Key Entry Points
- API app: `api/main.py`
- Celery tasks/worker logic: `bot/tasks.py`
- Trading engine: `bot/engine.py`
- Strategies: `bot/strategies/grid.py`, `bot/strategies/dca.py`
- CLI: `autogrid_cli/app.py`

## Environment and Configuration
- Start from `.env.example`; keep `.env` uncommitted.
- Required for local API/bot:
  - `DATABASE_URL`, `REDIS_URL`
  - `ENCRYPTION_KEY` (Fernet key, base64 urlsafe, 32 bytes)
  - `JWT_SECRET`
- Tests:
  - `TEST_DATABASE_URL` (defaults to `autogrid_test`)

## Build, Test, and Development Commands
- `make install` installs Python dependencies.
- `make dev` starts the Docker-based dev stack.
- `make dev-api` runs the API locally.
- `make test`, `make test-unit`, `make test-integration` run pytest suites.
- `make lint` and `make format` run Python lint/format steps.

## Testing Guidelines
- Pytest naming follows `pytest.ini` (`test_*.py`, `Test*`, `test_*`).
- Unit tests in `tests/unit/`; integration tests in `tests/integration/`.
- Integration tests expect Postgres + Redis available.
- Coverage target is 80 percent; `make test` generates HTML and terminal coverage reports.

## Lint, Format, Typecheck
- Black (line length 88), isort, flake8, mypy strict.
- Recommended local sequence:
  - `./.venv/bin/isort .`
  - `./.venv/bin/black .`
  - `./.venv/bin/flake8 bot/ api/ tests/`
  - `./.venv/bin/mypy api/ bot/`

## Database and Migrations
- Use Alembic for schema changes.
- Run `make migrate` before deploying schema changes.

## Releases and Images
- Core images are built and published to GHCR from this repo.
- Image tags must match what the cloud repo deploys.
- Prefer immutable tags (`vX.Y.Z` or `sha-<short>`).
- Do not build or retag images directly on the VPS.

## Production Integration Notes
- The cloud repo references the core images via:
  - `CORE_API_IMAGE=ghcr.io/fal1989/autogrid-core-api:<tag>`
  - `CORE_BOT_IMAGE=ghcr.io/fal1989/autogrid-core-bot:<tag>`
- Production and staging topology details live in `AutoGrid/docs/DEPLOY.md`.

## Commit and Pull Request Guidelines
- Short, imperative commit messages.
- Preferred format is Conventional Commits (`feat(core): ...`, `fix(core): ...`).

## Security and Configuration Tips
- Never commit API keys or exchange credentials.
- Keep trade-only permissions on exchange keys.
