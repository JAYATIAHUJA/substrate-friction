default:
	@just --list

install:
	uv sync --extra dev

test:
	uv run pytest -v -m "not engine"

test-engine:
	uv run pytest -v -m engine

probe:
	uv run python -m friction.probe

up:
	docker compose up -d
	@echo "waiting for readiness..."
	@until curl -sf http://127.0.0.1:9090/readyz >/dev/null; do sleep 1; done
	@echo "ready"

down:
	docker compose down -v
