from __future__ import annotations
import pandas as pd
from trader.strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    """
    Price Rate-of-Change momentum with optional relative-strength filter.

    Buy  when ROC(window) > threshold  AND (no benchmark OR stock ROC > bench ROC).
    Sell when ROC(window) < -threshold AND (no benchmark OR stock ROC < bench ROC).
    """

    def default_params(self) -> dict:
        return {"window": 20, "threshold": 0.03}

    def signals(
        self,
        ohlcv: pd.DataFrame,
        benchmark: pd.DataFrame | None = None,
        **kwargs,
    ) -> pd.Series:
        window = self._params["window"]
        threshold = self._params["threshold"]

        close = ohlcv["close"]
        roc = (close - close.shift(window)) / close.shift(window)

        if benchmark is not None:
            bench_close = benchmark["close"]
            bench_roc = (bench_close - bench_close.shift(window)) / bench_close.shift(window)
            bench_roc = bench_roc.reindex(roc.index, method="ffill")
        else:
            bench_roc = None

        signals = pd.Series(0, index=ohlcv.index)

        if bench_roc is not None:
            buy_mask = (roc > threshold) & (roc > bench_roc)
            sell_mask = (roc < -threshold) & (roc < bench_roc)
        else:
            buy_mask = roc > threshold
            sell_mask = roc < -threshold

        signals[buy_mask] = 1
        signals[sell_mask] = -1
        return signals.fillna(0).astype(int)
