.PHONY: db-up db-down migrate verify-db test test-db lint typecheck build dev-api dev-web

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

migrate:
	uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head

verify-db:
	uv run --project apps/api python -m app.db

test:
	pnpm test
	uv run --project apps/api pytest apps/api/tests

test-db:
	uv run --project apps/api python scripts/test_db.py

.PHONY: seed-demo reset-demo
seed-demo:
	uv run --project apps/api python -m app.seed_demo

reset-demo:
	uv run --project apps/api python -m app.seed_demo --reset

lint:
	pnpm lint
	uv run --project apps/api ruff check apps/api scripts/test_db.py
	uv run --project apps/api ruff format --check apps/api scripts/test_db.py

typecheck:
	pnpm typecheck
	uv run --project apps/api mypy --config-file apps/api/pyproject.toml apps/api/app

build:
	pnpm build

dev-api:
	uv run --project apps/api uvicorn app.main:app --reload --reload-dir apps/api/app

dev-web:
	pnpm dev
