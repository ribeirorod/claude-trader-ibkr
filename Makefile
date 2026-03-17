.PHONY: help install test server kill docker-up docker-down docker-logs

# Default target
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install       Install all dependencies (including dev extras)"
	@echo "  test          Run unit tests with the correct Python interpreter"
	@echo "  server        Start the trader server (FastAPI + scheduler + Telegram)"
	@echo "  kill          Stop the trader server"
	@echo "  docker-up     Build and start via docker-compose"
	@echo "  docker-down   Stop and remove docker-compose containers"
	@echo "  docker-logs   Tail docker-compose logs"

install:
	uv sync --extra dev

# Always use 'uv run python -m pytest' — bare 'pytest' picks up the system
# Python 3.12 from Homebrew and misses packages installed in the uv venv.
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

docker-logs:
	docker compose logs -f trader
