from __future__ import annotations
import pandas as pd
from trader.strategies.base import BaseStrategy

class RSIStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"period": 14, "oversold": 30, "overbought": 70}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        period = self._params["period"]
        oversold = self._params["oversold"]
        overbought = self._params["overbought"]

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = 100 - (100 / (1 + rs))

        signals = pd.Series(0, index=ohlcv.index)
        signals[rsi < oversold] = 1
        signals[rsi > overbought] = -1
        return signals.fillna(0).astype(int)
