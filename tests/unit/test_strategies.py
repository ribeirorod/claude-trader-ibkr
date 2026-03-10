import pandas as pd
import numpy as np
import pytest
from trader.strategies.rsi import RSIStrategy

def make_ohlcv(n=100) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close * 0.99, "high": close * 1.01,
        "low": close * 0.98, "close": close, "volume": 1000000,
    })

def test_rsi_signals_shape():
    strat = RSIStrategy({"period": 14, "oversold": 30, "overbought": 70})
    df = make_ohlcv()
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})

def test_rsi_default_params():
    strat = RSIStrategy()
    params = strat.default_params()
    assert "period" in params
    assert "oversold" in params
    assert "overbought" in params

def test_rsi_signals_not_all_zero():
    strat = RSIStrategy()
    df = make_ohlcv(200)
    signals = strat.signals(df)
    assert signals.abs().sum() > 0

from trader.strategies.macd import MACDStrategy
from trader.strategies.ma_cross import MACrossStrategy

def test_macd_signals_shape():
    strat = MACDStrategy()
    df = make_ohlcv(200)
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})

def test_ma_cross_signals_shape():
    strat = MACrossStrategy()
    df = make_ohlcv(200)
    signals = strat.signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()).issubset({-1, 0, 1})
