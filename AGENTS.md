# Repository Guidelines

## Project Structure and Module Organization
- `api/` holds the FastAPI backend (routes, services, models, core config).
- `bot/` contains the trading engine, strategies (`bot/strategies/`), and exchange connectors (`bot/exchange/`).
- `autogrid_cli/` contains the CLI application.
- `db/` stores database setup files (e.g., `db/init.sql`).
- `tests/` is split into `tests/unit/` and `tests/integration/`.

## Build, Test, and Development Commands
- `make install` installs Python dependencies.
- `make dev` starts the Docker-based dev stack.
- `make dev-api` runs the API locally.
- `make test`, `make test-unit`, `make test-integration` run pytest suites.
- `make lint` and `make format` run Python lint/format steps.

## Coding Style and Naming Conventions
- Python: Black (line length 88), isort, flake8, mypy strict.
- Use `snake_case` for modules and functions, `PascalCase` for classes.

## Testing Guidelines
- Pytest is the primary framework; naming follows `pytest.ini` (`test_*.py`, `Test*`, `test_*`).
- Unit tests live in `tests/unit/`; integration tests in `tests/integration/`.
- Coverage target is 80 percent; `make test` generates HTML and terminal coverage reports.

## Commit and Pull Request Guidelines
- Recent commits use short, imperative sentences (for example, "Add grid strategy risk guard").
- Preferred format is Conventional Commits as described in `CONTRIBUTING.md`.

## Security and Configuration Tips
- Use `.env` for local secrets and start from `.env.example` if available.
- Never commit API keys or exchange credentials; keep trade-only permissions on keys.
