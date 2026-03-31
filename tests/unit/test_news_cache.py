"""Tests for trader.news.cache — TTL-based news cache."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader.models import NewsItem
from trader.news.cache import (
    fresh_tickers,
    read_cache,
    write_cache,
)


def _make_item(ticker: str = "AAPL", idx: int = 1) -> NewsItem:
    return NewsItem(
        id=f"{ticker}-{idx}",
        ticker=ticker,
        headline=f"{ticker} headline {idx}",
        summary=f"summary {idx}",
        published_at="2026-03-31T10:00:00+00:00",
        source="test",
        url=f"https://example.com/{ticker}/{idx}",
    )


def test_write_and_read_cache(tmp_path: Path) -> None:
    cache_file = tmp_path / "news_cache.json"
    items = [_make_item("AAPL", i) for i in range(3)]

    write_cache(cache_file, "AAPL", items)
    result = read_cache(cache_file, "AAPL")

    assert len(result) == 3
    assert all(isinstance(r, NewsItem) for r in result)
    assert [r.id for r in result] == [i.id for i in items]


def test_read_cache_returns_empty_when_expired(tmp_path: Path) -> None:
    cache_file = tmp_path / "news_cache.json"
    items = [_make_item("AAPL")]

    write_cache(cache_file, "AAPL", items)

    # Backdate fetched_at to 5 hours ago (default TTL is 4 hours)
    data = json.loads(cache_file.read_text())
    data["AAPL"]["fetched_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=5)
    ).isoformat()
    cache_file.write_text(json.dumps(data))

    assert read_cache(cache_file, "AAPL") == []


def test_read_cache_returns_empty_for_missing_ticker(tmp_path: Path) -> None:
    cache_file = tmp_path / "news_cache.json"
    assert read_cache(cache_file, "AAPL") == []


def test_write_cache_preserves_other_tickers(tmp_path: Path) -> None:
    cache_file = tmp_path / "news_cache.json"

    write_cache(cache_file, "NVDA", [_make_item("NVDA")])
    write_cache(cache_file, "AAPL", [_make_item("AAPL")])

    assert len(read_cache(cache_file, "NVDA")) == 1
    assert len(read_cache(cache_file, "AAPL")) == 1


def test_fresh_tickers_lists_non_expired(tmp_path: Path) -> None:
    cache_file = tmp_path / "news_cache.json"

    write_cache(cache_file, "AAPL", [_make_item("AAPL")])
    write_cache(cache_file, "NVDA", [_make_item("NVDA")])

    result = fresh_tickers(cache_file)
    assert result == {"AAPL", "NVDA"}
