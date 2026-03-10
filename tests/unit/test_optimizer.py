import numpy as np
import pandas as pd
from trader.strategies.optimizer import Optimizer
from trader.strategies.rsi import RSIStrategy

def make_ohlcv(n=200):
    np.random.seed(0)
    c = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({"open": c, "high": c*1.01, "low": c*0.99, "close": c, "volume": 1000000})

def test_optimizer_returns_best_params():
    opt = Optimizer()
    df = make_ohlcv()
    best = opt.grid_search(RSIStrategy, df, {"period": [7, 14], "oversold": [25, 30], "overbought": [70, 75]})
    assert "period" in best
    assert best["period"] in [7, 14]
