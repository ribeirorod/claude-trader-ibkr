# Trader Server Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cron-driven, stateless Telegram listener with a persistent FastAPI + APScheduler + python-telegram-bot server that runs via `uv run trader-server`.

**Architecture:** `trader/server/` subpackage wired in an async `main()` — APScheduler loads `.claude/crons.json` on startup and fires agent jobs (in-process claude-agent-sdk) and system jobs (subprocess). python-telegram-bot replaces the 2-min cron poller with persistent polling. FastAPI exposes `/health` and `/status`. Note: uvicorn `reload=True` is incompatible with programmatic `uvicorn.Server`; paper mode gets `DEBUG` logging instead.

**Tech Stack:** FastAPI 0.115+, uvicorn 0.34+, APScheduler 3.10+, python-telegram-bot 21.0+, claude-agent-sdk 0.1.48+ (already installed), groq (already installed)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `trader/server/__init__.py` | Package marker |
| Create | `trader/server/app.py` | FastAPI factory (`/health`, `/status`) |
| Create | `trader/server/agent.py` | SDK wrapper: `ask()` for Telegram, `run_job()` for scheduler |
| Create | `trader/server/scheduler.py` | APScheduler: loads `crons.json`, fires agent + script jobs |
| Create | `trader/server/telegram.py` | python-telegram-bot Application builder + handlers |
| Create | `trader/server/__main__.py` | Async `main()` that wires everything, graceful shutdown |
| Create | `tests/unit/server/test_app.py` | FastAPI endpoint tests |
| Create | `tests/unit/server/test_agent.py` | Agent wrapper unit tests |
| Create | `tests/unit/server/test_scheduler.py` | Scheduler cron-parsing + job dispatch tests |
| Create | `tests/unit/server/test_telegram.py` | Telegram auth + message routing tests |
| Modify | `pyproject.toml` | Add 4 deps + `trader-server` entry point |
| Modify | `.claude/settings.json` | Add permissions deny rules |
| Modify | `.claude/crons.json` | Remove `telegram-listener` job |
| Create | `Dockerfile` | Container build (future use) |
| Create | `docker-compose.yml` | Compose config (future use) |

---

## Chunk 1: Project Config Changes

### Task 1: Add dependencies and entry point

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps and entry point to pyproject.toml**

In `pyproject.toml`, add to `dependencies`:
```toml
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "apscheduler>=3.10",
    "python-telegram-bot>=21.0",
    "pillow>=10.0",
```

Add to `[project.scripts]`:
```toml
trader-server = "trader.server.__main__:main"
```

Note: `pillow` is needed for photo optimization (already used in telegram-listener.py but not listed as dep).

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
```

Expected: resolves and installs all 5 new packages with no errors.

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "import fastapi, uvicorn, apscheduler, telegram; print('OK')"
```

Expected: prints `OK`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add server dependencies (fastapi, uvicorn, apscheduler, python-telegram-bot)"
```

---

### Task 2: Harden .claude/settings.json with deny rules

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Read current settings**

Check current `.claude/settings.json` — it only has a `hooks` block with `SessionStart`.

- [ ] **Step 2: Add permissions deny block**

Replace contents of `.claude/settings.json` with:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh /Users/beam/projects/vibe/trader/scripts/setup-crons.sh"
          }
        ]
      }
    ]
  },
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

- [ ] **Step 3: Commit**

```bash
git add .claude/settings.json
git commit -m "security: add agent deny rules to .claude/settings.json"
```

---

### Task 3: Remove telegram-listener from crons.json

**Files:**
- Modify: `.claude/crons.json`

- [ ] **Step 1: Remove the telegram-listener job**

In `.claude/crons.json`, delete the last object (id: `telegram-listener`). The file should now have 9 entries (eu-pre-market through ibkr-healthcheck).

- [ ] **Step 2: Commit**

```bash
git add .claude/crons.json
git commit -m "feat: remove telegram-listener cron — replaced by persistent server polling"
```

---

## Chunk 2: FastAPI App

### Task 4: Create app.py with /health and /status

**Files:**
- Create: `trader/server/__init__.py`
- Create: `trader/server/app.py`
- Create: `tests/unit/server/__init__.py`
- Create: `tests/unit/server/test_app.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/server/__init__.py` (empty).

Create `tests/unit/server/test_app.py`:
```python
import pytest
from fastapi.testclient import TestClient


