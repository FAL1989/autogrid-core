# Repository Guidelines

## Project Structure and Module Organization
- `api/` holds the FastAPI backend (routes, services, models, core config).
- `bot/` contains the trading engine, strategies (`bot/strategies/`), and exchange connectors (`bot/exchange/`).
- `web/` is the Next.js 14 dashboard and API routes.
- `telegram/` houses the Telegram bot integration.
- `db/` stores database setup files (e.g., `db/init.sql`).
- `tests/` is split into `tests/unit/` and `tests/integration/`.

## Build, Test, and Development Commands
- `make install` installs Python and Node dependencies.
- `make dev` starts the full Docker-based dev stack.
- `make dev-api` and `make dev-web` run API or web locally.
- `make test`, `make test-unit`, `make test-integration` run pytest suites.
- `make lint` and `make format` run Python and web lint/format steps.
- `make build` builds the Docker images; `make docker-up` and `make docker-down` manage services.
- `make migrate` applies Alembic migrations.

## Coding Style and Naming Conventions
- Python: Black (line length 88), isort, flake8, mypy strict. Use `snake_case` for modules and functions, `PascalCase` for classes.
- Web: ESLint with Next.js and strict TypeScript. Use `PascalCase` for React components and `kebab-case` for file names (for example, `bots-list.tsx`, `use-dashboard.ts`).
- Run `make format` before committing; run `cd web && npm run lint` for UI-only changes.

## Testing Guidelines
- Pytest is the primary framework; naming follows `pytest.ini` (`test_*.py`, `Test*`, `test_*`).
- Unit tests live in `tests/unit/`; integration tests in `tests/integration/`.
- Coverage target is 80 percent; `make test` generates HTML and terminal coverage reports.

## Commit and Pull Request Guidelines
- Recent commits use short, imperative sentences (for example, "Add production-ready Docker Compose configuration...").
- Preferred format is Conventional Commits as described in `CONTRIBUTING.md` (for example, `feat(bot): add grid strategy`).
- PRs should include a clear description, linked issue if applicable, test evidence, and screenshots for UI changes.

## Security and Configuration Tips
- Use `.env` for local secrets and start from `.env.example`.
- Never commit API keys or exchange credentials; keep trade-only permissions on keys.
