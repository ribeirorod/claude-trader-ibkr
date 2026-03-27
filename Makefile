.PHONY: help install test server kill \
        docker-up docker-down docker-logs docker-gateway-logs \
        docker-reauth docker-status

# Default target
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install               Install all dependencies (including dev extras)"
	@echo "  test                  Run unit tests"
	@echo "  server                Start the trader server locally (FastAPI + scheduler + Telegram)"
	@echo "  kill                  Stop the local trader server"
	@echo ""
	@echo "  docker-up             Build and start all services (gateway + trader)"
	@echo "  docker-down           Stop and remove containers"
	@echo "  docker-status         Show container health and status"
	@echo "  docker-logs           Tail trader container logs"
	@echo "  docker-gateway-logs   Tail ibkr-gateway container logs"
	@echo "  docker-reauth         Manually trigger Playwright re-auth inside trader container"

install:
	uv sync --extra dev

test:
	uv run python -m pytest tests/ -v

server:
	uv run trader-server

kill:
	@pkill -f "trader-server" 2>/dev/null && echo "Server stopped." || echo "No server process found."

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-status:
	docker compose ps

docker-logs:
	docker compose logs -f trader

docker-gateway-logs:
	docker compose logs -f ibkr-gateway

docker-reauth:
	docker compose exec trader uv run python scripts/ibkr-reauth.py
