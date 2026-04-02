"""Tests for sector-aware strategy parameter loading."""
import json
import pytest
from pathlib import Path
from trader.strategies.factory import (
    get_strategy, get_sector_params, _load_sector_params, _SECTOR_PARAMS_FILE,
    get_regime_thresholds,
)
from trader.strategies.rsi import RSIStrategy
from trader.strategies.macd import MACDStrategy
from trader.models.scan import ScanResult
from trader.models.quote import Quote


# ── Model tests ──────────────────────────────────────────────────────────────

def test_scan_result_has_sector_fields():
    r = ScanResult(symbol="NVDA", sector="Technology", industry="Semiconductors")
    assert r.sector == "Technology"
    assert r.industry == "Semiconductors"

def test_scan_result_sector_defaults_empty():
    r = ScanResult(symbol="AAPL")
    assert r.sector == ""
    assert r.industry == ""

def test_quote_has_sector_fields():
    q = Quote(ticker="NVDA", sector="Technology", industry="Semiconductors")
    assert q.sector == "Technology"
    assert q.industry == "Semiconductors"

def test_quote_sector_defaults_empty():
    q = Quote(ticker="AAPL")
    assert q.sector == ""
    assert q.industry == ""


# ── Sector params file ──────────────────────────────────────────────────────

def test_sector_params_file_exists():
    assert _SECTOR_PARAMS_FILE.exists(), "sector_params.json should exist"

def test_sector_params_file_valid_json():
    data = json.loads(_SECTOR_PARAMS_FILE.read_text())
    assert isinstance(data, dict)
    # Should have at least Technology and Energy
    assert "Technology" in data
    assert "Energy" in data

def test_sector_params_has_strategy_entries():
    data = json.loads(_SECTOR_PARAMS_FILE.read_text())
    tech = data["Technology"]
    assert "rsi" in tech
    assert "macd" in tech
    assert "oversold" in tech["rsi"]


# ── Factory: get_sector_params ───────────────────────────────────────────────

def test_get_sector_params_returns_overrides():
    import trader.strategies.factory as mod
    mod._sector_cache = None  # force reload
    params = get_sector_params("Technology", "rsi")
    assert params is not None
    assert "oversold" in params

def test_get_sector_params_case_insensitive():
    import trader.strategies.factory as mod
    mod._sector_cache = None
    p1 = get_sector_params("technology", "rsi")
    p2 = get_sector_params("TECHNOLOGY", "rsi")
    assert p1 == p2

def test_get_sector_params_unknown_sector():
    import trader.strategies.factory as mod
    mod._sector_cache = None
    assert get_sector_params("NonExistentSector", "rsi") is None

def test_get_sector_params_unknown_strategy():
    import trader.strategies.factory as mod
    mod._sector_cache = None
    assert get_sector_params("Technology", "unknown_strat") is None


# ── Factory: get_strategy with sector ────────────────────────────────────────

def test_get_strategy_with_sector_uses_overrides():
    import trader.strategies.factory as mod
    mod._sector_cache = None
    strat = get_strategy("rsi", sector="Technology")
    assert isinstance(strat, RSIStrategy)
    # Technology RSI should use oversold=25 (not default 30)
    assert strat.params["oversold"] == 25

def test_get_strategy_without_sector_uses_defaults():
    strat = get_strategy("rsi")
    assert isinstance(strat, RSIStrategy)
    assert strat.params["oversold"] == 30  # default

def test_get_strategy_explicit_params_override_sector():
    """Explicit params should always win over sector defaults."""
    import trader.strategies.factory as mod
    mod._sector_cache = None
    strat = get_strategy("rsi", params={"period": 7, "oversold": 20, "overbought": 80}, sector="Technology")
    assert strat.params["oversold"] == 20  # explicit wins
    assert strat.params["period"] == 7

def test_get_strategy_energy_rsi_params():
    import trader.strategies.factory as mod
    mod._sector_cache = None
    strat = get_strategy("rsi", sector="Energy")
    # Energy RSI uses period=21 (longer for trend-following)
    assert strat.params["period"] == 21

def test_get_strategy_utilities_tighter_bands():
    import trader.strategies.factory as mod
    mod._sector_cache = None
    strat = get_strategy("rsi", sector="Utilities")
    # Utilities uses tighter bands: oversold=35, overbought=65
    assert strat.params["oversold"] == 35
    assert strat.params["overbought"] == 65


# ── Sector params write-back (optimize --sector) ────────────────────────────

def test_sector_params_write_back(tmp_path, monkeypatch):
    """Simulates what optimize --sector does: writes best params back to file."""
    import trader.strategies.factory as mod

    # Create a temp sector_params.json
    sp = tmp_path / "sector_params.json"
    sp.write_text(json.dumps({"Technology": {"rsi": {"period": 14, "oversold": 30, "overbought": 70}}}))

    monkeypatch.setattr(mod, "_SECTOR_PARAMS_FILE", sp)
    monkeypatch.setattr(mod, "_sector_cache", None)

    # Simulate optimize writing back
    raw = json.loads(sp.read_text())
    raw["Technology"]["rsi"] = {"period": 21, "oversold": 25, "overbought": 75}
    sp.write_text(json.dumps(raw, indent=2))
    mod._sector_cache = None

    # Verify the updated params are loaded
    params = get_sector_params("Technology", "rsi")
    assert params["period"] == 21
    assert params["oversold"] == 25


# ── Regime thresholds ──────────────────────────────────────────────────────

def test_get_regime_thresholds_bear():
    import trader.strategies.factory as mod
    mod._regime_cache = None  # force reload
    thresholds = get_regime_thresholds("bear")
    assert thresholds == {"discovery": 3, "watchlist": 2}


def test_get_regime_thresholds_bull():
    import trader.strategies.factory as mod
    mod._regime_cache = None
    thresholds = get_regime_thresholds("bull")
    assert thresholds == {"discovery": 3, "watchlist": 2}


def test_get_regime_thresholds_caution():
    import trader.strategies.factory as mod
    mod._regime_cache = None
    thresholds = get_regime_thresholds("caution")
    assert thresholds == {"discovery": 3, "watchlist": 2}


def test_get_regime_thresholds_unknown_regime():
    import trader.strategies.factory as mod
    mod._regime_cache = None
    thresholds = get_regime_thresholds("unknown")
    assert thresholds is None


def test_get_regime_thresholds_case_insensitive():
    import trader.strategies.factory as mod
    mod._regime_cache = None
    t1 = get_regime_thresholds("bear")
    mod._regime_cache = None
    t2 = get_regime_thresholds("BEAR")
    assert t1 == t2
