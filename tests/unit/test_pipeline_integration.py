"""Integration test: discover -> analyze pipeline with mocked external deps."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest

from trader.models import NewsItem, ScanResult
from trader.pipeline.analyze import run_analyze
from trader.pipeline.discover import run_discover


def _make_ohlcv(days=60, trend="up"):
    dates = pd.date_range("2026-01-01", periods=days, freq="B")
    if trend == "up":
        close = np.linspace(100, 150, days) + np.random.default_rng(42).normal(0, 1, days)
    else:
        close = np.linspace(150, 100, days) + np.random.default_rng(42).normal(0, 1, days)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": [2_000_000] * days,
        },
        index=dates,
    )


def test_full_pipeline_discover_then_analyze(tmp_path: Path):
    """End-to-end: discover finds candidates, analyze produces proposals."""
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(
        json.dumps(
            {
                "default": {
                    "tickers": ["NVDA"],
                    "sectors": {"NVDA": "Technology"},
                },
            }
        )
    )
    pipeline_dir = tmp_path / "pipeline"

    # Phase 1: Discover -------------------------------------------------------
    async def mock_scan(scan_type, location, filters, limit):
        return [ScanResult(symbol="CRWD", sector="Technology")]

    candidates = asyncio.run(run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=mock_scan,
        news_fn=AsyncMock(return_value=[]),
    ))

    assert candidates.total_candidates >= 2  # NVDA (watchlist) + CRWD (discovery)
    assert (pipeline_dir / "candidates.json").exists()

    # Phase 2: Analyze ---------------------------------------------------------
    with patch(
        "trader.pipeline.analyze._fetch_ohlcv",
        return_value=_make_ohlcv(trend="up"),
    ), patch(
        "trader.pipeline.analyze._get_sector",
        return_value="Technology",
    ):
        proposals = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=1,
            watchlist_consensus_threshold=1,
        )

    assert (pipeline_dir / "proposals.json").exists()
    assert proposals.regime == "bull"
    # With consensus_threshold=1, at least one candidate should produce a proposal
    assert proposals.total_proposals >= 1
    for sp in proposals.sectors.values():
        for p in sp.proposals:
            assert p.ticker
            assert p.direction in ("long", "hedge", "short")
            assert p.order.side in ("buy", "sell", "short")
            assert p.consensus >= 1


@pytest.mark.asyncio
async def test_full_pipeline_with_sentiment_filtering(tmp_path, monkeypatch):
    """End-to-end: discover scores sentiment -> analyze filters bearish candidates."""

    # Bullish news for NVDA, bearish news for CRWD
    news_items = [
        NewsItem(id="1", ticker="NVDA", headline="NVDA surges on strong AI growth record",
                 summary="Strong earnings beat estimates", published_at="2026-03-31T10:00:00Z"),
        NewsItem(id="2", ticker="NVDA", headline="NVDA rally continues with bullish upgrade",
                 summary="Analysts raise price targets", published_at="2026-03-31T11:00:00Z"),
        NewsItem(id="3", ticker="CRWD", headline="CRWD declines on weak guidance warning",
                 summary="Losses concern investors with negative outlook", published_at="2026-03-31T10:00:00Z"),
        NewsItem(id="4", ticker="CRWD", headline="CRWD drops after lawsuit and recall risk",
                 summary="Bearish downgrade cuts price target", published_at="2026-03-31T11:00:00Z"),
    ]

    async def scan_fn(scan_type, location, filters, limit):
        return [ScanResult(symbol="CRWD", sector="Technology")]

    async def news_fn(tickers, limit=3):
        return [item for item in news_items if item.ticker in tickers]

    # Write watchlists with NVDA
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text('{"test": {"tickers": ["NVDA"], "sectors": {"NVDA": "Technology"}}}')

    # Run discover
    result = await run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=tmp_path,
        scan_fn=scan_fn,
        news_fn=news_fn,
    )

    # Verify sentiment scoring
    assert result.ticker_sentiment.get("NVDA", 0) > 0, "Bullish news should produce positive sentiment"
    assert result.ticker_sentiment.get("CRWD", 0) < 0, "Bearish news should produce negative sentiment"

    # Mock yfinance for analyze — uptrending data
    df = _make_ohlcv(trend="up")
    monkeypatch.setattr("trader.pipeline.analyze._fetch_ohlcv", lambda t, **kw: df)
    monkeypatch.setattr("trader.pipeline.analyze._get_sector", lambda t: "Technology")

    # Run analyze with low threshold
    proposals = run_analyze(
        pipeline_dir=tmp_path,
        regime="bull",
        account_value=100_000,
        existing_positions=[],
        open_orders=[],
        consensus_threshold=1,
        watchlist_consensus_threshold=1,
    )

    # CRWD (bearish sentiment < -0.2) should be filtered from long proposals
    long_tickers = [
        p.ticker for sp in proposals.sectors.values()
        for p in sp.proposals if p.direction == "long"
    ]
    assert "CRWD" not in long_tickers, "Bearish sentiment should filter CRWD from long proposals"
