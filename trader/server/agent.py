from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

log = structlog.get_logger(__name__)

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
    # ANTHROPIC_API_KEY is removed from os.environ by __main__.py at startup
    # so the SDK subprocess inherits an environment without it, forcing OAuth.
    return ClaudeAgentOptions(
        cwd=str(ROOT),
        allowed_tools=["Bash", "Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        system_prompt=system_prompt,
        model=_MODEL,
        max_turns=_MAX_TURNS,
    )
    


async def ask(text: str, chat_id: str) -> str:
    """Send a message from a Telegram user and return the agent's text response."""
    now = datetime.now().strftime("%a %d %b %Y  %H:%M CET")
    prompt = f"[{now}]\n{text}"
    parts: list[str] = []
    t0 = time.monotonic()
    log.info("agent_query_start", source="telegram", preview=text[:80])

    async for message in query(prompt=prompt, options=_build_options()):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(message, ResultMessage):
            if message.is_error:
                raise RuntimeError(str(message))
            # ResultMessage.result duplicates the last AssistantMessage — skip it

    result = "\n".join(parts).strip()
    log.info("agent_query_done", source="telegram", elapsed_s=round(time.monotonic() - t0, 1))
    return result


async def run_job(prompt: str, slot: str) -> None:
    """Run a scheduled agent job. Logs result to agent.jsonl."""
    log.info("agent_job_start", slot=slot)
    parts: list[str] = []
    t0 = time.monotonic()

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
        elapsed = round(time.monotonic() - t0, 1)
        _log_event("RUN_END", {"slot": slot, "result_preview": result_text[:200]})
        log.info("agent_job_done", slot=slot, elapsed_s=elapsed)

    except Exception as exc:
        log.error("agent_job_error", slot=slot, error=str(exc))
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


