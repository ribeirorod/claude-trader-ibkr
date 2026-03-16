# Trader Server Design

**Date:** 2026-03-16
**Branch:** feature/trader-cli-rewrite
**Status:** Approved

---

## Overview

Replace the cron-driven, stateless polling architecture with a persistent FastAPI + APScheduler + Telegram polling server (`trader/server/`). The server runs via `uv run trader-server`, is Docker-ready, and mirrors the open-assistant architecture. All scheduled agent jobs run in-process via `claude-agent-sdk` (skill-aware, no open Claude session required).

---

## Architecture

### Module Layout

```
trader/server/
├── __init__.py
├── __main__.py       # async main() — wires all components, handles graceful shutdown
├── app.py            # FastAPI factory — /health, /status endpoints
├── scheduler.py      # APScheduler — loads .claude/crons.json, fires agent + script jobs
├── agent.py          # Claude SDK wrapper — in-process, skill-aware, session persistence
└── telegram.py       # python-telegram-bot — polling, command handlers, message dispatch
```

### Startup Sequence

1. Load config (`trader/config.py` + `IBKR_MODE`)
2. Start APScheduler — register all jobs from `.claude/crons.json`
3. Start FastAPI/uvicorn (reload=True when `IBKR_MODE=paper`, False for `live`)
4. Start Telegram polling (persistent, replaces 2-min cron script)
5. All components run concurrently via `asyncio.gather()`
6. Graceful shutdown on SIGINT/SIGTERM — stop polling, drain scheduler, shutdown uvicorn

### Entry Points

Added to `pyproject.toml`:
```toml
trader-server = "trader.server.__main__:main"
```

Run modes:
```bash
IBKR_MODE=paper uv run trader-server   # reload=True, DEBUG logging
IBKR_MODE=live  uv run trader-server   # reload=False, INFO logging
```

---

## Components

### 1. `scheduler.py` — APScheduler

Reads `.claude/crons.json` on startup. Two job types:

**Agent jobs** (`"type": "agent"`, e.g. portfolio-conductor slots):
- Run `agent.run_job(prompt, slot)` in-process via claude-agent-sdk
- Session ID derived from slot name for continuity across runs
- Results logged to `.trader/logs/agent.jsonl`

**System jobs** (`"type": "cmd"`, e.g. daily-report, ibkr-healthcheck):
- Run via `asyncio.create_subprocess_exec()`
- Scripts remain in `scripts/` unchanged

**Removed from `crons.json`:** `telegram-listener` entry — replaced by persistent server polling.

**Note:** `setup-crons.sh` and the system crontab remain for standalone (non-server) use.

### 2. `agent.py` — Claude SDK Wrapper

```python
ClaudeAgentOptions(
    system_prompt=TRADER_SYSTEM_PROMPT,   # full trader CLI reference + safety rules
    allowed_tools=["Bash", "Read", "Glob", "Grep"],
    cwd=PROJECT_ROOT,                      # .claude/ discoverable: agents, skills, hooks
    permission_mode="bypassPermissions",
)
```

- One `ClaudeSDKClient` per `session_id`, stored in `_clients: dict[str, ClaudeSDKClient]`
- Sessions persisted to `.trader/sessions/{id}.json`, rehydrated on startup
- Two call sites:
  - `agent.ask(message, chat_id)` → Telegram messages, returns streamed text
  - `agent.run_job(prompt, slot)` → scheduled jobs, fire-and-log

### 3. `telegram.py` — python-telegram-bot

**Command handlers:**
- `/start` — greeting + available commands list
- `/reset` — clear agent session for this chat
- `/status` — quick positions summary

**Message handler** (text, voice, photos, documents):
1. Show `ChatAction.TYPING` while agent processes
2. Dispatch to `agent.ask(message, chat_id)`
3. Split responses >4000 chars at newline boundaries
4. Send Markdown, fallback to plain text on parse error

**Voice:** OGG download → Groq Whisper transcription → same handler
**Photos/docs:** Download to `.trader/tmp/` → file path injected into agent context
**Auth:** Silent reject for any sender not matching `TELEGRAM_CHAT_ID`

### 4. `app.py` — FastAPI

Minimal — health and status only:
```
GET /health   → {"status": "ok"}
GET /status   → {"scheduler": "running", "jobs": [...], "ibkr_mode": "paper|live"}
```

---

## Security: `.claude/settings.json` Deny Rules

Added to existing `.claude/settings.json` to restrict the in-process agent:

```json
{
  "permissions": {
    "deny": [
      "Bash(rm *)",
      "Bash(mv .env*)",
      "Bash(cp .env*)",
      "Write(.env*)",
      "Write(*.pem)",
      "Write(*.key)",
      "Write(.trader/credentials*)",
      "Edit(.env*)",
      "Write(.claude/settings.json)",
      "Edit(.claude/settings.json)",
      "Bash(rm .claude/settings.json)",
      "Bash(mv .claude/settings.json*)"
    ]
  }
}
```

The settings file protects itself and all sensitive credential paths from agent modification.

---

## New Dependencies

```toml
"fastapi>=0.115",
"uvicorn>=0.34",
"apscheduler>=3.10",
"python-telegram-bot>=21.0",
```

---

## Docker (Future)

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
EXPOSE 8080
CMD ["uv", "run", "trader-server"]
```

```yaml
services:
  trader:
    build: .
    env_file: .env
    ports:
      - "8080:8080"
    volumes:
      - trader-data:/app/.trader
    restart: unless-stopped
volumes:
  trader-data:
```

**Known concern:** `ibkr-reauth.py` uses Playwright (browser-based IBKR re-auth). The slim Python image has no browser. Resolution options:
1. Use `mcr.microsoft.com/playwright/python` base image
2. Run gateway + reauth on host; container connects to it over network

To be addressed when containerizing.

---

## Files to Create

| File | Purpose |
|------|---------|
| `trader/server/__init__.py` | Package marker |
| `trader/server/__main__.py` | Async entry point |
| `trader/server/app.py` | FastAPI factory |
| `trader/server/scheduler.py` | APScheduler + crons.json loader |
| `trader/server/agent.py` | SDK wrapper |
| `trader/server/telegram.py` | Telegram handler |
| `Dockerfile` | Container build |
| `docker-compose.yml` | Compose config |

## Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add deps + `trader-server` entry point |
| `.claude/settings.json` | Add permissions deny rules |
| `.claude/crons.json` | Remove `telegram-listener` job |
