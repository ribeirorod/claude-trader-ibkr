FROM python:3.12-slim

RUN pip install uv --quiet && rm -rf /root/.cache

# Non-root user required by claude-agent-sdk --dangerously-skip-permissions
RUN useradd -r -u 1001 -m -s /bin/bash trader

WORKDIR /app

# Build deps + Node.js (for Claude Code CLI) — single layer, clean up caches
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev \
    libjpeg-dev zlib1g-dev libfreetype-dev \
    nodejs npm curl \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/* /root/.npm /tmp/*

# Install Python deps (cached — only rebuilds when pyproject.toml/uv.lock change)
COPY --chown=trader:trader pyproject.toml uv.lock ./
RUN chown trader:trader /app
USER trader
RUN uv sync --frozen --no-dev

# Install Playwright Chromium (needs root for system deps, then back to trader)
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
USER root
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/*
RUN chown -R trader:trader /app/playwright-browsers
USER trader

# Copy application code — owned by trader to avoid a costly chown layer
COPY --chown=trader:trader . .

# Pre-create dirs so named volumes inherit trader-user ownership on first mount
RUN mkdir -p /app/.trader /home/trader/.claude

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -sf http://localhost:9090/health || exit 1

EXPOSE 9090

CMD ["uv", "run", "trader-server"]
