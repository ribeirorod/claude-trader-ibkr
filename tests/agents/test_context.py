import json
from pathlib import Path
import pytest
from trader.agents.context import build_context, load_profile, TimeSlot


@pytest.fixture
def profile_file(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps({
        "risk_tolerance": "moderate",
        "preferred_sectors": ["energy", "semiconductors"],
        "portfolio_targets": {
            "max_single_position_pct": 10,
            "max_new_positions_per_day": 3,
            "target_cash_reserve_pct": 10,
        },
        "asset_classes": {"equities": True, "leverage": False},
    }))
    return p


def test_load_profile(profile_file):
    profile = load_profile(profile_file)
    assert profile["risk_tolerance"] == "moderate"
    assert "semiconductors" in profile["preferred_sectors"]


def test_load_profile_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "missing.json")


def test_build_context_structure(profile_file):
    ctx = build_context(
        run_id="abc123",
        time_slot=TimeSlot.PRE_MARKET,
        snapshot={"net_liquidation": 90000, "buying_power": 15000, "positions": [], "open_orders": []},
        recent_log=[],
        profile_path=profile_file,
    )
    assert ctx["run_id"] == "abc123"
    assert ctx["time_slot"] == "pre-market"
    assert ctx["snapshot"]["net_liquidation"] == 90000
    assert ctx["guardrails"]["cash_only"] is True
    assert ctx["guardrails"]["max_new_positions_per_day"] == 3
    assert ctx["profile"]["risk_tolerance"] == "moderate"


def test_guardrails_from_profile(profile_file):
    ctx = build_context(
        run_id="x",
        time_slot=TimeSlot.INTRADAY,
        snapshot={},
        recent_log=[],
        profile_path=profile_file,
    )
    assert ctx["guardrails"]["max_single_position_pct"] == 0.10
    assert ctx["guardrails"]["cash_only"] is True


def test_time_slot_values():
    assert TimeSlot.PRE_MARKET.value == "pre-market"
    assert TimeSlot.INTRADAY.value == "intraday"
    assert TimeSlot.WEEKLY.value == "weekly"
