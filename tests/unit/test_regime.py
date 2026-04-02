from __future__ import annotations
import time
import pandas as pd
import numpy as np
from trader.market.regime import MarketRegime, detect_regime, _cache


def _make_ohlcv(n: int = 100, trend: str = "up") -> pd.DataFrame:
    """Synthetic OHLCV — trend='up' produces fast MA > slow MA, 'down' fast < slow."""
    close = np.linspace(100, 150, n) if trend == "up" else np.linspace(150, 100, n)
    return pd.DataFrame({
        "open":  close * 0.99,
        "high":  close * 1.01,
        "low":   close * 0.98,
        "close": close,
        "volume": np.ones(n) * 1_000_000,
    })


def _fetch_both_bull(ticker, period, progress):
    return _make_ohlcv(trend="up")


def _fetch_both_bear(ticker, period, progress):
    return _make_ohlcv(trend="down")


def _fetch_mixed(ticker, period, progress):
    return _make_ohlcv(trend="up") if ticker == "SPY" else _make_ohlcv(trend="down")


def test_both_bullish_returns_bull():
    regime = detect_regime(tickers=["SPY", "QQQ"], fetch_fn=_fetch_both_bull)
    assert regime == MarketRegime.BULL


def test_both_bearish_returns_bear():
    regime = detect_regime(tickers=["SPY", "QQQ"], fetch_fn=_fetch_both_bear)
    assert regime == MarketRegime.BEAR


def test_mixed_signals_returns_caution():
    regime = detect_regime(tickers=["SPY", "QQQ"], fetch_fn=_fetch_mixed)
    assert regime == MarketRegime.CAUTION


def test_regime_enum_values():
    assert MarketRegime.BULL.value == "bull"
    assert MarketRegime.CAUTION.value == "caution"
    assert MarketRegime.BEAR.value == "bear"


def test_regime_caches_result(tmp_path):
    """Second call with same params should use cache, not call fetch_fn again."""
    _cache.clear()
    call_count = 0

    def counting_fetch(ticker, period, progress):
        nonlocal call_count
        call_count += 1
        return _make_ohlcv(trend="up")

    r1 = detect_regime(
        tickers=["SPY", "QQQ"],
        fetch_fn=counting_fetch,
        cache_dir=tmp_path,
        cache_ttl_seconds=300,
    )
    first_count = call_count

    r2 = detect_regime(
        tickers=["SPY", "QQQ"],
        fetch_fn=counting_fetch,
        cache_dir=tmp_path,
        cache_ttl_seconds=300,
    )
    assert r1 == r2 == MarketRegime.BULL
    # Second call should NOT have incremented the counter
    assert call_count == first_count


def test_regime_cache_expires(tmp_path):
    """With TTL=0 and a small sleep, cache should expire and refetch."""
    _cache.clear()
    call_count = 0

    def counting_fetch(ticker, period, progress):
        nonlocal call_count
        call_count += 1
        return _make_ohlcv(trend="up")

    detect_regime(
        tickers=["SPY", "QQQ"],
        fetch_fn=counting_fetch,
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
    )
    first_count = call_count

    time.sleep(0.01)

    detect_regime(
        tickers=["SPY", "QQQ"],
        fetch_fn=counting_fetch,
        cache_dir=tmp_path,
        cache_ttl_seconds=0,
    )
    # Should have fetched again since cache expired
    assert call_count > first_count