def test_health_returns_ok():
    from trader.server.app import create_app
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_returns_scheduler_info(monkeypatch):
    import trader.server.app as app_module
    monkeypatch.setenv("IBKR_MODE", "paper")
    # Inject a fake scheduler state
    fake_scheduler = type("S", (), {"running": True, "get_jobs": lambda self: []})()
    from trader.server.app import create_app
    app = create_app(scheduler=fake_scheduler)
    client = TestClient(app)
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["scheduler"] == "running"
    assert data["ibkr_mode"] == "paper"
    assert "jobs" in data
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/server/test_app.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `trader.server.app` doesn't exist yet.

- [ ] **Step 3: Create package marker**

Create `trader/server/__init__.py`:
```python
"""Trader persistent server — FastAPI + APScheduler + Telegram polling."""
```

- [ ] **Step 4: Implement app.py**

Create `trader/server/app.py`:
```python
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI


def create_app(scheduler: Any = None) -> FastAPI:
    app = FastAPI(title="Trader Server", version="0.1.0")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/status")
    async def status() -> dict:
        sched_running = getattr(scheduler, "running", False)
        jobs: list[dict] = []
        if scheduler and sched_running:
            jobs = [
                {"id": j.id, "next_run": str(j.next_run_time)}
                for j in scheduler.get_jobs()
            ]
        return {
            "scheduler": "running" if sched_running else "stopped",
            "jobs": jobs,
            "ibkr_mode": os.getenv("IBKR_MODE", "paper"),
        }

    return app
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/server/test_app.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add trader/server/__init__.py trader/server/app.py tests/unit/server/
git commit -m "feat: add trader/server package with FastAPI /health and /status"
```

---

## Chunk 3: Agent Wrapper

### Task 5: Create agent.py — SDK wrapper

**Files:**
- Create: `trader/server/agent.py`
- Create: `tests/unit/server/test_agent.py`

The agent wrapper adapts the existing `telegram-listener.py` `_ask()` function into a reusable module with two call sites: `ask()` for Telegram messages and `run_job()` for scheduled slots.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/server/test_agent.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_ask_returns_text_from_assistant_message():
    from claude_agent_sdk import AssistantMessage, TextBlock
    from trader.server.agent import ask

    # Use spec= so isinstance() checks in the real code work correctly
    mock_text_block = MagicMock(spec=TextBlock)
    mock_text_block.text = "AAPL is at $200"

    mock_assistant = MagicMock(spec=AssistantMessage)
    mock_assistant.content = [mock_text_block]

    async def fake_query(prompt, options):
        yield mock_assistant

    with patch("trader.server.agent.query", fake_query):
        result = await ask("What is AAPL?", chat_id="123")

    assert result == "AAPL is at $200"


@pytest.mark.asyncio
async def test_ask_raises_on_error_result():
    from claude_agent_sdk import ResultMessage
    from trader.server.agent import ask

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = True
    mock_result.__str__ = lambda self: "tool error"

    async def fake_query(prompt, options):
        yield mock_result

    with patch("trader.server.agent.query", fake_query):
        with pytest.raises(RuntimeError, match="tool error"):
            await ask("bad request", chat_id="123")


@pytest.mark.asyncio
async def test_run_job_does_not_raise_on_success():
    from claude_agent_sdk import ResultMessage
    from trader.server.agent import run_job

    mock_result = MagicMock(spec=ResultMessage)
    mock_result.is_error = False
    mock_result.result = "done"

    async def fake_query(prompt, options):
        yield mock_result

    with patch("trader.server.agent.query", fake_query):
        # Should complete without raising
        await run_job("Run eu-pre-market analysis", slot="eu-pre-market")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/server/test_agent.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement agent.py**

