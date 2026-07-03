.PHONY: install dev lint test migrate docker-up docker-down

install:
	uv pip install -e ".[dev]"

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	ruff check app tests
	mypy app

test:
	pytest tests/ -v

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down

docker-logs:
	docker compose -f docker/docker-compose.yml logs -f api

clean:
	find . -type d -name __pycache__ | xargs rm -rf
	find . -name "*.pyc" -delete
