import pandas as pd
from trader.strategies.base import BaseStrategy

class MACrossStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"fast_window": 20, "slow_window": 50}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        fast = close.rolling(self._params["fast_window"]).mean()
        slow = close.rolling(self._params["slow_window"]).mean()

        prev_fast = fast.shift(1)
        prev_slow = slow.shift(1)

        signals = pd.Series(0, index=ohlcv.index)
        signals[(fast > slow) & (prev_fast <= prev_slow)] = 1
        signals[(fast < slow) & (prev_fast >= prev_slow)] = -1
        return signals.fillna(0).astype(int)