Create `trader/server/agent.py`:
```python
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
_LOG_PATH = ROOT / ".trader" / "logs" / "agent.jsonl"

SYSTEM_PROMPT = f"""\
You are the portfolio-conductor agent for an automated trading system.
You are being addressed directly by the portfolio owner via Telegram.
Working directory: {ROOT}

━━━ TRADER CLI REFERENCE ━━━

Positions & P&L:
  uv run trader positions list
  uv run trader positions pnl
  uv run trader positions close TICKER

Orders:
  uv run trader orders list [--status open|filled|cancelled|all]
  uv run trader orders buy TICKER QTY [--type market|limit|bracket] [--price N] [--take-profit N] [--stop-loss N]
  uv run trader orders sell TICKER QTY [--type market|limit|stop] [--price N]
  uv run trader orders bracket TICKER QTY --entry N --take-profit N --stop-loss N
  uv run trader orders stop TICKER --price N
  uv run trader orders trailing-stop TICKER --trail-percent N
  uv run trader orders take-profit TICKER --price N
  uv run trader orders cancel ORDER_ID
  uv run trader orders modify ORDER_ID [--price N] [--qty N]

Account:
  uv run trader account summary
  uv run trader account balance
  uv run trader account margin

Watchlists (stored in outputs/watchlists.json):
  uv run trader watchlist list
  uv run trader watchlist add TICKER [TICKER ...] [--list name]
  uv run trader watchlist remove TICKER [--list name]
  uv run trader watchlist show [name] [--signals]
  uv run trader watchlist from-scan SCAN_TYPE [--list name] [--ema200-above] [--mktcap-above N]

Quotes & Signals:
  uv run trader quotes TICKER [TICKER ...]
  uv run trader signals TICKER [--strategy rsi|macd|ma_cross|bnf]

News & Sentiment:
  uv run trader news TICKER [--limit N] [--days N]

Market Scan:
  uv run trader scan run SCAN_TYPE [--market STK.US.MAJOR] [--limit N]
  uv run trader scan markets

Strategies:
  uv run trader strategies list
  uv run trader strategies backtest STRATEGY TICKER [--days N]
  uv run trader strategies optimize STRATEGY TICKER

Reports:
  uv run python scripts/daily-report.py --slot open
  uv run python scripts/daily-report.py --slot close

Logs & state:
  tail -N .trader/logs/agent.jsonl
  tail -N .trader/logs/portfolio_evolution.jsonl
  cat .trader/profile.json
  cat outputs/watchlists.json

━━━ RULES ━━━

- Use Bash to run trader CLI commands and read files as needed
- Do NOT place buy/sell orders unless the user explicitly says to place an order
- For order placement, confirm ticker, qty, and price before executing
- Be precise and to the point — lead with the answer, skip preamble
- Use Markdown: *bold* for headers, `code` for tickers/values, code blocks for tables
- No emojis, no icons
- For analysis: key facts only — no restating the question, no filler sentences
"""

_MODEL = "claude-opus-4-6"
_MAX_TURNS = 30
_TG_MAX_CHARS = 4000


def _build_options(system_prompt: str = SYSTEM_PROMPT) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(ROOT),
        allowed_tools=["Bash", "Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        system_prompt=system_prompt,
        model=_MODEL,
        max_turns=_MAX_TURNS,
        env={"ANTHROPIC_API_KEY": ""},  # Empty string forces Claude Code OAuth (SDK checks absence vs empty string the same way)
    )


async def ask(text: str, chat_id: str) -> str:
    """Send a message from a Telegram user and return the agent's text response."""
    now = datetime.now().strftime("%a %d %b %Y  %H:%M CET")
    prompt = f"[{now}]\n{text}"
    parts: list[str] = []

    async for message in query(prompt=prompt, options=_build_options()):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(message, ResultMessage):
            if message.is_error:
                raise RuntimeError(str(message))
            if message.result:
                parts.append(message.result)

    return "\n".join(parts).strip()


async def run_job(prompt: str, slot: str) -> None:
    """Run a scheduled agent job. Logs result to agent.jsonl."""
    log.info("scheduler: running agent job slot=%s", slot)
    parts: list[str] = []

    try:
        async for message in query(prompt=prompt, options=_build_options()):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    raise RuntimeError(str(message))

        result_text = "\n".join(parts).strip()
        _log_event("RUN_END", {"slot": slot, "result_preview": result_text[:200]})
        log.info("scheduler: agent job complete slot=%s", slot)

    except Exception as exc:
        log.error("scheduler: agent job failed slot=%s error=%s", slot, exc)
        _log_event("RUN_ERROR", {"slot": slot, "error": str(exc)})
        raise


def _log_event(event_type: str, data: dict) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }
    with _LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def split_for_telegram(text: str, max_chars: int = _TG_MAX_CHARS) -> list[str]:
    """Split long text at newline boundaries for Telegram's 4096-char limit."""
    chunks: list[str] = []
    while len(text) > max_chars:
        split_at = text.rfind("\n", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)
    return [c for c in chunks if c.strip()]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/server/test_agent.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/server/agent.py tests/unit/server/test_agent.py
git commit -m "feat: add trader/server/agent.py — SDK wrapper with ask() and run_job()"
```

