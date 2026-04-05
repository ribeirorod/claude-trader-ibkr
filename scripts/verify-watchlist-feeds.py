#!/usr/bin/env python3
"""Verify that all watchlist tickers have working Yahoo Finance data feeds.

Usage:
    uv run python scripts/verify-watchlist-feeds.py

Exits with code 1 if total working tickers < 50.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yfinance as yf

from trader.market.ticker_map import resolve_yf_ticker

WATCHLIST_PATH = Path(".trader/watchlists.json")
MIN_WORKING = 50


def main() -> int:
    if not WATCHLIST_PATH.exists():
        print(f"ERROR: {WATCHLIST_PATH} not found")
        return 1

    data = json.loads(WATCHLIST_PATH.read_text())

    # Collect all unique tickers across all watchlists
    all_tickers: set[str] = set()
    for entry in data.values():
        if isinstance(entry, dict):
            all_tickers.update(entry.get("tickers", []))
        elif isinstance(entry, list):
            all_tickers.update(entry)

    print(f"Total unique tickers: {len(all_tickers)}")
    print()

    working: list[str] = []
    failed: list[str] = []

    for ticker in sorted(all_tickers):
        yf_sym = resolve_yf_ticker(ticker)
        try:
            df = yf.download(yf_sym, period="5d", progress=False)
            if len(df) > 0:
                working.append(ticker)
                suffix = f" -> {yf_sym}" if yf_sym != ticker else ""
                print(f"  OK   {ticker}{suffix} ({len(df)} rows)")
            else:
                failed.append(ticker)
                suffix = f" -> {yf_sym}" if yf_sym != ticker else ""
                print(f"  FAIL {ticker}{suffix} (0 rows)")
        except Exception as e:
            failed.append(ticker)
            print(f"  FAIL {ticker} ({e})")

    print()
    print(f"Working: {len(working)}")
    print(f"Failed:  {len(failed)}")
    if failed:
        print(f"Failed tickers: {', '.join(failed)}")

    if len(working) < MIN_WORKING:
        print(f"\nERROR: Only {len(working)} working tickers, need >= {MIN_WORKING}")
        return 1

    print(f"\nPASS: {len(working)} working tickers >= {MIN_WORKING} minimum")
    return 0


if __name__ == "__main__":
    sys.exit(main())
