#!/usr/bin/env python3
"""
Watchlist signal scan — runs RSI+news signals on all watchlists, sends Telegram push.

Usage:
  uv run python scripts/watchlist-signals.py

Reads:  outputs/watchlists.json
Sends:  one Telegram message with signals grouped by watchlist and signal type.
Runs:   weekdays 8:05am and 12:00pm CET via crons.json.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

sys.path.insert(0, str(ROOT))

from trader.config import Config
from trader.notify import send_telegram

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("watchlist-signals")

WATCHLISTS_PATH = ROOT / "outputs" / "watchlists.json"


def _load_watchlists() -> dict[str, list[str]]:
    """Load all watchlists. Returns {} if file is missing."""
    if not WATCHLISTS_PATH.exists():
        return {}
    return json.loads(WATCHLISTS_PATH.read_text())


def _run_signals(tickers: list[str]) -> list[dict]:
    """
    Run `trader strategies signals --with-news` via subprocess.

    Returns the parsed JSON array as-is — including per-ticker error dicts
    like {"ticker": "X", "error": "..."}. Returns [] only on subprocess
    failure (non-zero exit) or JSON parse error.
    """
    result = subprocess.run(
        [
            "uv", "run", "trader", "strategies", "signals",
            "--tickers", ",".join(tickers),
            "--with-news",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    if result.returncode != 0:
        log.error("signals_failed stderr=%s", result.stderr[:300])
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        log.error("signals_bad_json output=%s", result.stdout[:200])
        return []


def _fmt_signal_row(r: dict) -> str:
    """Format one successful ticker result as a fixed-width Telegram row."""
    label = r.get("signal_label", "hold").upper()
    ticker = r.get("ticker", "?")
    strategy = r.get("strategy", "rsi").upper()
    arrow = {"BUY": "↑", "SELL": "↓", "HOLD": "→"}.get(label, "→")
    sent = r.get("sentiment_score")  # field name matches CLI JSON output exactly
    sent_str = f"  sentiment {sent:+.2f}" if sent is not None else ""
    filtered = r.get("filtered", False)
    filter_reason_safe = r.get("filter_reason", "").replace("_", "\\_")
    filter_str = f"  [{filter_reason_safe}]" if filtered else ""
    return f"{label:<4} {ticker:<7} {strategy} {arrow}{sent_str}{filter_str}"


def _build_message(watchlists: dict[str, list[str]]) -> str | None:
    """
    Build the full Telegram message. Returns None if all lists are empty or
    produce no results.

    Grouping key: signal_label string ("buy"/"sell"/"hold").
    Error dicts (containing "error" key) are separated before grouping to
    avoid KeyError on missing signal_label.
    """
    now = datetime.now().strftime("%a %d %b  %H:%M CET")
    sections: list[str] = [f"*SIGNALS — {now}*"]
    any_content = False

    for list_name, tickers in sorted(watchlists.items()):
        if not tickers:
            continue
        results = _run_signals(tickers)
        if not results:
            log.warning(
                "signals_empty list=%s tickers=%s — subprocess returned no results",
                list_name,
                tickers,
            )
            continue
        any_content = True

        # Separate error dicts first to avoid KeyError on signal_label
        errors = [r for r in results if "error" in r]
        valid  = [r for r in results if "error" not in r]

        buys  = [r for r in valid if r.get("signal_label") == "buy"]
        sells = [r for r in valid if r.get("signal_label") == "sell"]
        holds = [r for r in valid if r.get("signal_label") == "hold"]

        rows: list[str] = []
        for group in (buys, sells, holds):
            for r in group:
                rows.append(_fmt_signal_row(r))
        for r in errors:
            rows.append(f"ERR  {r.get('ticker', '?'):<7}  {str(r.get('error', ''))[:40]}")

        sections += [
            "",
            f"*{list_name}*",
            "```",
            "\n".join(rows) if rows else "(no results)",
            "```",
        ]

    if not any_content:
        return None
    return "\n".join(sections)


def main() -> None:
    cfg = Config()
    watchlists = _load_watchlists()
    if not watchlists:
        log.info("No watchlists found — nothing to send.")
        return

    msg = _build_message(watchlists)
    if msg is None:
        log.info("All watchlists empty — nothing to send.")
        return

    ok = send_telegram(msg, config=cfg, parse_mode="Markdown")
    if ok:
        log.info("Signals report sent (%d lists).", len(watchlists))
    else:
        log.error("Failed to send Telegram message.")
        sys.exit(1)


if __name__ == "__main__":
    main()
