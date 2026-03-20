from __future__ import annotations
import pandas as pd
import numpy as np
from trader.market.regime import MarketRegime, detect_regime


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
