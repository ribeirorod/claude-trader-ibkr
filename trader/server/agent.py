from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import structlog
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
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

Watchlists (stored in .trader/watchlists.json):
  uv run trader watchlist list
  uv run trader watchlist add TICKER [TICKER ...] [--list name]
  uv run trader watchlist remove TICKER [--list name]
  uv run trader watchlist show [name] [--signals]
  uv run trader watchlist from-scan SCAN_TYPE [--list name] [--ema200-above] [--mktcap-above N]

Named watchlists — use these exact names:
  --list default        IBKR watchlist (scanned for signals automatically)
  --list tr-portfolio   Trade Republic holdings (monitor-only, no orders)
  --list tr-watchlist   Trade Republic watchlist (monitor-only, no orders)

Examples for natural language → CLI mapping:
  "add ASML to TR portfolio"     → trader watchlist add ASML --list tr-portfolio
  "remove NVDA from TR watchlist"→ trader watchlist remove NVDA --list tr-watchlist
  "show my TR portfolio"         → trader watchlist show tr-portfolio
  "what's on my IBKR watchlist"  → trader watchlist show default

Quotes & Signals:
  uv run trader quotes TICKER [TICKER ...]
  uv run trader signals TICKER [--strategy rsi|macd|ma_cross|bnf]

News & Sentiment:
  uv run trader news TICKER [--limit N] [--days N]

Market Regime:
  uv run trader market regime [--tickers SPY,QQQ]
  uv run trader market rotate [--tickers SPY,QQQ]

Market Scan:
  uv run trader scan run SCAN_TYPE [--market STK.US.MAJOR] [--limit N]
  uv run trader scan markets

Strategies:
  uv run trader strategies list
  uv run trader strategies signals --tickers T1,T2 --strategy STRAT [--with-options] [--regime bull|caution|bear]
  uv run trader strategies backtest STRATEGY TICKER [--days N]
  uv run trader strategies optimize STRATEGY TICKER

Options (buying puts/calls):
  uv run trader orders buy TICKER QTY --contract-type option --right put --strike N --expiry YYYY-MM-DD --type limit --price N
  uv run trader orders buy TICKER QTY --contract-type option --right call --strike N --expiry YYYY-MM-DD --type limit --price N

Notifications (progress updates to Telegram):
  uv run trader notify "message"

Reports:
  uv run python scripts/daily-report.py --slot open
  uv run python scripts/daily-report.py --slot close

Logs & state:
  tail -N .trader/logs/agent.jsonl
  tail -N .trader/logs/portfolio_evolution.jsonl
  cat .trader/profile.json
  cat .trader/watchlists.json

━━━ WEB RESEARCH ━━━

You have WebSearch and WebFetch tools for market research beyond the CLI.
Use them when: Benzinga news returns nothing, you need macro context,
scanning for new candidates, or validating a setup with external data.

WebSearch — search the web for market news, setups, screener results:
  "SMCI bearish technical setup March 2026"
  "stocks bouncing into 50 day moving average resistance"
  "UCITS inverse ETF Europe listed"
  "sector rotation defensive March 2026"

WebFetch — scrape specific pages for structured data:

  Finviz screener (bearish setups, below SMA200, high volume):
    https://finviz.com/screener.ashx?v=111&f=sh_avgvol_o1000,ta_sma200_pb,ta_sma50_pb&ft=4&o=-volume

  Finviz screener (oversold bounce candidates):
    https://finviz.com/screener.ashx?v=111&f=sh_avgvol_o500,ta_rsi_os30&o=rsi

  Finviz screener (overbought in downtrend — pullback short candidates):
    https://finviz.com/screener.ashx?v=111&f=ta_rsi_ob70,ta_sma200_pb&o=-rsi

  Barchart momentum (biggest losers / bearish momentum):
    https://www.barchart.com/stocks/momentum

  SlickCharts S&P 500 losers:
    https://www.slickcharts.com/sp500/losers

  SwingTradeBot screens (50/200 DMA resistance/support):
    https://swingtradebot.com/stock-screens/Moving%20Average

  ABG Analytics overbought/oversold:
    https://abg-analytics.com/overbought-oversold.shtml

  JustETF UCITS inverse/short ETFs:
    https://www.justetf.com/en/find-etf.html?assetClass=class-equity&strategy=Short

