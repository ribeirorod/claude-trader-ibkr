#!/usr/bin/env python3
"""
Watchlist signal scan via pipeline discover — runs discovery with sentiment
scoring and sends Telegram push with candidates grouped by sector.

Usage:
  uv run python scripts/watchlist-signals.py

Reads:  .trader/watchlists.json (via pipeline discover)
Writes: .trader/pipeline/candidates.json (via pipeline discover)
Sends:  one Telegram message with discovered candidates and sentiment.
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


def _run_pipeline_discover() -> dict | None:
    """Run pipeline discover and return the CandidateSet as a dict."""
    try:
        result = subprocess.run(
            ["uv", "run", "trader", "pipeline", "discover"],
            capture_output=True, text=True, timeout=180, cwd=str(ROOT),
        )
        if result.returncode != 0:
            log.error("pipeline discover failed: %s", result.stderr[:300])
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.error("pipeline discover timed out")
        return None
    except json.JSONDecodeError:
        log.error("pipeline discover returned invalid JSON")
        return None
    except Exception as e:
        log.error("pipeline discover error: %s", e)
        return None


def _build_message(candidate_set: dict) -> str | None:
    """Format candidates into a concise Telegram message.

    Only surfaces actionable info: tickers with sentiment or news.
    Sectors shown as counts, not individual ticker lists.
    """
    regime = candidate_set.get("regime", "unknown")
    sectors = candidate_set.get("sectors", {})
    ticker_sentiment = candidate_set.get("ticker_sentiment", {})
    total = candidate_set.get("total_candidates", 0)
    watchlist_count = candidate_set.get("watchlist_count", 0)
    discovery_count = candidate_set.get("discovery_count", 0)

    if total == 0:
        return None

    now = datetime.now().strftime("%a %d %b  %H:%M CET")
    lines = [
        f"<b>DISCOVER — {now}</b>",
        f"{regime.upper()} · {total} candidates ({watchlist_count} WL + {discovery_count} scan)",
    ]

    # Collect tickers with notable sentiment or news
    movers: list[tuple[str, float, int]] = []  # (ticker, sentiment, news_count)
    for candidates in sectors.values():
        for c in candidates:
            ticker = c.get("ticker", "?")
            sentiment = ticker_sentiment.get(ticker, 0.0)
            news_count = len(c.get("news", []))
            if abs(sentiment) > 0.05 or news_count > 0:
                movers.append((ticker, sentiment, news_count))

    # Sort by abs(sentiment) descending
    movers.sort(key=lambda x: abs(x[1]), reverse=True)

    if movers:
        lines.append("")
        lines.append("<b>Movers</b>")
        rows = []
        for ticker, sentiment, news_count in movers[:15]:
            arrow = "▲" if sentiment > 0.05 else "▼" if sentiment < -0.05 else "·"
            news_tag = f"  ({news_count}n)" if news_count > 0 else ""
            rows.append(f"  {arrow} {ticker:<8} {sentiment:+.2f}{news_tag}")
        lines.append("<pre>" + "\n".join(rows) + "</pre>")
        if len(movers) > 15:
            lines.append(f"  ...+{len(movers) - 15} more")

    # Sector summary as counts (skip "Unknown")
    sector_counts = []
    for name, candidates in sorted(sectors.items()):
        if not candidates or name == "Unknown":
            continue
        sector_counts.append((name, len(candidates)))
    sector_counts.sort(key=lambda x: x[1], reverse=True)

    if sector_counts:
        lines.append("")
        lines.append("<b>Sectors</b>")
        top = sector_counts[:8]
        sector_parts = [f"{name} ({count})" for name, count in top]
        lines.append("  " + ", ".join(sector_parts))
        remaining = len(sector_counts) - len(top)
        if remaining > 0:
            lines.append(f"  ...+{remaining} more sectors")

    return "\n".join(lines)


def main() -> None:
    cfg = Config()

    cs = _run_pipeline_discover()
    if cs is None:
        log.error("Pipeline discover failed — nothing to send.")
        sys.exit(1)

    msg = _build_message(cs)
    if msg is None:
        log.info("No candidates found — nothing to send.")
        return

    ok = send_telegram(msg, config=cfg, parse_mode="HTML")
    if ok:
        total = cs.get("total_candidates", 0)
        log.info("Pipeline discover report sent (%d candidates).", total)
    else:
        log.error("Failed to send Telegram message.")
        sys.exit(1)


if __name__ == "__main__":
    main()
