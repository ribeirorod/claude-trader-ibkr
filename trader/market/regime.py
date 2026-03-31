from __future__ import annotations
import json
import time
from enum import Enum
from pathlib import Path
from typing import Callable
import pandas as pd
import yfinance as yf


class MarketRegime(Enum):
    BULL = "bull"
    CAUTION = "caution"
    BEAR = "bear"


_FAST_WINDOW = 20
_SLOW_WINDOW = 50

# Module-level in-memory cache: {cache_key: {"regime": str, "ts": float}}
_cache: dict[str, dict] = {}


def _default_fetch(ticker: str, period: str, progress: bool) -> pd.DataFrame:
    raw = yf.download(ticker, period=period, progress=progress, auto_adjust=True)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    return raw


def _ma_state(ohlcv: pd.DataFrame) -> int:
    """Return +1 if fast MA > slow MA (bullish), -1 if fast < slow (bearish), 0 if equal."""
    close = ohlcv["close"]
    fast = close.rolling(_FAST_WINDOW).mean().iloc[-1]
    slow = close.rolling(_SLOW_WINDOW).mean().iloc[-1]
    if pd.isna(fast) or pd.isna(slow):
        raise ValueError(
            f"Not enough data for MA windows ({len(ohlcv)} rows, need {_SLOW_WINDOW})"
        )
    if fast > slow:
        return 1
    if fast < slow:
        return -1
    return 0


def _cache_key(tickers: list[str], lookback: str) -> str:
    return f"regime:{'|'.join(sorted(tickers))}:{lookback}"


def _read_file_cache(cache_dir: Path, key: str, ttl: int) -> MarketRegime | None:
    """Read from file cache. Returns MarketRegime if valid, None otherwise."""
    cache_file = cache_dir / "regime.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        if data.get("key") != key:
            return None
        if time.time() - data.get("ts", 0) >= ttl:
            return None
        return MarketRegime(data["regime"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _write_file_cache(cache_dir: Path, key: str, regime: MarketRegime) -> None:
    """Write regime to file cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "regime.json"
    cache_file.write_text(json.dumps({
        "key": key,
        "regime": regime.value,
        "ts": time.time(),
    }))


def detect_regime(
    tickers: list[str] | None = None,
    lookback: str = "200d",
    fetch_fn: Callable | None = None,
    cache_dir: Path | None = None,
    cache_ttl_seconds: int = 1800,
) -> MarketRegime:
    """Detect broad market regime via 20/50-day MA state on reference tickers.

    Uses MA level comparison (state-based), not crossover events, so the
    result reflects the current trend regardless of when the last cross was.

    Returns BULL if all tickers bullish, BEAR if all bearish, else CAUTION.

    When cache_dir is provided, results are cached (in-memory and on disk)
    for cache_ttl_seconds to avoid redundant yfinance downloads across
    pipeline stages. Without cache_dir, no caching is performed.
    """
    if tickers is None:
        tickers = ["SPY", "QQQ"]
    if fetch_fn is None:
        fetch_fn = _default_fetch

    use_cache = cache_dir is not None
    key = _cache_key(tickers, lookback)
    now = time.time()

    if use_cache:
        # Check file cache first (survives across process invocations)
        result = _read_file_cache(cache_dir, key, cache_ttl_seconds)
        if result is not None:
            _cache[key] = {"regime": result.value, "ts": now}
            return result

        # Check in-memory cache
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < cache_ttl_seconds:
                return MarketRegime(entry["regime"])

    # Cache miss (or caching disabled) — compute regime
    states: list[int] = []
    for ticker in tickers:
        ohlcv = fetch_fn(ticker, lookback, False)
        states.append(_ma_state(ohlcv))

    if all(s == 1 for s in states):
        regime = MarketRegime.BULL
    elif all(s == -1 for s in states):
        regime = MarketRegime.BEAR
    else:
        regime = MarketRegime.CAUTION

    # Store in caches when caching is enabled
    if use_cache:
        _cache[key] = {"regime": regime.value, "ts": time.time()}
        _write_file_cache(cache_dir, key, regime)

    return regime
