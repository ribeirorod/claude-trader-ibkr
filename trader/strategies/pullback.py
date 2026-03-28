"""Pullback strategy — multi-factor pullback detector for both directions.

Detects pullbacks within established trends and emits directional signals:
  +1 = bullish pullback (buy the dip in an uptrend)
  -1 = bearish pullback (short via puts in a downtrend)
   0 = no actionable setup

Two phases: (1) define the trend regime, (2) detect the pullback within it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader.strategies.base import BaseStrategy
from trader.strategies.stop_loss import atr as compute_atr


class PullbackStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {
            # Trend regime
            "trend_ema": 200,
            # Intermediate momentum
            "fast_ema": 20,
            "slow_ema": 50,
            "cross_lookback": 5,
            # RSI divergence / exhaustion
            "rsi_period": 14,
            "divergence_lookback": 10,
            "rsi_overbought_in_downtrend": 60,
            "rsi_oversold_in_uptrend": 40,
            # Volume dry-up
            "vol_ma": 20,
            "vol_decline_pct": 0.7,
            # ATR expansion
            "atr_period": 14,
            "atr_ma": 20,
            "atr_expansion": 1.5,
            # Minimum factors required to trigger (out of 4 confirmation factors)
            "min_factors": 3,
        }

    def signals(self, ohlcv: pd.DataFrame, **kwargs) -> pd.Series:
        p = self._params
        close = ohlcv["close"]
        volume = ohlcv["volume"]

        # --- Trend regime (EMA 200) ---
        ema_trend = close.ewm(span=p["trend_ema"], min_periods=p["trend_ema"]).mean()
        bearish_regime = close < ema_trend
        bullish_regime = close > ema_trend

        # --- EMA cross (fast/slow) ---
        ema_fast = close.ewm(span=p["fast_ema"], min_periods=p["fast_ema"]).mean()
        ema_slow = close.ewm(span=p["slow_ema"], min_periods=p["slow_ema"]).mean()
        bearish_cross = _recent_cross_below(ema_fast, ema_slow, p["cross_lookback"])
        bullish_cross = _recent_cross_above(ema_fast, ema_slow, p["cross_lookback"])

        # --- RSI ---
        rsi = _rsi(close, p["rsi_period"])
        bearish_divergence = _bearish_divergence(close, rsi, p["divergence_lookback"])
        bullish_divergence = _bullish_divergence(close, rsi, p["divergence_lookback"])
        rsi_exhaustion_bear = rsi > p["rsi_overbought_in_downtrend"]
        rsi_exhaustion_bull = rsi < p["rsi_oversold_in_uptrend"]

        # --- Volume dry-up ---
        vol_ma = volume.rolling(p["vol_ma"]).mean()
        weak_volume = volume < (vol_ma * p["vol_decline_pct"])

        # --- ATR expansion ---
        current_atr = compute_atr(ohlcv, p["atr_period"])
        atr_avg = current_atr.rolling(p["atr_ma"]).mean()
        atr_expanding = current_atr > (atr_avg * p["atr_expansion"])

        # --- Composite scoring ---
        # 4 confirmation factors per direction (regime is a gate, not a factor)
        bear_factors = (
            bearish_cross.astype(int)
            + (bearish_divergence | rsi_exhaustion_bear).astype(int)
            + weak_volume.astype(int)
            + atr_expanding.astype(int)
        )
        bull_factors = (
            bullish_cross.astype(int)
            + (bullish_divergence | rsi_exhaustion_bull).astype(int)
            + weak_volume.astype(int)
            + atr_expanding.astype(int)
        )

        signals = pd.Series(0, index=ohlcv.index)
        signals[bearish_regime & (bear_factors >= p["min_factors"])] = -1
        signals[bullish_regime & (bull_factors >= p["min_factors"])] = 1

        # Where both trigger (rare, boundary), prefer the regime direction
        return signals.fillna(0).astype(int)


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------

def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _recent_cross_below(fast: pd.Series, slow: pd.Series, lookback: int) -> pd.Series:
    """True if fast crossed below slow within the last `lookback` bars."""
    cross = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    return cross.rolling(lookback, min_periods=1).max().astype(bool)


def _recent_cross_above(fast: pd.Series, slow: pd.Series, lookback: int) -> pd.Series:
    """True if fast crossed above slow within the last `lookback` bars."""
    cross = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    return cross.rolling(lookback, min_periods=1).max().astype(bool)


def _swing_highs(series: pd.Series, lookback: int) -> list[tuple[int, float]]:
    """Find local maxima (swing highs) in a series over a window."""
    highs = []
    values = series.values
    for i in range(lookback, len(values) - 1):
        window = values[max(0, i - lookback):i + lookback + 1]
        if not np.isnan(values[i]) and values[i] == np.nanmax(window):
            highs.append((i, values[i]))
    return highs


def _swing_lows(series: pd.Series, lookback: int) -> list[tuple[int, float]]:
    """Find local minima (swing lows) in a series over a window."""
    lows = []
    values = series.values
    for i in range(lookback, len(values) - 1):
        window = values[max(0, i - lookback):i + lookback + 1]
        if not np.isnan(values[i]) and values[i] == np.nanmin(window):
            lows.append((i, values[i]))
    return lows


def _bearish_divergence(close: pd.Series, rsi: pd.Series, lookback: int) -> pd.Series:
    """Price makes higher high but RSI makes lower high → bearish divergence."""
    result = pd.Series(False, index=close.index)
    price_highs = _swing_highs(close, lookback)
    rsi_highs = _swing_highs(rsi, lookback)
    if len(price_highs) < 2 or len(rsi_highs) < 2:
        return result
    # Compare last two swing highs
    for i in range(1, len(price_highs)):
        prev_p = price_highs[i - 1]
        curr_p = price_highs[i]
        # Find matching RSI highs near those indices
        prev_r = _nearest(rsi_highs, prev_p[0], lookback)
        curr_r = _nearest(rsi_highs, curr_p[0], lookback)
        if prev_r and curr_r:
            if curr_p[1] > prev_p[1] and curr_r[1] < prev_r[1]:
                # Mark from current swing high onward for lookback bars
                start = curr_p[0]
                end = min(start + lookback, len(close))
                result.iloc[start:end] = True
    return result


def _bullish_divergence(close: pd.Series, rsi: pd.Series, lookback: int) -> pd.Series:
    """Price makes lower low but RSI makes higher low → bullish divergence."""
    result = pd.Series(False, index=close.index)
    price_lows = _swing_lows(close, lookback)
    rsi_lows = _swing_lows(rsi, lookback)
    if len(price_lows) < 2 or len(rsi_lows) < 2:
        return result
    for i in range(1, len(price_lows)):
        prev_p = price_lows[i - 1]
        curr_p = price_lows[i]
        prev_r = _nearest(rsi_lows, prev_p[0], lookback)
        curr_r = _nearest(rsi_lows, curr_p[0], lookback)
        if prev_r and curr_r:
            if curr_p[1] < prev_p[1] and curr_r[1] > prev_r[1]:
                start = curr_p[0]
                end = min(start + lookback, len(close))
                result.iloc[start:end] = True
    return result


def _nearest(
    points: list[tuple[int, float]], target_idx: int, max_dist: int
) -> tuple[int, float] | None:
    """Find the point closest to target_idx within max_dist."""
    best = None
    best_dist = max_dist + 1
    for idx, val in points:
        dist = abs(idx - target_idx)
        if dist < best_dist:
            best = (idx, val)
            best_dist = dist
    return best if best_dist <= max_dist else None
