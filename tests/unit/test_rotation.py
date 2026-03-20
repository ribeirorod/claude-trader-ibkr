from __future__ import annotations
from trader.market.regime import MarketRegime
from trader.market.rotation import build_rotation_actions

PROFILE = {
    "bear_market": {
        "inverse_etf_basket": [
            {"ticker": "SH",   "description": "1x inverse S&P 500"},
            {"ticker": "PSQ",  "description": "1x inverse Nasdaq"},
        ],
        "defensive_sectors": ["GLD", "XLU", "XLP", "TLT"],
        "max_inverse_pct": 0.20,
    }
}

PROFILE_NO_BEAR = {}


def test_bear_regime_returns_inverse_and_defensive():
    actions = build_rotation_actions(MarketRegime.BEAR, PROFILE)
    tickers = [a["ticker"] for a in actions]
    assert "SH" in tickers
    assert "PSQ" in tickers
    assert "GLD" in tickers


def test_bear_regime_all_actions_have_required_keys():
    actions = build_rotation_actions(MarketRegime.BEAR, PROFILE)
    for a in actions:
        assert "action" in a
        assert "ticker" in a
        assert "reason" in a


def test_caution_regime_returns_only_defensive_no_inverse():
    actions = build_rotation_actions(MarketRegime.CAUTION, PROFILE)
    tickers = [a["ticker"] for a in actions]
    assert "SH" not in tickers
    assert "PSQ" not in tickers
    assert len(actions) > 0


def test_bull_regime_returns_empty():
    actions = build_rotation_actions(MarketRegime.BULL, PROFILE)
    assert actions == []


def test_missing_bear_market_section_returns_empty():
    actions = build_rotation_actions(MarketRegime.BEAR, PROFILE_NO_BEAR)
    assert actions == []
