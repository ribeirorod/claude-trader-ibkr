"""Tests for PullbackStrategy and OptionsSelector."""
import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta

from trader.strategies.pullback import PullbackStrategy
from trader.strategies.options_selector import select_contract, OptionsRecommendation
from trader.models.quote import OptionChain, OptionContract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n=300, seed=42, trend="down"):
    """Generate synthetic OHLCV data with a trend plus realistic pullbacks.

    The key is to have a dominant trend (for EMA200 regime) but with counter-
    trend bounces that create EMA20/50 crosses and volume/RSI divergence.
    """
    np.random.seed(seed)
    noise = np.random.randn(n) * 1.5

    if trend == "down":
        # Downtrend with periodic relief rallies (pullback bounces)
        drift = np.linspace(0, -80, n)
        # Add 3 rally bounces of ~15 points each
        bounce = np.zeros(n)
        for start in [210, 240, 265]:
            if start + 15 < n:
                bounce[start:start + 15] += np.linspace(0, 12, 15)
                if start + 30 < n:
                    bounce[start + 15:start + 30] += np.linspace(12, 0, 15)
        close = 200 + drift + bounce + np.cumsum(noise) * 0.3
    elif trend == "up":
        # Uptrend with periodic dips (pullback dips)
        drift = np.linspace(0, 80, n)
        dip = np.zeros(n)
        for start in [210, 240, 265]:
            if start + 15 < n:
                dip[start:start + 15] -= np.linspace(0, 12, 15)
                if start + 30 < n:
                    dip[start + 15:start + 30] -= np.linspace(12, 0, 15)
        close = 50 + drift + dip + np.cumsum(noise) * 0.3
    else:
        close = 100 + np.cumsum(noise * 0.3)

    close = np.maximum(close, 1.0)

    # Volume: generally declining during pullback bounces/dips (weak volume)
    base_vol = np.random.randint(800_000, 2_000_000, size=n).astype(float)
    # Reduce volume during bounce/dip periods to trigger vol_decline factor
    for start in [210, 240, 265]:
        end = min(start + 30, n)
        base_vol[start:end] *= 0.4

    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "open": close * 0.995,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": base_vol,
    }, index=idx)


def _make_chain(current_price: float, right: str = "put", n_strikes: int = 10):
    """Generate a synthetic option chain around current_price."""
    expiry = (date.today() + timedelta(days=35)).strftime("%Y-%m-%d")
    contracts = []
    for i in range(n_strikes):
        strike = round(current_price - 15 + i * 3, 2)
        distance = abs(strike - current_price)
        delta = -0.5 + distance * 0.02 if right == "put" else 0.5 - distance * 0.02
        contracts.append(OptionContract(
            strike=strike,
            right=right,
            expiry=expiry,
            bid=round(max(0.5, 5 - distance * 0.3), 2),
            ask=round(max(0.7, 5.5 - distance * 0.3), 2),
            last=round(max(0.6, 5.2 - distance * 0.3), 2),
            delta=round(delta, 3),
            implied_vol=0.30,
            open_interest=1000,
        ))
    return OptionChain(ticker="TEST", expiry=expiry, contracts=contracts)


# ---------------------------------------------------------------------------
# PullbackStrategy tests
# ---------------------------------------------------------------------------

class TestPullbackStrategy:
    def test_signals_shape_and_values(self):
        strat = PullbackStrategy()
        df = _make_ohlcv(300)
        signals = strat.signals(df)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

    def test_default_params_present(self):
        strat = PullbackStrategy()
        p = strat.default_params()
        assert "trend_ema" in p
        assert "fast_ema" in p
        assert "rsi_period" in p
        assert "vol_decline_pct" in p
        assert "atr_expansion" in p
        assert "min_factors" in p

    def test_custom_params_override(self):
        strat = PullbackStrategy({"min_factors": 2, "cross_lookback": 8})
        assert strat.params["min_factors"] == 2
        assert strat.params["cross_lookback"] == 8
        # Defaults still present
        assert strat.params["trend_ema"] == 200

    def test_downtrend_can_produce_short_signals(self):
        """In a persistent downtrend, strategy should eventually emit -1."""
        strat = PullbackStrategy({"min_factors": 2})
        df = _make_ohlcv(300, trend="down")
        signals = strat.signals(df)
        assert -1 in signals.values, "Expected at least one short signal in downtrend"

    def test_uptrend_can_produce_long_signals(self):
        """In a persistent uptrend, strategy should eventually emit +1."""
        strat = PullbackStrategy({"min_factors": 2})
        df = _make_ohlcv(300, trend="up")
        signals = strat.signals(df)
        assert 1 in signals.values, "Expected at least one long signal in uptrend"

    def test_sideways_mostly_neutral(self):
        """In a sideways market, signals should be mostly 0."""
        strat = PullbackStrategy({"min_factors": 4})
        df = _make_ohlcv(300, trend="flat")
        signals = strat.signals(df)
        # Most should be neutral
        neutral_pct = (signals == 0).mean()
        assert neutral_pct > 0.7, f"Expected >70% neutral in flat market, got {neutral_pct:.1%}"

    def test_short_dataframe_returns_all_zero(self):
        """Too few bars for EMA200 → all signals should be 0."""
        strat = PullbackStrategy()
        df = _make_ohlcv(50, trend="down")
        signals = strat.signals(df)
        assert (signals == 0).all()

    def test_registered_in_factory(self):
        from trader.strategies.factory import get_strategy, list_strategies
        assert "pullback" in list_strategies()
        strat = get_strategy("pullback")
        assert isinstance(strat, PullbackStrategy)


