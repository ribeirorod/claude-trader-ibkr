"""Integration test: discover -> analyze pipeline with mocked external deps."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd

from trader.models import ScanResult
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
    async def mock_scan(scan_type, market, filters, limit):
        return [ScanResult(symbol="CRWD", sector="Technology")]

    candidates = run_discover(
        regime="bull",
        watchlist_path=wl_path,
        pipeline_dir=pipeline_dir,
        scan_fn=mock_scan,
        news_fn=AsyncMock(return_value=[]),
    )

    assert candidates.total_candidates >= 2  # NVDA (watchlist) + CRWD (discovery)
    assert (pipeline_dir / "candidates.json").exists()

    # Phase 2: Analyze ---------------------------------------------------------
    with patch(
        "trader.pipeline.analyze._fetch_ohlcv",
        return_value=_make_ohlcv(trend="up"),
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
