# ===========================================
# AutoGrid Makefile
# ===========================================

.PHONY: help install dev test lint format build clean docker-up docker-down migrate

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

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

install: install-python

$(PYTHON):
	python3 -m venv $(VENV)
	$(PIP) install -U pip

install-python: $(PYTHON)
	@echo "Installing Python dependencies..."
	$(PIP) install -r requirements.txt

# ===========================================
# Development
# ===========================================

dev: docker-up
	@echo "Development environment started!"
	@echo "API: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"

dev-api:
	$(PYTHON) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# ===========================================
# Testing
# ===========================================

test:
	$(PYTHON) -m pytest tests/ -v --cov=api --cov=bot --cov-report=html --cov-report=term

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v

test-integration:
	$(PYTHON) -m pytest tests/integration/ -v

test-watch:
	$(PYTHON) -m pytest tests/ -v --watch

# ===========================================
# Linting & Formatting
# ===========================================

lint: lint-python

lint-python:
	@echo "Running Python linters..."
	$(PYTHON) -m black --check .
	$(PYTHON) -m isort --check-only .
	$(PYTHON) -m flake8 api/ bot/ tests/
	$(PYTHON) -m mypy api/ bot/

format: format-python

format-python:
	@echo "Formatting Python code..."
	$(PYTHON) -m black .
	$(PYTHON) -m isort .

typecheck:
	@echo "Running type checks..."
	$(PYTHON) -m mypy api/ bot/

# ===========================================
# Build
# ===========================================

build: build-docker

build-docker:
	docker-compose build

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
	$(PYTHON) -m alembic upgrade head

migrate-new:
	@read -p "Migration name: " name; \
	$(PYTHON) -m alembic revision --autogenerate -m "$$name"

migrate-down:
	$(PYTHON) -m alembic downgrade -1

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
	@echo "Done!"
