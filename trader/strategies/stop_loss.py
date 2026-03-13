from __future__ import annotations
import pandas as pd

def atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range over `period` bars."""
    high = ohlcv["high"]
    low = ohlcv["low"]
    prev_close = ohlcv["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def stop_level(
    ohlcv: pd.DataFrame,
    entry_price: float,
    atr_multiplier: float = 2.0,
    period: int = 14,
) -> float:
    """Return the long stop-loss price: entry - (multiplier × ATR)."""
    current_atr = atr(ohlcv, period).iloc[-1]
    return max(0.01, entry_price - atr_multiplier * current_atr)

def position_size(
    ohlcv: pd.DataFrame,
    entry_price: float,
    account_value: float,
    risk_pct: float = 0.01,
    atr_multiplier: float = 2.0,
    period: int = 14,
) -> int:
    """Return share count where max loss equals risk_pct of account."""
    current_atr = atr(ohlcv, period).iloc[-1]
    risk_per_share = atr_multiplier * current_atr
    if risk_per_share <= 0:
        return 0
    dollar_risk = account_value * risk_pct
    shares = int(dollar_risk / risk_per_share)
    max_shares = int(account_value / entry_price) if entry_price > 0 else shares
    return max(1, min(shares, max_shares))
