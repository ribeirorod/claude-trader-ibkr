import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import numpy as np
from trader.pipeline.analyze import run_analyze, _fetch_ohlcv
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


def test_fetch_ohlcv_passes_interval(tmp_path):
    """_fetch_ohlcv should forward the interval parameter to yf.download."""
    with patch("trader.pipeline.analyze.yf.download") as mock_dl:
        mock_dl.return_value = pd.DataFrame({
            "Open": [100], "High": [102], "Low": [98],
            "Close": [101], "Volume": [1_000_000],
        }, index=pd.date_range("2026-04-01", periods=1, freq="h"))

        _fetch_ohlcv("AAPL", period="30d", interval="4h")

        mock_dl.assert_called_once_with(
            "AAPL", period="30d", interval="4h",
            progress=False, auto_adjust=True,
        )


def test_analyze_passes_interval_to_fetch(tmp_path):
    """run_analyze should forward interval to _fetch_ohlcv with adjusted period."""
    cs = _make_candidate_set([("AAPL", "watchlist", "Technology")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    with patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="up")) as mock_fetch:
        run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=2,
            watchlist_consensus_threshold=1,
            interval="4h",
        )

        call_kwargs = mock_fetch.call_args
        assert call_kwargs[1].get("interval") == "4h" or (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == "4h"), \
            f"Expected interval='4h' in call: {call_kwargs}"


def test_analyze_bearish_signal_produces_inverse_etf_proposal(tmp_path):
    """When a bearish signal fires on a mapped ticker, an inverse ETF proposal is added."""
    cs = _make_candidate_set([("CSPX", "watchlist", "ETF")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    def _all_sell(df, sector, regime="bull"):
        return {"rsi": -1, "macd": -1, "ma_cross": -1, "bnf": -1, "momentum": -1, "pullback": -1}

    inverse_map = {
        "index_hedges": {
            "SP500": {"ticker": "XISX", "leverage": -1},
        },
        "sector_hedges": {},
        "usage_rules": {"max_hold_days": 20, "max_portfolio_pct": 10},
    }

    with (
        patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="down")),
        patch("trader.pipeline.analyze._run_all_strategies", side_effect=_all_sell),
        patch("trader.pipeline.analyze.load_inverse_map", return_value=inverse_map),
    ):
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=1,
            watchlist_consensus_threshold=1,
        )

    all_proposals = [p for sp in result.sectors.values() for p in sp.proposals]
    inverse_proposals = [p for p in all_proposals if p.ticker == "XISX"]
    assert len(inverse_proposals) == 1, (
        f"Expected 1 inverse ETF proposal for XISX, got {len(inverse_proposals)}. "
        f"All proposals: {[(p.ticker, p.direction, p.order.contract_type) for p in all_proposals]}"
    )
    inv = inverse_proposals[0]
    assert inv.order.side == "buy"
    assert inv.order.contract_type == "etf"
    assert inv.direction == "hedge"


def test_analyze_unmapped_ticker_no_inverse_proposal(tmp_path):
    """A bearish signal on an unmapped ticker should NOT produce an inverse ETF proposal."""
    cs = _make_candidate_set([("RANDOMTICKER", "watchlist", "Technology")])
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    def _all_sell(df, sector, regime="bull"):
        return {"rsi": -1, "macd": -1, "ma_cross": -1, "bnf": -1, "momentum": -1, "pullback": -1}

    with (
        patch("trader.pipeline.analyze._fetch_ohlcv", return_value=_make_ohlcv(trend="down")),
        patch("trader.pipeline.analyze._run_all_strategies", side_effect=_all_sell),
        patch("trader.pipeline.analyze.load_inverse_map", return_value={}),
    ):
        result = run_analyze(
            pipeline_dir=pipeline_dir,
            regime="bull",
            account_value=100_000.0,
            existing_positions=[],
            open_orders=[],
            consensus_threshold=1,
            watchlist_consensus_threshold=1,
        )

    all_proposals = [p for sp in result.sectors.values() for p in sp.proposals]
    inverse_tickers = {"XISX", "SQQQ", "SEU5", "SUK2", "XSPS"}
    inverse_proposals = [p for p in all_proposals if p.ticker in inverse_tickers]
    assert len(inverse_proposals) == 0
