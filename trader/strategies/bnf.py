"""BNF (price-action breakout) strategy."""
import pandas as pd
from trader.strategies.base import BaseStrategy

class BNFStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"lookback": 20, "breakout_pct": 0.02}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        lookback = self._params["lookback"]
        pct = self._params["breakout_pct"]

        rolling_high = high.rolling(lookback).max().shift(1)
        rolling_low = low.rolling(lookback).min().shift(1)

        signals = pd.Series(0, index=ohlcv.index)
        signals[close > rolling_high * (1 + pct)] = 1
        signals[close < rolling_low * (1 - pct)] = -1
        return signals.fillna(0).astype(int)