---

## Chunk 4: Scheduler

### Task 6: Create scheduler.py — APScheduler + crons.json loader

**Files:**
- Create: `trader/server/scheduler.py`
- Create: `tests/unit/server/test_scheduler.py`

The scheduler reads `.claude/crons.json` and maps jobs. Discriminator: `"agent": "system"` → subprocess via `cmd` field; any other value → `run_job()` via agent.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/server/test_scheduler.py`:
```python
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


SAMPLE_CRONS = [
    {
        "id": "eu-pre-market",
        "cron": "3 8 * * 1-5",
        "label": "EU pre-market",
        "agent": "portfolio-conductor",
        "slot": "eu-pre-market",
        "prompt": "Run EU pre-market analysis.",
    },
    {
        "id": "ibkr-healthcheck",
        "cron": "*/5 * * * *",
        "label": "IBKR health check",
        "agent": "system",
        "cmd": "uv run python scripts/ibkr-healthcheck.py",
        "prompt": "Run health check.",
    },
]


def test_load_crons_parses_correctly(tmp_path):
    from trader.server.scheduler import load_crons

    crons_file = tmp_path / "crons.json"
    crons_file.write_text(json.dumps(SAMPLE_CRONS))
    jobs = load_crons(crons_file)
    assert len(jobs) == 2
    assert jobs[0]["id"] == "eu-pre-market"
    assert jobs[1]["id"] == "ibkr-healthcheck"


def test_is_agent_job():
    from trader.server.scheduler import is_agent_job

    assert is_agent_job({"agent": "portfolio-conductor"}) is True
    assert is_agent_job({"agent": "system"}) is False


def test_build_scheduler_registers_jobs(tmp_path):
    from trader.server.scheduler import build_scheduler

    crons_file = tmp_path / "crons.json"
    crons_file.write_text(json.dumps(SAMPLE_CRONS))

    with patch("trader.server.scheduler.run_job", new_callable=AsyncMock):
        scheduler = build_scheduler(crons_path=crons_file)
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert "eu-pre-market" in job_ids
        assert "ibkr-healthcheck" in job_ids
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/server/test_scheduler.py -v
```

Expected: `ImportError` — module doesn't exist.

- [ ] **Step 3: Implement scheduler.py**

Create `trader/server/scheduler.py`:
```python
from __future__ import annotations

import asyncio
import json
import logging
import shlex
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.server.agent import run_job

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CRONS_PATH = ROOT / ".claude" / "crons.json"


def load_crons(crons_path: Path = DEFAULT_CRONS_PATH) -> list[dict]:
    """Load and return all job definitions from crons.json."""
    return json.loads(crons_path.read_text())


def is_agent_job(job: dict) -> bool:
    """Return True if this job should be dispatched to the claude-agent-sdk."""
    return job.get("agent", "system") != "system"


async def _run_agent_job(job: dict) -> None:
    await run_job(prompt=job["prompt"], slot=job.get("slot", job["id"]))


async def _run_script_job(job: dict) -> None:
    cmd = job["cmd"]
    log.info("scheduler: running script job id=%s cmd=%s", job["id"], cmd)
    args = shlex.split(cmd)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.error(
            "scheduler: script job failed id=%s rc=%d stderr=%s",
            job["id"],
            proc.returncode,
            stderr.decode(errors="replace")[:500],
        )
    else:
        log.info("scheduler: script job done id=%s", job["id"])


