from __future__ import annotations
from enum import Enum
from typing import Callable
import pandas as pd
import yfinance as yf


class MarketRegime(Enum):
    BULL = "bull"
    CAUTION = "caution"
    BEAR = "bear"


_FAST_WINDOW = 20
_SLOW_WINDOW = 50


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


def detect_regime(
    tickers: list[str] | None = None,
    lookback: str = "200d",
    fetch_fn: Callable | None = None,
) -> MarketRegime:
    """Detect broad market regime via 20/50-day MA state on reference tickers.

    Uses MA level comparison (state-based), not crossover events, so the
    result reflects the current trend regardless of when the last cross was.

    Returns BULL if all tickers bullish, BEAR if all bearish, else CAUTION.
    """
    if tickers is None:
        tickers = ["SPY", "QQQ"]
    if fetch_fn is None:
        fetch_fn = _default_fetch

    states: list[int] = []
    for ticker in tickers:
        ohlcv = fetch_fn(ticker, lookback, False)
        states.append(_ma_state(ohlcv))

    if all(s == 1 for s in states):
        return MarketRegime.BULL
    if all(s == -1 for s in states):
        return MarketRegime.BEAR
    return MarketRegime.CAUTION
