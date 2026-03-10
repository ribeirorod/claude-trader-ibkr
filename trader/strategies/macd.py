import pandas as pd
from trader.strategies.base import BaseStrategy

class MACDStrategy(BaseStrategy):
    def default_params(self) -> dict:
        return {"fast": 12, "slow": 26, "signal": 9}

    def signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        ema_fast = close.ewm(span=self._params["fast"], adjust=False).mean()
        ema_slow = close.ewm(span=self._params["slow"], adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self._params["signal"], adjust=False).mean()

        prev_macd = macd_line.shift(1)
        prev_signal = signal_line.shift(1)

        signals = pd.Series(0, index=ohlcv.index)
        signals[(macd_line > signal_line) & (prev_macd <= prev_signal)] = 1
        signals[(macd_line < signal_line) & (prev_macd >= prev_signal)] = -1
        return signals.fillna(0).astype(int)
