#!/usr/bin/env python3
"""
Background per-ticker news fetcher (designed for cron).

Loads tickers from outputs/watchlists.json, skips those with fresh cache,
fetches news for the rest via the provider chain, and sends a Telegram summary.

Usage:
  uv run python scripts/news-fetcher.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Load .env before any project imports
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

sys.path.insert(0, str(ROOT))

from trader.config import Config  # noqa: E402
from trader.news.cache import fresh_tickers, write_cache  # noqa: E402
from trader.news.factory import get_news_provider  # noqa: E402
from trader.notify import send_telegram  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# -- constants ----------------------------------------------------------------
TTL_HOURS = 4.0
PER_TICKER_LIMIT = 5
DELAY_BETWEEN_TICKERS = 1.0

WATCHLIST_PATH = ROOT / "outputs" / "watchlists.json"
CACHE_PATH = ROOT / ".trader" / "pipeline" / "news-cache.json"


def _load_tickers() -> list[str]:
    """Return a sorted list of unique tickers from all watchlists."""
    try:
        data = json.loads(WATCHLIST_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Cannot load watchlists from %s: %s", WATCHLIST_PATH, exc)
        return []

    tickers: set[str] = set()
    for watchlist in data.values():
        if isinstance(watchlist, dict):
            tickers.update(watchlist.get("tickers", []))
    return sorted(tickers)


async def main() -> None:
    all_tickers = _load_tickers()
    if not all_tickers:
        logger.warning("No tickers found in %s — nothing to do", WATCHLIST_PATH)
        return

    logger.info("Loaded %d unique tickers from watchlists", len(all_tickers))

    fresh = fresh_tickers(CACHE_PATH, TTL_HOURS)
    stale = [t for t in all_tickers if t not in fresh]
    logger.info(
        "%d fresh (skipped), %d stale (to fetch)", len(fresh), len(stale),
    )

    if not stale:
        logger.info("All tickers are fresh — nothing to fetch")
        return

    config = Config()
    provider = get_news_provider(config)

    fetched = 0
    failed = 0

    try:
        for i, ticker in enumerate(stale, 1):
            logger.info("[%d/%d] Fetching news for %s", i, len(stale), ticker)
            try:
                items = await provider.get_news([ticker], limit=PER_TICKER_LIMIT)
                write_cache(CACHE_PATH, ticker, items)
                logger.info("  -> %d items cached for %s", len(items), ticker)
                fetched += 1
            except Exception:
                logger.exception("  -> FAILED for %s", ticker)
                failed += 1

            # Rate-limit delay (skip after last ticker)
            if i < len(stale):
                await asyncio.sleep(DELAY_BETWEEN_TICKERS)
    finally:
        await provider.aclose()

    summary = (
        f"News fetcher: {fetched} tickers updated, "
        f"{failed} failed, {len(fresh)} skipped (fresh)"
    )
    logger.info(summary)
    send_telegram(summary, config, parse_mode="Markdown")


if __name__ == "__main__":
    asyncio.run(main())