Tips:
- Finviz may block scraping (403) — fall back to WebSearch "finviz screener bearish below SMA200"
- Always cross-reference web findings with strategy signals before proposing trades
- Web data is supplementary — CLI signals + consensus are the primary decision drivers

━━━ REGIME-AWARE TRADING ━━━

Always run `uv run trader market regime` first. The regime does NOT block trades —
strategies already assess conditions. Regime adjusts SIZING and STOPS only.

Bear regime:
- Longs are ALLOWED if strategies signal buy — reduce position size to 50%
- Tighten stops to 1x ATR (instead of default 2x)
- Target cash reserve: 40%
- Also look for bearish setups:
  uv run trader strategies signals --tickers T1,T2 --strategy pullback --with-options --regime bear
  Signal -1 = bearish pullback → buy put or short (if margin available)
- Run `uv run trader market rotate` for defensive sector rotation

Caution regime:
- Reduce new entry sizing to 75%
- Prefer stocks with 3+ strategy consensus
- Run defensive rotation for partial hedges

Bull regime:
- Full position sizing, normal stops (2x ATR)

Account constraints (cash account, no margin):
- No short selling (requires margin)
- Options only if premium fits within position size guardrail
- Use inverse ETFs (UCITS only — US-listed ETFs not tradeable from EU) as bearish proxy
- Fractional shares are supported for all long positions

━━━ SCHEDULER ━━━

An APScheduler runs inside the server process — it handles ALL recurring jobs automatically:
- IBKR healthcheck + tickle: every 5 min
- Watchlist signals: 8:05am + 12:00pm CET
- Daily reports (BOD/EOD): 7:55am + 10:05pm CET
- Market analysis crons: eu-pre-market, eu-market, eu-us-overlap, us-market, weekly, monthly

These are defined in .claude/crons.json and loaded at server startup.
Do NOT create your own cron jobs, loops, or scheduled tasks — the scheduler already handles it.
If asked about tickle/healthcheck, confirm it runs every 5 minutes via the scheduler.

━━━ RULES ━━━

- Use Bash to run trader CLI commands and read files as needed
- Do NOT use CronCreate, CronDelete, or any cron management tools — the scheduler is managed externally
- You MAY place orders autonomously when all guardrails pass:
  • Max position size: €25 (25% of account)
  • Every entry MUST have a stop-loss (bracket order preferred, or defined-risk put)
  • Risk/reward ratio ≥ 2:1
  • Max 4 open positions at any time
  • Never go all-in — keep ≥ 30% cash reserve
  • For puts: max risk = premium paid, no stop needed (defined risk)
- Log ORDER_INTENT to agent.jsonl BEFORE placing any order
- After a fill, send confirmation to Telegram with ticker, qty, price, stop, target
- If guardrails fail, log the proposal but do NOT execute — send a Telegram alert instead
- For multi-step analysis (cron jobs, opportunity scans, portfolio reviews), send progress
  updates via `uv run trader notify "message"` so the user sees what's happening:
  • At the START of each major step: "Checking market regime...", "Scanning watchlist signals...",
    "Running risk assessment...", "Analyzing opportunities..."
  • Keep updates short — one line, no formatting needed
  • Do NOT send progress updates for simple user queries (quotes, single ticker checks)
- Be precise and to the point — lead with the answer, skip preamble
- Output is sent to Telegram — use only Telegram-compatible formatting:
  • **bold** for headers/emphasis, `code` for tickers/numbers/values
  • Bullet lists with - or *
  • Fenced code blocks (```...```) for multi-line data
  • [text](url) for links, ~~text~~ for strikethrough
  • Do NOT use markdown tables (|---|) — Telegram can't render them.
    Instead use aligned key: value pairs or bullet lists for structured data.
  • Keep messages concise — Telegram truncates at 4096 chars
