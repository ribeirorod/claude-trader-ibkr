"""TTL-based news cache backed by a single JSON file."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader.models import NewsItem


def _load_cache(path: Path) -> dict:
    """Load JSON cache file. Returns {} on missing or corrupt file."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_cache(path: Path, data: dict) -> None:
    """Write *data* as JSON, creating parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def write_cache(path: Path, ticker: str, items: list[NewsItem]) -> None:
    """Persist *items* for a single *ticker*, preserving other tickers."""
    data = _load_cache(path)
    data[ticker] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.model_dump() for item in items],
    }
    _save_cache(path, data)


def read_cache(
    path: Path, ticker: str, ttl_hours: float = 4.0
) -> list[NewsItem]:
    """Return cached items for *ticker*, or [] if expired / missing."""
    data = _load_cache(path)
    entry = data.get(ticker)
    if entry is None:
        return []

    fetched_at = datetime.fromisoformat(entry["fetched_at"])
    if datetime.now(timezone.utc) - fetched_at > timedelta(hours=ttl_hours):
        return []

    return [NewsItem(**item) for item in entry["items"]]


def fresh_tickers(path: Path, ttl_hours: float = 4.0) -> set[str]:
    """Return the set of tickers whose cache has not expired."""
    data = _load_cache(path)
    now = datetime.now(timezone.utc)
    result: set[str] = set()
    for ticker, entry in data.items():
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        if now - fetched_at <= timedelta(hours=ttl_hours):
            result.add(ticker)
    return result
