from __future__ import annotations
import json
from pathlib import Path
from trader.strategies.rsi import RSIStrategy
from trader.strategies.macd import MACDStrategy
from trader.strategies.ma_cross import MACrossStrategy
from trader.strategies.bnf import BNFStrategy
from trader.strategies.momentum import MomentumStrategy
from trader.strategies.pullback import PullbackStrategy
from trader.strategies.base import BaseStrategy

_REGISTRY = {
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "ma_cross": MACrossStrategy,
    "bnf": BNFStrategy,
    "momentum": MomentumStrategy,
    "pullback": PullbackStrategy,
}

_SECTOR_PARAMS_FILE = Path(__file__).parent / "sector_params.json"
_sector_cache: dict | None = None

_REGIME_PARAMS_FILE = Path(__file__).parent / "regime_params.json"
_regime_cache: dict | None = None


def _load_sector_params() -> dict:
    global _sector_cache
    if _sector_cache is None:
        if _SECTOR_PARAMS_FILE.exists():
            raw = json.loads(_SECTOR_PARAMS_FILE.read_text())
            # Normalize keys to lowercase for case-insensitive lookup
            _sector_cache = {k.lower(): v for k, v in raw.items() if isinstance(v, dict)}
        else:
            _sector_cache = {}
    return _sector_cache


def _load_regime_params() -> dict:
    global _regime_cache
    if _regime_cache is None:
        if _REGIME_PARAMS_FILE.exists():
            raw = json.loads(_REGIME_PARAMS_FILE.read_text())
            # Normalize keys to lowercase for case-insensitive lookup
            _regime_cache = {k.lower(): v for k, v in raw.items() if isinstance(v, dict)}
        else:
            _regime_cache = {}
    return _regime_cache


def get_sector_params(sector: str, strategy_name: str) -> dict | None:
    """Return param overrides for a sector+strategy combo, or None if not configured."""
    sp = _load_sector_params()
    sector_entry = sp.get(sector.lower())
    if not sector_entry:
        return None
    return sector_entry.get(strategy_name.lower())


def get_regime_params(regime: str, strategy_name: str) -> dict | None:
    """Return param overrides for a regime+strategy combo, or None if not configured."""
    rp = _load_regime_params()
    regime_entry = rp.get(regime.lower())
    if not regime_entry:
        return None
    return regime_entry.get(strategy_name.lower())


def get_strategy(
    name: str,
    params: dict | None = None,
    sector: str | None = None,
    regime: str | None = None,
) -> BaseStrategy:
    """Create a strategy instance.

    If *sector* is provided and no explicit *params* override, sector-specific
    defaults are loaded from sector_params.json.  If *regime* is also provided,
    regime overrides are applied on top of sector defaults (regime wins).
    Explicit *params* always win over both sector and regime.
    """
    cls = _REGISTRY.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(_REGISTRY)}")
    if params:
        return cls(params)

    # Start with sector overrides (or empty)
    merged: dict = {}
    if sector:
        sector_overrides = get_sector_params(sector, name)
        if sector_overrides:
            merged.update(sector_overrides)

    # Regime overrides applied on top (wins over sector)
    if regime:
        regime_overrides = get_regime_params(regime, name)
        if regime_overrides:
            merged.update(regime_overrides)

    if merged:
        return cls(merged)
    return cls()


def list_strategies() -> list[str]:
    return list(_REGISTRY)
