import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from click.testing import CliRunner

from trader.cli.__main__ import cli
from trader.models import Position


def make_position(ticker="AAPL", qty=10, avg_cost=150.0, unrealized_pnl=-45.0):
    return Position(
        ticker=ticker,
        qty=qty,
        avg_cost=avg_cost,
        market_value=qty * avg_cost,
        unrealized_pnl=unrealized_pnl,
    )


def write_agent_log(path: Path, entries: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_time_stops_command_outputs_json():
    """trader market time-stops outputs JSON with time-stop results."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / ".trader" / "logs" / "agent.jsonl"
        write_agent_log(log_path, [
            {
                "ts": "2026-03-12T09:30:00",
                "run_id": "test",
                "agent": "pipeline",
                "event": "ORDER_INTENT",
                "ticker": "AAPL",
                "side": "buy",
                "qty": 10,
            },
        ])

        mock_adapter = AsyncMock()
        mock_adapter.list_positions = AsyncMock(return_value=[
            make_position("AAPL", unrealized_pnl=-45.0),
        ])

        with patch("trader.cli.market.get_adapter", return_value=mock_adapter), \
             patch("trader.cli.market.detect_regime", return_value=MagicMock(value="bear")), \
             patch("trader.cli.market._get_agent_log_path", return_value=log_path), \
             patch("trader.cli.market._get_today", return_value=datetime(2026, 3, 30)):
            result = runner.invoke(cli, ["market", "time-stops"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["regime"] == "bear"
        assert len(data["results"]) == 1
        assert data["results"][0]["ticker"] == "AAPL"
        assert data["results"][0]["action"] == "review"


def test_time_stops_command_regime_override():
    """--regime flag overrides detected regime."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / ".trader" / "logs" / "agent.jsonl"
        write_agent_log(log_path, [
            {
                "ts": "2026-03-23T09:30:00",
                "run_id": "test",
                "agent": "pipeline",
                "event": "ORDER_INTENT",
                "ticker": "AAPL",
                "side": "buy",
                "qty": 10,
            },
        ])

        mock_adapter = AsyncMock()
        mock_adapter.list_positions = AsyncMock(return_value=[
            make_position("AAPL", unrealized_pnl=100.0),
        ])

        with patch("trader.cli.market.get_adapter", return_value=mock_adapter), \
             patch("trader.cli.market._get_agent_log_path", return_value=log_path), \
             patch("trader.cli.market._get_today", return_value=datetime(2026, 3, 30)):
            result = runner.invoke(cli, ["market", "time-stops", "--regime", "bull"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["regime"] == "bull"
        assert data["results"][0]["max_days"] == 20
