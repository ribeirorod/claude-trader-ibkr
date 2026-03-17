import pandas as pd
import numpy as np
import pytest
from trader.strategies.momentum import MomentumStrategy

def make_ohlcv(n=100, trend=0.5, seed=1) -> pd.DataFrame:
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5 + trend)
    return pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": 1_000_000,
    })

def test_momentum_signals_shape():
    strat = MomentumStrategy()
    df = make_ohlcv(100)
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})

def test_momentum_default_params():
    strat = MomentumStrategy()
    p = strat.default_params()
    assert "window" in p
    assert "threshold" in p

def test_momentum_buy_on_strong_uptrend():
    """Strong uptrend should produce at least one buy signal."""
    strat = MomentumStrategy({"window": 10, "threshold": 0.01})
    df = make_ohlcv(100, trend=1.0)  # strong uptrend
    signals = strat.signals(df)
    assert (signals == 1).any()

def test_momentum_sell_on_strong_downtrend():
    """Strong downtrend should produce at least one sell signal."""
    strat = MomentumStrategy({"window": 10, "threshold": 0.01})
    df = make_ohlcv(100, trend=-1.0)  # downtrend
    signals = strat.signals(df)
    assert (signals == -1).any()

def test_momentum_no_signal_on_flat():
    """Flat market below threshold should produce no signals."""
    np.random.seed(99)
    # noise amplitude 0.0001 → max 10-period ROC ≈ 0.00002, well below threshold=0.10
    close = np.full(100, 100.0) + np.random.randn(100) * 0.0001
    df = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close, "volume": 1_000_000
    })
    strat = MomentumStrategy({"window": 10, "threshold": 0.10})
    signals = strat.signals(df)
    assert (signals == 0).all()

def test_momentum_with_benchmark():
    """Stock beating benchmark → buy; underperforming → sell."""
    strat = MomentumStrategy({"window": 10, "threshold": 0.01})
    stock = make_ohlcv(100, trend=1.5)
    bench = make_ohlcv(100, trend=0.1, seed=5)
    signals = strat.signals(stock, benchmark=bench)
    assert (signals == 1).any()

def test_momentum_registered_in_factory():
    from trader.strategies.factory import get_strategy
    strat = get_strategy("momentum")
    assert isinstance(strat, MomentumStrategy)

def test_momentum_benchmark_suppresses_weak_stock():
    """Stock with positive ROC but weaker than benchmark → no buys fired."""
    strat = MomentumStrategy({"window": 10, "threshold": 0.01})
    # Weak stock: gentle uptrend
    weak_stock = make_ohlcv(100, trend=0.2, seed=7)
    # Very strong benchmark: aggressive uptrend → bench_roc > stock_roc
    strong_bench = make_ohlcv(100, trend=3.0, seed=8)
    signals = strat.signals(weak_stock, benchmark=strong_bench)
    # Stock ROC barely exceeds threshold but benchmark ROC >> stock ROC → buy suppressed
    assert (signals == 1).sum() == 0
