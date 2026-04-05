from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(".trader/inverse_etfs.json")

_TICKER_TO_INDEX: dict[str, str] = {
    "CSPX": "SP500", "VUSA": "SP500", "SPY": "SP500", "VOO": "SP500",
    "IVV": "SP500", "SWDA": "SP500",
    "EQQQ": "NASDAQ100", "QQQ": "NASDAQ100", "TQQQ": "NASDAQ100",
    "IMEU": "EUROSTOXX50",
    "ISF": "FTSE100", "VUKE": "FTSE100",
}


def load_inverse_map(path: Path | None = None) -> dict:
    p = path or _DEFAULT_PATH
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Could not load inverse ETF map from %s: %s", p, exc)
        return {}


def find_inverse(
    ticker: str,
    inverse_map: dict,
    *,
    sector: str | None = None,
) -> str | None:
    if not inverse_map:
        return None

    upper_ticker = ticker.upper()
    index_hedges = inverse_map.get("index_hedges", {})
    sector_hedges = inverse_map.get("sector_hedges", {})

    index_key = _TICKER_TO_INDEX.get(upper_ticker)
    if index_key and index_key in index_hedges:
        return index_hedges[index_key]["ticker"]

    if sector:
        sector_lower = sector.lower()
        if sector_lower in sector_hedges:
            return sector_hedges[sector_lower]["ticker"]

    return None
