import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from click.testing import CliRunner
from trader.cli.__main__ import cli


def test_prune_removes_stale_discovery_tickers(tmp_path):
    runner = CliRunner()
    stale_date = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    fresh_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    wl_data = {
        "discovery": {
            "tickers": ["STALE", "FRESH", "MANUAL"],
            "sectors": {},
            "metadata": {
                "STALE": {"added_at": stale_date, "source": "discovery"},
                "FRESH": {"added_at": fresh_date, "source": "discovery"},
            },
        },
    }
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps(wl_data))

    # Patch _wl_path to use our tmp_path
    with patch("trader.cli.watchlist._wl_path", return_value=wl_path):
        result = runner.invoke(cli, ["watchlist", "prune"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "STALE" in data["pruned"]
    assert "FRESH" not in data["pruned"]
    assert "MANUAL" not in data["pruned"]

    updated = json.loads(wl_path.read_text())
    assert "STALE" not in updated["discovery"]["tickers"]
    assert "FRESH" in updated["discovery"]["tickers"]
    assert "MANUAL" in updated["discovery"]["tickers"]


def test_prune_dry_run_does_not_modify(tmp_path):
    runner = CliRunner()
    stale_date = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    wl_data = {
        "discovery": {
            "tickers": ["STALE"],
            "sectors": {},
            "metadata": {"STALE": {"added_at": stale_date, "source": "discovery"}},
        },
    }
    wl_path = tmp_path / "watchlists.json"
    wl_path.write_text(json.dumps(wl_data))

    with patch("trader.cli.watchlist._wl_path", return_value=wl_path):
        result = runner.invoke(cli, ["watchlist", "prune", "--dry-run"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "STALE" in data["would_prune"]

    unchanged = json.loads(wl_path.read_text())
    assert "STALE" in unchanged["discovery"]["tickers"]