def build_scheduler(crons_path: Path = DEFAULT_CRONS_PATH) -> AsyncIOScheduler:
    """Create, populate, and return an AsyncIOScheduler (not yet started)."""
    scheduler = AsyncIOScheduler()
    jobs = load_crons(crons_path)

    for job in jobs:
        trigger = CronTrigger.from_crontab(job["cron"])
        if is_agent_job(job):
            scheduler.add_job(
                _run_agent_job,
                trigger=trigger,
                args=[job],
                id=job["id"],
                replace_existing=True,
            )
        else:
            scheduler.add_job(
                _run_script_job,
                trigger=trigger,
                args=[job],
                id=job["id"],
                replace_existing=True,
            )
        log.info("scheduler: registered %s [%s]", job["id"], job["cron"])

    return scheduler
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/server/test_scheduler.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/server/scheduler.py tests/unit/server/test_scheduler.py
git commit -m "feat: add trader/server/scheduler.py — APScheduler loading crons.json"
```

---

## Chunk 5: Telegram Handler

### Task 7: Create telegram.py — python-telegram-bot Application

**Files:**
- Create: `trader/server/telegram.py`
- Create: `tests/unit/server/test_telegram.py`

This ports the logic from `scripts/telegram-listener.py` into a persistent `Application`. The `_ask()` → `agent.ask()`. Media handling (voice, photos, docs) is preserved verbatim. Auth guard is by `TELEGRAM_CHAT_ID`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/server/test_telegram.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_update(chat_id: str, text: str = "hello") -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = int(chat_id)
    update.message.text = text
    update.message.voice = None
    update.message.document = None
    update.message.photo = None
    update.message.caption = None
    update.message.reply_text = AsyncMock()
    update.message.reply_markdown = AsyncMock()
    return update


def test_build_telegram_app_returns_application(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    from trader.server.telegram import build_telegram_app
    app = build_telegram_app()
    assert app is not None


@pytest.mark.asyncio
async def test_unauthorized_message_is_ignored(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    from trader.server.telegram import _handle_message

    update = _make_update(chat_id="999", text="intruder")
    ctx = MagicMock()

    with patch("trader.server.telegram.agent.ask", new_callable=AsyncMock) as mock_ask:
        await _handle_message(update, ctx)
        mock_ask.assert_not_called()


@pytest.mark.asyncio
async def test_authorized_message_dispatches_to_agent(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
    from trader.server.telegram import _handle_message

    update = _make_update(chat_id="456", text="show positions")
    ctx = MagicMock()

    with patch("trader.server.telegram.agent.ask", new_callable=AsyncMock, return_value="AAPL: 10 shares") as mock_ask:
        with patch("trader.server.telegram._send_response", new_callable=AsyncMock):
            await _handle_message(update, ctx)
            mock_ask.assert_called_once()
            # text is the first positional arg to agent.ask(text, chat_id=...)
            assert mock_ask.call_args.args[0] == "show positions"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/server/test_telegram.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement telegram.py**

Create `trader/server/telegram.py`:
```python
from __future__ import annotations

import asyncio
import logging
import os
import traceback
from datetime import datetime
from pathlib import Path

from telegram import ChatAction, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from trader.server import agent

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
TMP_DIR = ROOT / ".trader" / "tmp"
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"


def _authorized_chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def _is_authorized(update: Update) -> bool:
    allowed = _authorized_chat_id()
    if not allowed:
        return False
    return str(update.effective_chat.id) == allowed


async def _send_response(update: Update, text: str) -> None:
    """Send response, splitting at 4000 chars. Falls back to plain text on parse error."""
    chunks = agent.split_for_telegram(text)
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            try:
                await update.message.reply_text(chunk)
            except Exception as exc:
                log.error("Failed to send Telegram message: %s", exc)