- No emojis, no icons
- For analysis: key facts only — no restating the question, no filler sentences
"""

_MODEL = "claude-opus-4-6"
_MAX_TURNS = 30
_TG_MAX_CHARS = 4000

# ── Persistent client ────────────────────────────────────────────────────────
# A single ClaudeSDKClient lives for the lifetime of the server process.
# Each Telegram chat gets its own session_id, so conversation history persists
# across messages within the same chat.  Cron jobs use a separate session.

_client: ClaudeSDKClient | None = None


def _build_options(system_prompt: str = SYSTEM_PROMPT) -> ClaudeAgentOptions:
    # ANTHROPIC_API_KEY is removed from os.environ by __main__.py at startup
    # so the SDK subprocess inherits an environment without it, forcing OAuth.
    return ClaudeAgentOptions(
        cwd=str(ROOT),
        allowed_tools=["Bash", "Read", "Glob", "Grep", "WebFetch", "WebSearch"],
        permission_mode="bypassPermissions",
        system_prompt=system_prompt,
        model=_MODEL,
        max_turns=_MAX_TURNS,
    )


async def _get_client() -> ClaudeSDKClient:
    """Return the singleton ClaudeSDKClient, connecting on first use."""
    global _client
    if _client is None:
        _client = ClaudeSDKClient(options=_build_options())
        await _client.connect()
        log.info("agent_client_connected")
    return _client


async def _reset_client() -> ClaudeSDKClient:
    """Force-reconnect the SDK client (e.g. after a stale/dead session)."""
    global _client
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None
    return await _get_client()


async def _collect_response(client: ClaudeSDKClient) -> str:
    """Read streamed messages from the client until the result is complete."""
    parts: list[str] = []
    async for message in client.receive_messages():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(message, ResultMessage):
            if message.is_error:
                raise RuntimeError(str(message))
            break
    return "\n".join(parts).strip()


async def ask(text: str, chat_id: str) -> str:
    """Send a message from a Telegram user and return the agent's text response.

    Uses a persistent session keyed by chat_id so the agent remembers
    prior conversation within the same Telegram chat.

    If the SDK returns an empty response (dead subprocess), auto-reconnects
    and retries once.
    """
    now = datetime.now().strftime("%a %d %b %Y  %H:%M CET")
    prompt = f"[{now}]\n{text}"
    session_id = f"telegram-{chat_id}"
    t0 = time.monotonic()
    log.info("agent_query_start", source="telegram", session=session_id, preview=text[:80])

    client = await _get_client()
    await client.query(prompt, session_id=session_id)
    result = await _collect_response(client)

    # Detect dead client: 0-length response in <1s means subprocess is gone
    elapsed = time.monotonic() - t0
    if not result and elapsed < 2.0:
        log.warning("agent_empty_response_reconnecting", elapsed_s=round(elapsed, 1))
        client = await _reset_client()
        t0 = time.monotonic()
        await client.query(prompt, session_id=session_id)
        result = await _collect_response(client)

    log.info("agent_query_done", source="telegram", elapsed_s=round(time.monotonic() - t0, 1))
    return result or "(Agent returned no response. Try /reset and retry.)"


async def run_job(prompt: str, slot: str) -> None:
    """Run a scheduled agent job. Logs result to agent.jsonl.

    Cron jobs share a single 'cron' session so the agent has continuity
    across scheduled runs (e.g., morning brief → midday check → EOD report).
    """
    log.info("agent_job_start", slot=slot)
    session_id = f"cron-{slot}"
    t0 = time.monotonic()

    try:
        client = await _get_client()
        await client.query(prompt, session_id=session_id)
        result_text = await _collect_response(client)

        # Auto-reconnect on dead client
        elapsed = time.monotonic() - t0
        if not result_text and elapsed < 2.0:
            log.warning("agent_job_empty_response_reconnecting", slot=slot)
            client = await _reset_client()
            t0 = time.monotonic()
            await client.query(prompt, session_id=session_id)
            result_text = await _collect_response(client)

        elapsed = round(time.monotonic() - t0, 1)
        _log_event("RUN_END", {"slot": slot, "result_preview": result_text[:200]})
        log.info("agent_job_done", slot=slot, elapsed_s=elapsed)

    except Exception as exc:
        log.error("agent_job_error", slot=slot, error=str(exc))
        _log_event("RUN_ERROR", {"slot": slot, "error": str(exc)})
        raise


async def clear_session(chat_id: str) -> None:
    """Clear a Telegram chat session by disconnecting and reconnecting the client.

    The ClaudeSDKClient uses session_id to maintain history.  To reset,
    we disconnect the whole client — the next call to _get_client() will
    create a fresh one with no history for any session.
    """
    global _client
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None
    log.info("agent_session_cleared", chat_id=chat_id)


async def shutdown() -> None:
    """Disconnect the persistent client. Call on server shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.disconnect()
        except Exception:
            pass
        _client = None
        log.info("agent_client_disconnected")


def _log_event(event_type: str, data: dict) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }
    with _LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")
