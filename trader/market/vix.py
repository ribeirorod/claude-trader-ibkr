from __future__ import annotations

import logging
from typing import Callable

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_vix(period: str = "30d") -> pd.DataFrame:
    """Download ^VIX data from yfinance."""
    df = yf.download("^VIX", period=period, progress=False)
    if df.empty:
        return df
    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def vix_gate(
    threshold: float = 30.0,
    cooldown_days: int = 5,
    fetch_fn: Callable | None = None,
) -> dict:
    """Check if VIX conditions block new long entries.

    Returns dict with: blocked, vix_current, vix_peak, days_since_peak, reason.
    Fails open (blocked=False) if data unavailable.
    """
    default = {"blocked": False, "vix_current": 0.0, "vix_peak": 0.0, "days_since_peak": 0, "reason": None}
    try:
        df = (fetch_fn or fetch_vix)()
        if df.empty or len(df) < 2:
            return default

        current_vix = float(df["Close"].iloc[-1])
        default["vix_current"] = current_vix

        if current_vix <= threshold:
            return default

        # Find peak in recent window
        window = df["Close"].iloc[-cooldown_days:] if len(df) >= cooldown_days else df["Close"]
        peak_idx = window.idxmax()
        peak_val = float(window.max())
        days_since = (df.index[-1] - peak_idx).days

        default["vix_peak"] = peak_val
        default["days_since_peak"] = days_since

        # If VIX declining for 2+ days from peak, mean-reversion underway — allow longs
        if len(df) >= 3:
            last3 = df["Close"].iloc[-3:].values
            if last3[-1] < last3[-2] < last3[-3]:
                default["reason"] = f"VIX {current_vix:.1f} elevated but declining (mean-reversion)"
                return default

        # VIX still elevated and not declining — block new longs
        default["blocked"] = True
        default["reason"] = f"VIX {current_vix:.1f} > {threshold}, {days_since}d since peak {peak_val:.1f}. Wait for cooldown."
        return default

    except Exception as exc:
        logger.warning("VIX gate failed, allowing trades: %s", exc)
        return default
