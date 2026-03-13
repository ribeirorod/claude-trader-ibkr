import pytest
from unittest.mock import patch
from trader.fundamentals.screener import FundamentalScreener

def _mock_info(pe=15.0, eps_growth=0.20, rev_growth=0.15):
    return {
        "trailingPE": pe,
        "earningsGrowth": eps_growth,
        "revenueGrowth": rev_growth,
    }

def test_passes_healthy_stock():
    screener = FundamentalScreener()
    with patch.object(screener, "_fetch_info", return_value=_mock_info(pe=20, eps_growth=0.15)):
        result = screener.check("AAPL")
    assert result["pass"] is True
    assert result["veto_reason"] is None

def test_vetoes_extreme_pe():
    screener = FundamentalScreener()
    with patch.object(screener, "_fetch_info", return_value=_mock_info(pe=250)):
        result = screener.check("XYZ", max_pe=100)
    assert result["pass"] is False
    assert result["veto_reason"] == "pe_too_high"

def test_vetoes_declining_earnings():
    screener = FundamentalScreener()
    with patch.object(screener, "_fetch_info", return_value=_mock_info(eps_growth=-0.25)):
        result = screener.check("XYZ", min_eps_growth=-0.10)
    assert result["pass"] is False
    assert result["veto_reason"] == "earnings_declining"

def test_passes_when_pe_missing():
    """ETFs have no P/E — should not veto."""
    screener = FundamentalScreener()
    with patch.object(screener, "_fetch_info", return_value={}):
        result = screener.check("CSPX", max_pe=100)
    assert result["pass"] is True

def test_passes_when_eps_growth_missing():
    screener = FundamentalScreener()
    with patch.object(screener, "_fetch_info", return_value={"trailingPE": 18.0}):
        result = screener.check("AAPL", min_eps_growth=-0.10)
    assert result["pass"] is True

def test_returns_raw_fundamentals():
    screener = FundamentalScreener()
    info = _mock_info(pe=18.0, eps_growth=0.12)
    with patch.object(screener, "_fetch_info", return_value=info):
        result = screener.check("AAPL")
    assert "pe" in result
    assert "eps_growth" in result
    assert result["pe"] == 18.0
