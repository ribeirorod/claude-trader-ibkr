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


def test_execute_rejects_when_guard_blocks(tmp_path):
    """OrderGuard rejection produces status='guarded' with reason in output."""
    from trader.pipeline.models import (
        ProposalSet, SectorProposals, Proposal, ProposalOrder, ProposalSizing,
    )
    from trader.guard import GuardResult

    runner = CliRunner()
    pipeline_dir = tmp_path / "pipeline"
    pipeline_dir.mkdir()

    proposal_set = ProposalSet(
        run_id="test-exec",
        regime="bull",
        available_capital=100_000.0,
        sectors={
            "Technology": SectorProposals(
                summary="test",
                proposals=[
                    Proposal(
                        rank=1,
                        ticker="AAPL",
                        source="discovery",
                        direction="long",
                        consensus=3,
                        strategies_agree=["RSI", "MACD", "MACross"],
                        conviction="high",
                        order=ProposalOrder(
                            side="buy",
                            order_type="limit",
                            contract_type="stock",
                            qty=10,
                            price=150.0,
                            stop_loss=145.0,
                            take_profit=160.0,
                        ),
                        sizing=ProposalSizing(
                            atr=3.5,
                            risk_per_share=5.0,
                            position_value=1500.0,
                            pct_of_nlv=0.015,
                        ),
                        sector="Technology",
                    ),
                ],
            ),
        },
    )
    (pipeline_dir / "proposals.json").write_text(proposal_set.model_dump_json())

    mock_acct = MagicMock()
    mock_acct.balance.net_liquidation = 100_000.0

    guard_result = GuardResult(
        allowed=False,
        reason="daily_limit",
        details={"today": 3, "max": 3},
    )

    with patch("trader.cli.pipeline._get_pipeline_dir", return_value=pipeline_dir), \
         patch("trader.cli.pipeline.get_adapter") as mock_adapter_factory, \
         patch("trader.cli.pipeline.OrderGuard") as mock_guard_cls:

        mock_adapter = AsyncMock()
        mock_adapter.get_account = AsyncMock(return_value=mock_acct)
        mock_adapter.list_positions = AsyncMock(return_value=[])
        mock_adapter.list_orders = AsyncMock(return_value=[])
        mock_adapter_factory.return_value = mock_adapter

        mock_guard = MagicMock()
        mock_guard.validate.return_value = guard_result
        mock_guard_cls.return_value = mock_guard

        result = runner.invoke(cli, ["pipeline", "execute"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)

    # The order should be guarded, not placed
    assert data["guarded"] == 1
    assert data["executed"] == 0
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "guarded"
    assert "daily_limit" in data["results"][0]["reason"]

    # place_order should NOT have been called
    mock_adapter.place_order.assert_not_called()