# ---------------------------------------------------------------------------
# OptionsSelector tests
# ---------------------------------------------------------------------------

class TestOptionsSelector:
    def test_neutral_signal_returns_no_action(self):
        chain = _make_chain(100.0)
        rec = select_contract(
            signal=0, current_price=100.0, current_atr=3.0,
            chain=chain, account_value=100_000,
        )
        assert rec.action == "no_action"
        assert rec.contract is None
        assert rec.suggested_qty == 0

    def test_short_signal_recommends_put(self):
        chain = _make_chain(100.0, right="put")
        rec = select_contract(
            signal=-1, current_price=100.0, current_atr=3.0,
            chain=chain, account_value=100_000,
        )
        assert rec.action == "buy_put"
        assert rec.contract is not None
        assert rec.contract.right == "put"
        assert rec.suggested_qty >= 1

    def test_long_signal_recommends_call(self):
        chain = _make_chain(100.0, right="call")
        rec = select_contract(
            signal=1, current_price=100.0, current_atr=3.0,
            chain=chain, account_value=100_000,
        )
        assert rec.action == "buy_call"
        assert rec.contract is not None
        assert rec.contract.right == "call"
        assert rec.suggested_qty >= 1

    def test_strike_near_atr_target(self):
        chain = _make_chain(100.0, right="put")
        rec = select_contract(
            signal=-1, current_price=100.0, current_atr=5.0,
            chain=chain, account_value=100_000,
        )
        if rec.contract:
            target = 100.0 - 5.0  # 95
            assert abs(rec.contract.strike - target) <= 6, \
                f"Strike {rec.contract.strike} too far from target {target}"

    def test_max_risk_respects_account_pct(self):
        chain = _make_chain(100.0, right="put")
        rec = select_contract(
            signal=-1, current_price=100.0, current_atr=3.0,
            chain=chain, account_value=50_000, risk_pct=0.01,
        )
        if rec.contract and rec.max_risk > 0:
            assert rec.max_risk <= 50_000 * 0.01 + 500, \
                f"Max risk ${rec.max_risk} exceeds 1% of $50k + 1 contract tolerance"

    def test_empty_chain_returns_no_contract(self):
        chain = OptionChain(ticker="TEST", expiry="2026-04-17", contracts=[])
        rec = select_contract(
            signal=-1, current_price=100.0, current_atr=3.0,
            chain=chain, account_value=100_000,
        )
        assert rec.contract is None
        assert rec.suggested_qty == 0

    def test_no_matching_dte_returns_no_contract(self):
        """Contracts with DTE outside window should be filtered out."""
        # Expiry too far out (200 days)
        far_expiry = (date.today() + timedelta(days=200)).strftime("%Y-%m-%d")
        chain = OptionChain(
            ticker="TEST", expiry=far_expiry,
            contracts=[OptionContract(
                strike=95, right="put", expiry=far_expiry,
                bid=2.0, ask=2.5, delta=-0.35,
            )],
        )
        rec = select_contract(
            signal=-1, current_price=100.0, current_atr=3.0,
            chain=chain, account_value=100_000,
        )
        assert rec.contract is None


# ---------------------------------------------------------------------------
# RiskFilter short-signal tests
# ---------------------------------------------------------------------------

class TestRiskFilterShortSignals:
    def test_short_passes_with_no_sentiment(self):
        from trader.strategies.risk_filter import RiskFilter
        rf = RiskFilter()
        result = rf.filter(signal=-1, quote=None, position=None, sentiment=None)
        assert result["signal"] == -1
        assert result["filtered"] is False

    def test_short_suppressed_on_bullish_sentiment(self):
        from trader.strategies.risk_filter import RiskFilter
        from trader.models import SentimentResult
        rf = RiskFilter()
        bullish = SentimentResult(
            ticker="SPY", score=0.5, signal="bullish",
            article_count=5, lookback_hours=24, top_headlines=[],
        )
        result = rf.filter(signal=-1, quote=None, position=None, sentiment=bullish)
        assert result["signal"] == 0
        assert result["filter_reason"] == "sentiment_bullish"

    def test_short_passes_on_bearish_sentiment(self):
        from trader.strategies.risk_filter import RiskFilter
        from trader.models import SentimentResult
        rf = RiskFilter()
        bearish = SentimentResult(
            ticker="SPY", score=-0.5, signal="bearish",
            article_count=5, lookback_hours=24, top_headlines=[],
        )
        result = rf.filter(signal=-1, quote=None, position=None, sentiment=bearish)
        assert result["signal"] == -1
        assert result["filtered"] is False

    def test_short_suppressed_in_earnings_blackout(self):
        from unittest.mock import MagicMock
        from trader.strategies.risk_filter import RiskFilter
        rf = RiskFilter()
        mock_ecal = MagicMock()
        mock_ecal.is_in_blackout.return_value = True
        result = rf.filter(
            signal=-1, quote=None, position=None, sentiment=None,
            earnings_calendar=mock_ecal, ticker="AAPL",
        )
        assert result["signal"] == 0
        assert result["filter_reason"] == "earnings_blackout"
