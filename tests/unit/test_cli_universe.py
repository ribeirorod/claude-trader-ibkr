# tests/unit/test_cli_universe.py
from __future__ import annotations
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from click.testing import CliRunner
from trader.cli.__main__ import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_universe_path(tmp_path):
    """Patch _universe_path to return a fresh temp path — isolates all file I/O."""
    p = tmp_path / "universe.json"
    with patch("trader.cli.universe._universe_path", return_value=p):
        yield p


def test_universe_show_empty(runner, fake_universe_path):
    """universe show returns empty structure when file missing."""
    result = runner.invoke(cli, ["universe", "show"],
                           obj={"broker": "ibkr-rest", "config": MagicMock()})
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["us"] == []
    assert data["eu"] == []
    assert data["last_refreshed_us"] is None


def test_universe_show_existing(runner, fake_universe_path):
    """universe show reads and returns existing universe.json."""
    fake_universe_path.write_text(json.dumps({
        "last_refreshed_us": "2026-03-19T10:00:00Z",
        "last_refreshed_eu": None,
        "us": [{"ticker": "NVDA", "score": 85}],
        "eu": [],
        "etf": [],
        "options_candidates": [],
    }))
    result = runner.invoke(cli, ["universe", "show"],
                           obj={"broker": "ibkr-rest", "config": MagicMock()})
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["us"][0]["ticker"] == "NVDA"
    assert data["last_refreshed_us"] == "2026-03-19T10:00:00Z"


def test_universe_refresh_writes_file(runner, fake_universe_path):
    """universe refresh --market us writes scan results to universe.json."""
    mock_scan_result = [MagicMock(symbol="NVDA"), MagicMock(symbol="AVGO")]

    with patch("trader.cli.universe._run_scan", new_callable=AsyncMock, return_value=mock_scan_result), \
         patch("trader.cli.universe.get_adapter"):
        result = runner.invoke(cli, ["universe", "refresh", "--market", "us"],
                               obj={"broker": "ibkr-rest", "config": MagicMock()})

    assert result.exit_code == 0, result.output
    assert fake_universe_path.exists()
    data = json.loads(fake_universe_path.read_text())
    tickers = [e["ticker"] for e in data["us"]]
    assert "NVDA" in tickers
    assert "AVGO" in tickers
    assert data["last_refreshed_us"] is not None


def test_universe_refresh_eu_preserves_us_segment(runner, fake_universe_path):
    """universe refresh --market eu only overwrites eu; us segment is preserved."""
    existing = {
        "last_refreshed_us": "2026-03-19T10:00:00Z",
        "last_refreshed_eu": None,
        "us": [{"ticker": "NVDA", "score": 85, "sources": [], "asset_class": "stock", "exchange": "MAJOR"}],
        "eu": [],
        "etf": [],
        "options_candidates": [],
    }
    fake_universe_path.write_text(json.dumps(existing))

    mock_scan_result = [MagicMock(symbol="ASML")]
    with patch("trader.cli.universe._run_scan", new_callable=AsyncMock, return_value=mock_scan_result), \
         patch("trader.cli.universe.get_adapter"):
        result = runner.invoke(cli, ["universe", "refresh", "--market", "eu"],
                               obj={"broker": "ibkr-rest", "config": MagicMock()})

    assert result.exit_code == 0, result.output
    data = json.loads(fake_universe_path.read_text())
    assert data["us"][0]["ticker"] == "NVDA"
    assert data["eu"][0]["ticker"] == "ASML"
    assert data["last_refreshed_us"] == "2026-03-19T10:00:00Z"
    assert data["last_refreshed_eu"] is not None
