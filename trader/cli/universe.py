# trader/cli/universe.py
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import logging

import click

from trader.adapters.factory import get_adapter
from trader.cli.__main__ import output_json

logger = logging.getLogger(__name__)

# Same ROOT convention as trader/server/agent.py
_ROOT = Path(__file__).resolve().parent.parent.parent


def _universe_path() -> Path:
    """Return canonical path to .trader/universe.json. Called by name so tests can patch it."""
    return _ROOT / ".trader" / "universe.json"


_SCAN_CONFIGS: dict[str, list[dict]] = {
    "us": [
        {"scan": "HIGH_VS_52W_HL",  "market": "STK.US.MAJOR", "limit": 20,
         "filters": [{"code": "curEMA200Above", "value": 1}]},
        {"scan": "TOP_PERC_GAIN",   "market": "STK.US.MAJOR", "limit": 20,
         "filters": [{"code": "marketCapAbove", "value": 500}]},
        {"scan": "MOST_ACTIVE_USD", "market": "STK.US.MAJOR", "limit": 10,
         "filters": []},
    ],
    "eu": [
        {"scan": "HIGH_VS_52W_HL",  "market": "STK.EU.IBIS", "limit": 15,
         "filters": [{"code": "curEMA200Above", "value": 1}]},
        {"scan": "TOP_PERC_GAIN",   "market": "STK.EU.IBIS", "limit": 15,
         "filters": []},
        {"scan": "TOP_PERC_GAIN",   "market": "STK.EU.AEB", "limit": 10,
         "filters": []},
        {"scan": "MOST_ACTIVE",     "market": "STK.EU.LSE", "limit": 10,
         "filters": []},
    ],
    "etf": [
        {"scan": "MOST_ACTIVE",    "market": "ETF.EQ.US.MAJOR", "limit": 20,
         "filters": []},
        {"scan": "HIGH_VS_52W_HL", "market": "ETF.EQ.US.MAJOR", "limit": 10,
         "filters": []},
    ],
    "options": [
        {"scan": "HIGH_OPT_IMP_VOLAT",           "market": "STK.US.MAJOR", "limit": 10,
         "filters": []},
        {"scan": "LOW_OPT_VOLUME_PUT_CALL_RATIO", "market": "STK.US.MAJOR", "limit": 10,
         "filters": []},
    ],
}

_SCAN_SCORES: dict[str, int] = {
    "HIGH_VS_52W_HL": 70,
    "TOP_PERC_GAIN": 65,
    "MOST_ACTIVE_USD": 40,
    "MOST_ACTIVE": 40,
    "HIGH_OPT_IMP_VOLAT": 60,
    "LOW_OPT_VOLUME_PUT_CALL_RATIO": 55,
}

_SEGMENT_TS_KEY = {"us": "last_refreshed_us", "eu": "last_refreshed_eu",
                   "etf": "last_refreshed_etf", "options": "last_refreshed_options"}
_SEGMENT_DATA_KEY = {"us": "us", "eu": "eu", "etf": "etf", "options": "options_candidates"}
_ASSET_CLASS = {"us": "stock", "eu": "stock", "etf": "etf", "options": "options"}


def _load() -> dict:
    p = _universe_path()
    if p.exists():
        return json.loads(p.read_text())
    return {
        "last_refreshed_eu": None, "last_refreshed_us": None,
        "last_refreshed_etf": None, "last_refreshed_options": None,
        "eu": [], "us": [], "etf": [], "options_candidates": [],
    }


def _save(data: dict) -> None:
    p = _universe_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


async def _run_scan(adapter, scan_type: str, market: str,
                    filters: list[dict], limit: int) -> list:
    """Run one IBKR scanner. Caller owns adapter connect/disconnect lifecycle."""
    try:
        return await adapter.scan(scan_type, market, filters or None, limit)
    except Exception as exc:
        logger.warning("scan %s on %s failed: %s", scan_type, market, exc)
        return []


@click.group()
def universe():
    """
    Universe cache: IBKR scan results used by opportunity-finder.

    \b
    Examples:
      trader universe show
      trader universe refresh --market us
      trader universe refresh --market all
    """


@universe.command("show")
@click.pass_context
def show(ctx):
    """Show current universe cache and staleness timestamps."""
    output_json(_load())


@universe.command("refresh")
@click.option("--market", default="all",
               type=click.Choice(["us", "eu", "etf", "options", "all"]),
               help="Segment to refresh. Default: all.")
@click.pass_context
def refresh(ctx, market):
    """
    Refresh universe cache by running IBKR scans.

    Writes .trader/universe.json with per-segment timestamps.
    Segments not targeted by --market are preserved unchanged.

    \b
    Examples:
      trader universe refresh
      trader universe refresh --market us
    """
    segments = ["us", "eu", "etf", "options"] if market == "all" else [market]
    adapter = get_adapter(ctx.obj["broker"], ctx.obj["config"])
    data = _load()

    async def run_all() -> tuple[dict[str, int], dict[str, list[str]]]:
        # Single connect/disconnect for all scans — matches watchlist.py pattern.
        # _run_scan must NOT manage adapter lifecycle; a closed httpx client
        # cannot be reopened and would silently return [] on every subsequent scan.
        await adapter.connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            counts: dict[str, int] = {}
            errors: dict[str, list[str]] = {}
            for seg in segments:
                tickers_seen: dict[str, dict] = {}
                seg_errors: list[str] = []
                for cfg in _SCAN_CONFIGS[seg]:
                    results = await _run_scan(adapter, cfg["scan"], cfg["market"],
                                              cfg["filters"], cfg["limit"])
                    if not results:
                        seg_errors.append(f"{cfg['scan']}@{cfg['market']}")
                    score = _SCAN_SCORES.get(cfg["scan"], 40)
                    exchange = cfg["market"].split(".")[-1]
                    for r in results:
                        t = r.symbol
                        if t not in tickers_seen:
                            tickers_seen[t] = {
                                "ticker": t, "exchange": exchange,
                                "asset_class": _ASSET_CLASS[seg],
                                "sources": [], "score": score,
                            }
                        else:
                            tickers_seen[t]["score"] = max(tickers_seen[t]["score"], score)
                        if cfg["scan"] not in tickers_seen[t]["sources"]:
                            tickers_seen[t]["sources"].append(cfg["scan"])
                segment_list = sorted(tickers_seen.values(), key=lambda x: -x["score"])
                data[_SEGMENT_DATA_KEY[seg]] = segment_list
                data[_SEGMENT_TS_KEY[seg]] = now
                counts[seg] = len(segment_list)
                if seg_errors:
                    errors[seg] = seg_errors
            _save(data)
            return counts, errors
        finally:
            try:
                await adapter.disconnect()
            except Exception:
                pass

    counts, errors = asyncio.run(run_all())
    result = {"refreshed": counts, "universe_path": str(_universe_path()), **data}
    if errors:
        result["scan_errors"] = errors
    output_json(result)
