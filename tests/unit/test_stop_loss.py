import pandas as pd
import numpy as np
import pytest
from trader.strategies.stop_loss import atr, stop_level, position_size

def make_ohlcv(n=50, seed=42) -> pd.DataFrame:
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    high = close * 1.01
    low = close * 0.99
    return pd.DataFrame({
        "open": close * 0.995, "high": high,
        "low": low, "close": close, "volume": 500_000,
    })

def test_atr_length():
    df = make_ohlcv()
    result = atr(df, period=14)
    assert len(result) == len(df)

def test_atr_all_positive():
    df = make_ohlcv()
    result = atr(df, period=14)
    assert (result.dropna() > 0).all()

def test_atr_first_n_are_nan():
    df = make_ohlcv()
    result = atr(df, period=14)
    # indices 0-12 (13 elements) are NaN; index 13 is the first valid value
    assert result.iloc[:13].isna().all()
    assert not pd.isna(result.iloc[13])  # period boundary: exactly 14 bars needed

def test_stop_level_below_entry():
    df = make_ohlcv()
    entry = df["close"].iloc[-1]
    sl = stop_level(df, entry_price=entry, atr_multiplier=2.0, period=14)
    assert sl < entry

def test_stop_level_respects_multiplier():
    df = make_ohlcv()
    entry = df["close"].iloc[-1]
    sl1 = stop_level(df, entry_price=entry, atr_multiplier=1.0, period=14)
    sl2 = stop_level(df, entry_price=entry, atr_multiplier=3.0, period=14)
    assert sl2 < sl1  # wider multiplier → lower stop

def test_position_size_respects_risk():
    df = make_ohlcv()
    entry = df["close"].iloc[-1]
    account_value = 100_000
    risk_pct = 0.01
    atr_multiplier = 2.0
    size = position_size(
        df, entry_price=entry,
        account_value=account_value, risk_pct=risk_pct,
        atr_multiplier=atr_multiplier, period=14,
    )
    assert isinstance(size, int)
    assert size > 0
    # verify the risk-dollar contract: size * risk_per_share ≈ dollar_risk
    from trader.strategies.stop_loss import atr as compute_atr
    current_atr = float(compute_atr(df, period=14).iloc[-1])
    risk_per_share = atr_multiplier * current_atr
    dollar_risk = account_value * risk_pct
    # Allow ±1 share of rounding tolerance
    expected = int(dollar_risk / risk_per_share)
    assert abs(size - expected) <= 1

def test_position_size_larger_account_more_shares():
    df = make_ohlcv()
    entry = df["close"].iloc[-1]
    s1 = position_size(df, entry, account_value=50_000, risk_pct=0.01, atr_multiplier=2.0)
    s2 = position_size(df, entry, account_value=200_000, risk_pct=0.01, atr_multiplier=2.0)
    assert s2 > s1


from trader.strategies.stop_loss import regime_atr_multiplier

def test_bull_multiplier_is_2():
    assert regime_atr_multiplier("bull") == 2.0

def test_caution_multiplier_is_1_5():
    assert regime_atr_multiplier("caution") == 1.5

def test_bear_multiplier_is_1():
    assert regime_atr_multiplier("bear") == 1.0

def test_unknown_regime_defaults_to_bull():
    assert regime_atr_multiplier("unknown") == 2.0
