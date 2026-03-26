import json
from unittest.mock import patch
from click.testing import CliRunner
import pandas as pd
import numpy as np
from trader.cli.__main__ import cli

def make_ohlcv(n=100):
    np.random.seed(0)
    c = 100 + np.cumsum(np.random.randn(n))
    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": c, "high": c*1.01, "low": c*0.99, "close": c, "volume": 100000}, index=idx)

def test_strategies_signals():
    runner = CliRunner()
    with patch("yfinance.download", return_value=make_ohlcv()):
        result = runner.invoke(cli, ["strategies", "signals", "--tickers", "AAPL", "--strategy", "rsi"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["ticker"] == "AAPL"
    assert "signal" in data[0]
    assert "filtered" in data[0]

def test_signals_output_contains_sentiment_fields():
    """signals output must include sentiment_velocity and sentiment_multiplier keys."""
    runner = CliRunner()
    with patch("yfinance.download", return_value=make_ohlcv()):
        result = runner.invoke(
            cli,
            ["strategies", "signals", "--tickers", "AAPL", "--strategy", "rsi"],
        )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert "sentiment_multiplier" in data[0]
    assert "sentiment_velocity" in data[0]
    assert "atr" in data[0]
    assert "stop_level" in data[0]

def test_signals_passes_regime_to_risk_filter():
    """The --regime bear flag should cause RiskFilter to block long signals."""
    from trader.strategies.risk_filter import RiskFilter

    # Create uptrending data that would normally produce a buy signal
    dates = pd.date_range("2026-01-01", periods=60, freq="B")
    close = np.linspace(100, 150, 60)
    df = pd.DataFrame({
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": np.random.randint(1000000, 5000000, 60),
    }, index=dates)

    captured_kwargs = {}
    original_filter = RiskFilter.filter
    def spy_filter(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_filter(self, *args, **kwargs)

    runner = CliRunner()
    with patch("trader.cli.strategies._fetch_ohlcv", return_value=df), \
         patch.object(RiskFilter, "filter", spy_filter):
        result = runner.invoke(cli, [
            "strategies", "signals",
            "--tickers", "AAPL",
            "--strategy", "rsi",
            "--regime", "bear",
        ])

    assert result.exit_code == 0, result.output
    assert captured_kwargs.get("regime") == "bear"
