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
        env={"ANTHROPIC_API_KEY": ""},  # Force Claude Code OAuth session
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
