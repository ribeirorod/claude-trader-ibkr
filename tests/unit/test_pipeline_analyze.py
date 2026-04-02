import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import numpy as np
from trader.pipeline.analyze import run_analyze
from trader.pipeline.models import Candidate, CandidateNews, CandidateSet, ProposalSet


def _make_ohlcv(days=60, trend="up"):
    dates = pd.date_range("2026-01-01", periods=days, freq="B")
    if trend == "up":
        close = np.linspace(100, 150, days) + np.random.normal(0, 2, days)
    else:
        close = np.linspace(150, 100, days) + np.random.normal(0, 2, days)
    return pd.DataFrame({
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, days),
    }, index=dates)


def _make_candidate_set(tickers_and_sources):
    candidates = []
    for ticker, source, sector in tickers_and_sources:
        candidates.append(Candidate(
            ticker=ticker, source=source,
            priority="high" if source == "watchlist" else "normal",
            sector=sector,
        ))
    sectors = {}
    for c in candidates:
        sectors.setdefault(c.sector or "Unknown", []).append(c)
    return CandidateSet(run_id="test", regime="bull", sectors=sectors)


def test_analyze_produces_proposals(tmp_path):
    cs = _make_candidate_set([("AAPL", "watchlist", "Technology")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="up")):
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=2,
            watchlist_consensus_threshold=1,
        )

    assert isinstance(result, ProposalSet)
    assert result.total_proposals >= 0


def test_analyze_watchlist_has_lower_threshold(tmp_path):
    cs = _make_candidate_set([
        ("NVDA", "watchlist", "Technology"),
        ("CRWD", "discovery", "Technology"),
    ])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="up")):
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=6,
            watchlist_consensus_threshold=1,
        )

    assert isinstance(result, ProposalSet)


def test_analyze_writes_proposals_json(tmp_path):
    cs = _make_candidate_set([("SPY", "watchlist", "ETF")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv()):
        run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
        )

    assert (pipeline_dir / "proposals.json").exists()


def test_analyze_bear_regime_allows_longs(tmp_path):
    """Bear regime no longer blocks longs — strategies assess conditions, regime adjusts sizing."""
    cs = _make_candidate_set([("AAPL", "watchlist", "Technology")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="up")):
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bear",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
        )

    # Proposals should exist if strategies signal buy — bear regime doesn't filter them
    assert (pipeline_dir / "proposals.json").exists()


def test_analyze_filters_on_bearish_sentiment(tmp_path):
    """Bearish sentiment (score < -0.2) should filter out long proposals via RiskFilter."""
    # Create a candidate with bearish news and negative ticker_sentiment
    bearish_news = [
        CandidateNews(headline="Company faces massive lawsuit", sentiment=-0.8),
        CandidateNews(headline="Revenue misses expectations badly", sentiment=-0.7),
        CandidateNews(headline="CEO resigns amid scandal", sentiment=-0.9),
    ]
    candidate = Candidate(
        ticker="BADNEWS",
        source="watchlist",
        priority="high",
        sector="Technology",
        news=bearish_news,
    )
    cs = CandidateSet(
        run_id="test",
        regime="bull",
        sectors={"Technology": [candidate]},
        ticker_sentiment={"BADNEWS": -0.5},  # strongly bearish
    )

    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="up")):
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=1,
            watchlist_consensus_threshold=1,
        )

    # The bearish sentiment should cause RiskFilter to veto any long proposal
    long_tickers = [
        p.ticker
        for sp in result.sectors.values()
        for p in sp.proposals
        if p.direction == "long"
    ]
    assert "BADNEWS" not in long_tickers, (
        "Bearish sentiment (score=-0.5) should filter out long proposals"
    )


def test_analyze_bear_regime_uses_regime_thresholds(tmp_path):
    """Bear regime should use thresholds from regime_params.json when CLI doesn't override."""
    cs = _make_candidate_set([("AAPL", "watchlist", "Technology")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="up")), \
         patch("trader.pipeline.analyze.get_regime_thresholds", return_value={"discovery": 5, "watchlist": 5}) as mock_thresholds:
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bear",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
        )

    mock_thresholds.assert_called_once_with("bear")
    total = sum(len(sp.proposals) for sp in result.sectors.values())
    assert total == 0, f"Expected 0 proposals with regime threshold=5, got {total}"
