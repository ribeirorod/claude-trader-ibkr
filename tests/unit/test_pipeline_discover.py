import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from trader.pipeline.discover import run_discover
from trader.pipeline.models import CandidateSet
from trader.models import ScanResult, NewsItem


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


def test_discover_scores_news_sentiment(tmp_path):
    """News items with bullish words produce real sentiment scores (not 0.0)
    and ticker_sentiment dict has positive score for tickers with bullish news."""
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({
        "default": {"tickers": ["AAPL", "TSLA"], "sectors": {"AAPL": "Technology", "TSLA": "Automotive"}},
    }))
    pipeline_dir = tmp_path / "pipeline"

    bullish_news = [
        NewsItem(
            id="1",
            ticker="AAPL",
            headline="AAPL beats earnings, strong growth and record profit surge",
            summary="Apple exceeds expectations with record revenue and strong gains",
            published_at="2026-03-31T10:00:00Z",
        ),
        NewsItem(
            id="2",
            ticker="AAPL",
            headline="Analysts upgrade AAPL, bullish rally expected",
            summary="Multiple analysts raised price targets after positive results",
            published_at="2026-03-31T11:00:00Z",
        ),
        NewsItem(
            id="3",
            ticker="TSLA",
            headline="TSLA decline continues amid weak demand and losses",
            summary="Tesla misses estimates, bearish outlook with lower guidance",
            published_at="2026-03-31T10:00:00Z",
        ),
    ]

    async def mock_news_fn(tickers, limit):
        return [item for item in bullish_news if item.ticker in tickers]

    result = _run(run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=AsyncMock(return_value=[]),
        news_fn=mock_news_fn,
    ))

    # Check that CandidateNews has real sentiment (not hardcoded 0.0)
    aapl_candidates = [
        c for candidates in result.sectors.values()
        for c in candidates if c.ticker == "AAPL"
    ]
    assert len(aapl_candidates) == 1
    aapl = aapl_candidates[0]
    assert len(aapl.news) > 0
    # At least one headline should have non-zero sentiment
    assert any(n.sentiment != 0.0 for n in aapl.news)
    # Bullish news should produce positive per-headline sentiment
    assert any(n.sentiment > 0.0 for n in aapl.news)

    # Check ticker_sentiment dict has positive score for AAPL (bullish news)
    assert "AAPL" in result.ticker_sentiment
    assert result.ticker_sentiment["AAPL"] > 0.0

    # Check TSLA has negative sentiment (bearish news)
    assert "TSLA" in result.ticker_sentiment
    assert result.ticker_sentiment["TSLA"] < 0.0
