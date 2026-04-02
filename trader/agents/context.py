from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_PROFILE_PATH = Path(".trader/profile.json")


class TimeSlot(Enum):
    PRE_MARKET = "pre-market"
    INTRADAY = "intraday"
    WEEKLY = "weekly"


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Portfolio profile not found: {p}")
    return json.loads(p.read_text())


def build_context(
    run_id: str,
    time_slot: TimeSlot,
    snapshot: dict[str, Any],
    recent_log: list[dict],
    profile_path: Path = DEFAULT_PROFILE_PATH,
    regime: str | None = None,
    cfg=None,
) -> dict[str, Any]:
    from trader.config import Config  # local import to avoid circular at module level
    if cfg is None:
        cfg = Config()

    profile = load_profile(profile_path)
    targets = profile.get("portfolio_targets", {})

    # Regime-aware cash floor: override target_cash_reserve_pct when defensive
    base_cash_floor = targets.get("target_cash_reserve_pct", 10) / 100
    if regime == "bear":
        effective_cash_floor = max(base_cash_floor, cfg.bear_cash_floor)
    elif regime == "caution":
        effective_cash_floor = max(base_cash_floor, cfg.caution_cash_floor)
    else:
        effective_cash_floor = base_cash_floor

    return {
        "run_id": run_id,
        "time_slot": time_slot.value,
        "snapshot": snapshot,
        "recent_log": recent_log,
        "profile": profile,
        "market_regime": regime or "bull",
        "guardrails": {
            "cash_only": not profile.get("asset_classes", {}).get("leverage", False),
            "max_single_position_pct": targets.get("max_single_position_pct", 10) / 100,
            "max_new_positions_per_day": targets.get("max_new_positions_per_day", 3),
            "target_cash_reserve_pct": effective_cash_floor,
            "min_consensus_for_longs": 4 if regime == "bear" else 3 if regime == "caution" else 2,
            "require_positive_sentiment_for_longs": regime == "bear",
            "position_sizing_pct": 30 if regime == "bear" else 50 if regime == "caution" else 100,
            "atr_stop_multiplier": 1.0 if regime == "bear" else 1.5 if regime == "caution" else 2.0,
        },
    }
