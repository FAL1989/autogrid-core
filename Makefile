# ===========================================
# AutoGrid Makefile
# ===========================================

.PHONY: help install dev test lint format build clean docker-up docker-down migrate

# Default target
help:
	@echo "AutoGrid Development Commands"
	@echo "=============================="
	@echo ""
	@echo "  make install     - Install all dependencies"
	@echo "  make dev         - Start development environment"
	@echo "  make test        - Run all tests"
	@echo "  make lint        - Run linters"
	@echo "  make format      - Format code"
	@echo "  make build       - Build for production"
	@echo "  make clean       - Clean temporary files"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make docker-up   - Start all Docker services"
	@echo "  make docker-down - Stop all Docker services"
	@echo "  make docker-logs - View Docker logs"
	@echo ""
	@echo "Database Commands:"
	@echo "  make migrate     - Run database migrations"
	@echo "  make migrate-new - Create new migration"

# ===========================================
# Installation
# ===========================================

install: install-python install-node

install-python:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt

install-node:
	@echo "Installing Node.js dependencies..."
	cd web && npm install

# ===========================================
# Development
# ===========================================

dev: docker-up
	@echo "Development environment started!"
	@echo "API: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"
	@echo "Web: http://localhost:3000"

dev-api:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd web && npm run dev

# ===========================================
# Testing
# ===========================================

test:
	pytest tests/ -v --cov=api --cov=bot --cov-report=html --cov-report=term

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-watch:
	pytest tests/ -v --watch

# ===========================================
# Linting & Formatting
# ===========================================

lint: lint-python lint-node

lint-python:
	@echo "Running Python linters..."
	black --check .
	isort --check-only .
	flake8 api/ bot/ tests/
	mypy api/ bot/

lint-node:
	@echo "Running Node.js linters..."
	cd web && npm run lint

format: format-python format-node

format-python:
	@echo "Formatting Python code..."
	black .
	isort .

format-node:
	@echo "Formatting Node.js code..."
	cd web && npm run lint:fix

typecheck:
	@echo "Running type checks..."
	mypy api/ bot/
	cd web && npm run typecheck

# ===========================================
# Build
# ===========================================

build: build-docker

build-docker:
	docker-compose build

build-web:
	cd web && npm run build

# ===========================================
# Docker
# ===========================================

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-restart:
	docker-compose restart

docker-clean:
	docker-compose down -v --rmi local

# ===========================================
# Database
# ===========================================

migrate:
	alembic upgrade head

migrate-new:
	@read -p "Migration name: " name; \
	alembic revision --autogenerate -m "$$name"

migrate-down:
	alembic downgrade -1

db-shell:
	docker-compose exec postgres psql -U postgres -d autogrid

# ===========================================
# Cleanup
# ===========================================

clean:
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf web/.next 2>/dev/null || true
	@echo "Done!"

# ===========================================
# CLI
# ===========================================

cli-init:
	python -m bot.cli init

cli-credentials:
	python -m bot.cli credentials add

cli-bot-create:
	python -m bot.cli bot create

cli-backtest:
	python -m bot.cli backtest