async def _keep_typing(update: Update, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await update.message.chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(4)


def _transcribe_voice(file_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Sync — runs in thread pool via asyncio.to_thread."""
    import groq
    client = groq.Groq(api_key=os.getenv("GROQ_API_KEY", ""))
    transcription = client.audio.transcriptions.create(
        model=GROQ_WHISPER_MODEL,
        file=(filename, file_bytes),
        response_format="text",
    )
    return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()


def _optimise_image(data: bytes, max_dim: int = 1280, quality: int = 82) -> bytes:
    """Sync — runs in thread pool via asyncio.to_thread."""
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


async def _handle_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text(
        "*Trader Bot*\n\nAvailable commands:\n"
        "/status — quick positions summary\n"
        "/reset — clear this conversation session\n\n"
        "Or just send any message to talk to the portfolio agent.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _handle_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text("Session cleared. Starting fresh.")


async def _handle_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    chat_id = str(update.effective_chat.id)
    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update, stop))
    try:
        response = await agent.ask("Show current positions and account summary.", chat_id=chat_id)
    except Exception as exc:
        response = f"Error: {exc}"
    finally:
        stop.set()
        typing_task.cancel()
    await _send_response(update, response)


async def _handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return

    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()

    # Voice
    if update.message.voice and not text:
        try:
            voice_file = await ctx.bot.get_file(update.message.voice.file_id)
            audio_bytes = await voice_file.download_as_bytearray()
            text = await asyncio.to_thread(_transcribe_voice, bytes(audio_bytes))
            log.info("Voice transcribed: %s", text[:80])
        except Exception as exc:
            log.error("Transcription failed: %s", exc)
            await update.message.reply_text(f"Transcription failed: {exc}")
            return

    # Document
    if update.message.document and not text and not update.message.photo:
        doc = update.message.document
        fname = doc.file_name or f"document-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        caption = (update.message.caption or "").strip()
        try:
            doc_file = await ctx.bot.get_file(doc.file_id)
            doc_bytes = await doc_file.download_as_bytearray()
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            doc_path = TMP_DIR / fname
            doc_path.write_bytes(bytes(doc_bytes))
            text = f"{caption}\n\n[Document saved at: {doc_path}]" if caption else f"[Document saved at: {doc_path}]"
        except Exception as exc:
            await update.message.reply_text(f"Could not download document: {exc}")
            return

    # Photo
    if update.message.photo:
        best = max(update.message.photo, key=lambda p: p.file_size or 0)
        caption = (update.message.caption or "").strip()
        try:
            photo_file = await ctx.bot.get_file(best.file_id)
            img_bytes = await photo_file.download_as_bytearray()
            img_bytes = await asyncio.to_thread(_optimise_image, bytes(img_bytes))
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            img_path = TMP_DIR / f"tg-photo-{ts}.jpg"
            img_path.write_bytes(img_bytes)
            text = f"{caption}\n\n[Image saved at: {img_path}]" if caption else f"[Image saved at: {img_path}]"
        except Exception as exc:
            await update.message.reply_text(f"Could not download image: {exc}")
            return

    if not text:
        return

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update, stop))
    try:
        response = await agent.ask(text, chat_id=chat_id)
        await _send_response(update, response)
    except Exception as exc:
        tb = traceback.format_exc()
        log.error("Agent error: %s\n%s", exc, tb)
        short = str(exc)
        if "exit code" in short.lower() or len(short) < 20:
            short = tb.strip().splitlines()[-1]
        await update.message.reply_text(
            f"Agent error: {short}\n\nCheck `.trader/logs/` for full traceback."
        )
    finally:
        stop.set()
        typing_task.cancel()


def build_telegram_app() -> Application:
    """Build and return the Telegram Application (not yet started)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN must be set")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("reset", _handle_reset))
    app.add_handler(CommandHandler("status", _handle_status))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, _handle_message))
    return app
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/unit/server/test_telegram.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/server/telegram.py tests/unit/server/test_telegram.py
git commit -m "feat: add trader/server/telegram.py — persistent python-telegram-bot handler"
```

---

## Chunk 6: Entry Point + Docker

### Task 8: Create __main__.py — async main wiring everything together

**Files:**
- Create: `trader/server/__main__.py`

- [ ] **Step 1: Implement __main__.py**

Create `trader/server/__main__.py`:
```python
from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import uvicorn

from trader.server.app import create_app
from trader.server.scheduler import build_scheduler
from trader.server.telegram import build_telegram_app

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def _configure_logging() -> None:
    level = logging.DEBUG if os.getenv("IBKR_MODE", "paper") == "paper" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s  %(message)s",
    )


