.PHONY: up down bot worker migrate test lint clean

# ─── Docker ───────────────────────────────────────────────────────────────────
up:
	docker-compose up -d

down:
	docker-compose down

# ─── Dev (local) ──────────────────────────────────────────────────────────────
bot:
	python -m app.bot.main

worker:
	celery -A app.workers.celery_app worker --loglevel=info --concurrency=4

api:
	uvicorn app.api.routes:api --reload --port 8000

# ─── Database ─────────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migration:
	alembic revision --autogenerate -m "$(MSG)"

# ─── Quality ──────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=app --cov-report=html

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

fmt:
	ruff format app/ tests/

# ─── Cleanup ──────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage
