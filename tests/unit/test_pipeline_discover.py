import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from trader.pipeline.discover import run_discover
from trader.pipeline.models import CandidateSet
from trader.models import ScanResult


def _scan_result(symbol, sector="Technology"):
    return ScanResult(symbol=symbol, sector=sector)


def _run(coro):
    return asyncio.run(coro)


def test_discover_includes_watchlist_tickers(tmp_path):
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({
        "default": {"tickers": ["NVDA", "AAPL"], "sectors": {"NVDA": "Technology", "AAPL": "Technology"}},
    }))
    pipeline_dir = tmp_path / "pipeline"

    result = _run(run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=AsyncMock(return_value=[]),
        news_fn=AsyncMock(return_value=[]),
    ))

    assert isinstance(result, CandidateSet)
    assert result.watchlist_count == 2
    tech = result.sectors.get("Technology", [])
    assert any(c.ticker == "NVDA" and c.priority == "high" for c in tech)


def test_discover_adds_scan_results(tmp_path):
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({}))
    pipeline_dir = tmp_path / "pipeline"

    async def mock_scan(scan_type, location, filters, limit):
        if scan_type == "HIGH_VS_52W_HL":
            return [_scan_result("CRWD", "Technology"), _scan_result("XOM", "Energy")]
        return []

    result = _run(run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=mock_scan,
        news_fn=AsyncMock(return_value=[]),
    ))

    assert result.discovery_count >= 2
    assert any(c.ticker == "CRWD" for candidates in result.sectors.values() for c in candidates)


def test_discover_deduplicates_watchlist_and_scan(tmp_path):
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({
        "default": {"tickers": ["NVDA"], "sectors": {"NVDA": "Technology"}},
    }))
    pipeline_dir = tmp_path / "pipeline"

    async def mock_scan(scan_type, location, filters, limit):
        return [_scan_result("NVDA", "Technology")]

    result = _run(run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=mock_scan,
        news_fn=AsyncMock(return_value=[]),
    ))

    nvda_candidates = [
        c for candidates in result.sectors.values()
        for c in candidates if c.ticker == "NVDA"
    ]
    assert len(nvda_candidates) == 1
    assert nvda_candidates[0].source == "watchlist"
    assert nvda_candidates[0].priority == "high"


def test_discover_uses_bearish_scans_in_bear_regime(tmp_path):
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({}))
    pipeline_dir = tmp_path / "pipeline"

    scans_called = []
    async def mock_scan(scan_type, location, filters, limit):
        scans_called.append(scan_type)
        return []

    _run(run_discover(
        regime="bear",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=mock_scan,
        news_fn=AsyncMock(return_value=[]),
    ))

    assert "TOP_PERC_LOSE" in scans_called or "HIGH_OPT_IMP_VOLAT" in scans_called


def test_discover_writes_candidates_json(tmp_path):
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({
        "default": {"tickers": ["AAPL"], "sectors": {"AAPL": "Technology"}},
    }))
    pipeline_dir = tmp_path / "pipeline"

    _run(run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=AsyncMock(return_value=[]),
        news_fn=AsyncMock(return_value=[]),
    ))

    assert (pipeline_dir / "candidates.json").exists()
    data = json.loads((pipeline_dir / "candidates.json").read_text())
    assert data["regime"] == "bull"