async def _run() -> None:
    _configure_logging()
    is_paper = os.getenv("IBKR_MODE", "paper") == "paper"

    # 1. Scheduler
    scheduler = build_scheduler()
    scheduler.start()
    log.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # 2. FastAPI
    app = create_app(scheduler=scheduler)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.getenv("SERVER_PORT", "8080")),
        log_level="debug" if is_paper else "info",
        reload=False,  # reload not compatible with programmatic run; use --reload via CLI if needed
    )
    server = uvicorn.Server(config)

    # 3. Telegram
    tg_app = build_telegram_app()
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram polling started")

    # 4. Run until interrupted
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    server_task = asyncio.create_task(server.serve())

    try:
        await stop_event.wait()
    finally:
        log.info("Shutting down...")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        scheduler.shutdown(wait=False)
        server.should_exit = True
        await server_task
        log.info("Shutdown complete")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test the entry point (dry run — no live broker needed)**

```bash
TELEGRAM_BOT_TOKEN=123456:ABCdefGHIjklMNOpqrSTUvwxyz TELEGRAM_CHAT_ID=0 IBKR_MODE=paper timeout 5 uv run trader-server 2>&1 || true
```

Expected: server starts, logs "Scheduler started with N jobs", then fails on Telegram polling (invalid token, no network) and exits. No import errors — a `telegram.error.NetworkError` or similar is acceptable here; the goal is to confirm all modules load and the scheduler initialises correctly.

- [ ] **Step 3: Commit**

```bash
git add trader/server/__main__.py
git commit -m "feat: add trader/server/__main__.py — async main wiring scheduler + uvicorn + telegram"
```

---

### Task 9: Add Dockerfile and docker-compose.yml (future use)

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

Create `Dockerfile`:
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

- [ ] **Step 2: Create docker-compose.yml**

Create `docker-compose.yml`:
```yaml
services:
  trader:
    build: .
    env_file: .env
    ports:
      - "8080:8080"
    volumes:
      - trader-data:/app/.trader   # sessions, logs, tmp
    restart: unless-stopped

volumes:
  trader-data:
```

- [ ] **Step 3: Add .dockerignore**

Create `.dockerignore`:
```
.env
.git
.venv
__pycache__
*.pyc
.DS_Store
clientportal.gw.zip
tests/
docs/
.trader/
```

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: add Dockerfile and docker-compose.yml for trader-server"
```

---

## Chunk 7: Full Test Suite + Smoke Run

### Task 10: Run all server tests and verify entry point

- [ ] **Step 1: Run all server unit tests**

```bash
uv run pytest tests/unit/server/ -v
```

Expected: all tests pass (app: 2, agent: 3, scheduler: 3, telegram: 3 = 11 total).

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v --ignore=tests/integration
```

Expected: all existing tests still pass, no regressions.

- [ ] **Step 3: Verify CLI entry point is installed**

```bash
uv run trader-server --help 2>&1 || uv run python -m trader.server --help 2>&1 || echo "no --help, checking import"
uv run python -c "from trader.server.__main__ import main; print('entry point OK')"
```

Expected: prints `entry point OK`.

- [ ] **Step 4: Verify setup-crons.sh no longer registers telegram-listener**

```bash
grep telegram-listener .claude/crons.json && echo "FOUND - must remove" || echo "OK - not present"
```

Expected: `OK - not present`.

- [ ] **Step 5: Final commit**

```bash
git add trader/ tests/unit/server/ pyproject.toml uv.lock .claude/settings.json .claude/crons.json Dockerfile docker-compose.yml .dockerignore
git commit -m "feat: trader-server complete — FastAPI + APScheduler + Telegram polling"
```

---

## Running the Server

```bash
# Paper mode (DEBUG logging, connects to paper IBKR account)
IBKR_MODE=paper uv run trader-server

# Live mode (INFO logging)
IBKR_MODE=live uv run trader-server

# Override port
SERVER_PORT=9000 uv run trader-server

# Health check
curl http://localhost:8080/health
curl http://localhost:8080/status
```

## Known Limitations

- **Playwright in Docker:** `ibkr-reauth.py` uses browser automation. The slim Python image has no browser. Options: (1) use `mcr.microsoft.com/playwright/python` base image, (2) run gateway on host and have container connect to it over network. To be addressed when containerizing.
- **uvicorn reload:** `reload=True` is not compatible with programmatic `uvicorn.Server`. To use reload in paper mode, run via CLI: `uvicorn trader.server.app:create_app --reload --factory`. The programmatic mode (used by `trader-server`) always runs without reload but restarts fast via Docker/launchd.
