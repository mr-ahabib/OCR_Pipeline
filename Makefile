# Makefile for OCR Pipeline Project
# Provides convenient commands for development and deployment

.PHONY: help install dev run test clean migrate-up migrate-down migrate-create migrate-current migrate-history migrate-stamp migrate-reset

# Default target
help:
	@echo "═══════════════════════════════════════════════════════════"
	@echo "  OCR Pipeline - Available Commands"
	@echo "═══════════════════════════════════════════════════════════"
	@echo ""
	@echo "📦 Installation & Setup:"
	@echo "  make install          Install all dependencies"
	@echo "  make dev              Install dev dependencies"
	@echo ""
	@echo "🚀 Running Application:"
	@echo "  make run              Start development server"
	@echo "  make run-prod         Start production server"
	@echo ""
	@echo "🗄️  Database Management:"
	@echo "  make migrate-up       Apply all pending migrations"
	@echo "  make migrate-down     Rollback last migration"
	@echo "  make migrate-create   Create new migration (MSG='message')"
	@echo "  make migrate-current  Show current migration version"
	@echo "  make migrate-history  Show migration history"
	@echo "  make migrate-stamp    Mark current schema as migrated (fix state)"
	@echo "  make migrate-reset    Reset migration state (DANGEROUS)"
	@echo "  make db-init          Initialize database tables"
	@echo "  make db-recreate      Drop and recreate database (DANGEROUS)"
	@echo ""
	@echo "🧪 Testing & Quality:"
	@echo "  make test             Run all tests"
	@echo "  make lint             Run code linting"
	@echo "  make format           Format code with black"
	@echo ""
	@echo "🧹 Cleanup:"
	@echo "  make clean            Remove cache files"
	@echo "  make clean-all        Remove cache and virtual environment"
	@echo ""
	@echo "═══════════════════════════════════════════════════════════"

# Installation commands
install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt
	@echo "✅ Dependencies installed successfully!"

dev:
	@echo "📦 Installing development dependencies..."
	pip install -r requirements.txt
	pip install pytest pytest-cov black flake8 mypy
	@echo "✅ Dev dependencies installed!"

# Running application
run:
	@echo "🚀 Starting development server..."
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-prod:
	@echo "🚀 Starting production server..."
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Database migration commands (shortened)
migrate-up:
	@echo "⬆️  Applying migrations..."
	alembic upgrade head
	@echo "✅ Migrations applied successfully!"

migrate-down:
	@echo "⬇️  Rolling back last migration..."
	alembic downgrade -1
	@echo "✅ Rollback completed!"

migrate-create:
	@if [ -z "$(MSG)" ]; then \
		echo "❌ Error: Please provide a message with MSG='your message'"; \
		echo "Example: make migrate-create MSG='add user table'"; \
		exit 1; \
	fi
	@echo "📝 Creating new migration..."
	alembic revision --autogenerate -m "$(MSG)"
	@echo "✅ Migration created!"

migrate-current:
	@echo "📍 Current migration version:"
	alembic current

migrate-history:
	@echo "📜 Migration history:"
	alembic history --verbose

migrate-stamp:
	@echo "📌 Marking current database state as migrated..."
	@echo "⚠️  Use this when tables exist but migration tracking is out of sync"
	alembic stamp head
	@echo "✅ Migration state updated!"

migrate-reset:
	@echo "⚠️  DANGER: Resetting migration state..."
	@read -p "Are you sure? This will clear migration history. [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		PGPASSWORD=$${DATABASE_PASSWORD:-123456} psql -U $${DATABASE_USER:-postgres} -h $${DATABASE_HOST:-localhost} -d $${DATABASE_NAME:-OCR} -c "TRUNCATE alembic_version;"; \
		echo "✅ Migration state cleared!"; \
	else \
		echo "❌ Cancelled."; \
	fi

db-init:
	@echo "🗄️  Initializing database..."
	python -c "from app.db.init_db import init_db, create_initial_data; init_db(); create_initial_data()"
	@echo "✅ Database initialized!"

db-recreate:
	@echo "⚠️  DANGER: Dropping and recreating database..."
	@read -p "Are you sure? All data will be lost! [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		PGPASSWORD=$${DATABASE_PASSWORD:-123456} psql -U $${DATABASE_USER:-postgres} -h $${DATABASE_HOST:-localhost} -c "DROP DATABASE IF EXISTS $${DATABASE_NAME:-OCR};"; \
		PGPASSWORD=$${DATABASE_PASSWORD:-123456} psql -U $${DATABASE_USER:-postgres} -h $${DATABASE_HOST:-localhost} -c "CREATE DATABASE $${DATABASE_NAME:-OCR};"; \
		$(MAKE) migrate-up; \
		$(MAKE) db-init; \
		echo "✅ Database recreated!"; \
	else \
		echo "❌ Cancelled."; \
	fi

# Testing commands
test:
	@echo "🧪 Running tests..."
	pytest tests/ -v --cov=app --cov-report=html

lint:
	@echo "🔍 Running linter..."
	flake8 app/ --max-line-length=120

format:
	@echo "✨ Formatting code..."
	black app/ --line-length=120

# Cleanup commands
clean:
	@echo "🧹 Cleaning cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cache cleaned!"

clean-all: clean
	@echo "🧹 Removing virtual environment..."
	rm -rf venv/
	@echo "✅ All cleaned!"

# Docker commands (optional)
docker-build:
	@echo "🐳 Building Docker image..."
	docker build -t ocr-pipeline:latest .

docker-run:
	@echo "🐳 Running Docker container..."
	docker run -p 8000:8000 --env-file .env ocr-pipeline:latest

# Quick start command
quickstart: install migrate-up db-init
	@echo "🎉 Quick start complete!"
	@echo "Run 'make run' to start the server"
