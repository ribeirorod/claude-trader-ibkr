import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from click.testing import CliRunner
from trader.cli.__main__ import cli


def test_pipeline_discover_command(tmp_path):
    runner = CliRunner()
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps({
        "default": {"tickers": ["AAPL"], "sectors": {"AAPL": "Technology"}},
    }))

    with patch("trader.cli.pipeline._get_watchlist_path", return_value=wl_path), \
         patch("trader.cli.pipeline._get_pipeline_dir", return_value=tmp_path / "pipeline"), \
         patch("trader.market.regime.detect_regime", return_value=MagicMock(value="bull")), \
         patch("trader.cli.pipeline.get_adapter") as mock_adapter_factory, \
         patch("trader.cli.pipeline.get_news_provider") as mock_news_factory:

        mock_adapter = AsyncMock()
        mock_adapter.scan = AsyncMock(return_value=[])
        mock_adapter_factory.return_value = mock_adapter

        mock_news = AsyncMock()
        mock_news.get_news = AsyncMock(return_value=[])
        mock_news.aclose = AsyncMock()
        mock_news_factory.return_value = mock_news

        result = runner.invoke(cli, ["pipeline", "discover"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "regime" in data
    assert "total_candidates" in data


def test_pipeline_analyze_command(tmp_path):
    runner = CliRunner()
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()

    from trader.pipeline.models import CandidateSet, Candidate
    cs = CandidateSet(
        run_id="test",
        regime="bull",
        sectors={"Technology": [
            Candidate(ticker="AAPL", source="watchlist", priority="high", sector="Technology"),
        ]},
    )
    (pipeline_dir / "candidates.json").write_text(cs.model_dump_json())

    import pandas as pd
    import numpy as np
    df = pd.DataFrame({
        "open": np.linspace(100, 150, 60),
        "high": np.linspace(102, 152, 60),
        "low": np.linspace(98, 148, 60),
        "close": np.linspace(100, 150, 60),
        "volume": [1_000_000] * 60,
    }, index=pd.date_range("2026-01-01", periods=60, freq="B"))

    mock_acct = MagicMock()
    mock_acct.balance.net_liquidation = 100_000.0

    with patch("trader.cli.pipeline._get_pipeline_dir", return_value=pipeline_dir), \
         patch("trader.pipeline.analyze._fetch_ohlcv", return_value=df), \
         patch("trader.market.regime.detect_regime", return_value=MagicMock(value="bull")), \
         patch("trader.cli.pipeline.get_adapter") as mock_adapter_factory:

        mock_adapter = AsyncMock()
        mock_adapter.get_account = AsyncMock(return_value=mock_acct)
        mock_adapter.list_positions = AsyncMock(return_value=[])
        mock_adapter.list_orders = AsyncMock(return_value=[])
        mock_adapter_factory.return_value = mock_adapter

        result = runner.invoke(cli, ["pipeline", "analyze"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "regime" in data
    assert "total_proposals" in data
