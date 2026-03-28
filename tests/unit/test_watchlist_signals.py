"""Tests for scripts/watchlist-signals.py — TDD, written before the script."""
from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _load_module():
    spec = _ilu.spec_from_file_location(
        "watchlist_signals",
        Path(__file__).parents[2] / "scripts" / "watchlist-signals.py",
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


# ── _fmt_signal_row ────────────────────────────────────────────────────────────

def test_fmt_signal_row_buy_with_sentiment():
    row = _mod._fmt_signal_row({
        "ticker": "NVDA",
        "signal": 1,
        "signal_label": "buy",
        "strategy": "rsi",
        "sentiment_score": 0.60,
        "filtered": False,
    })
    assert row.startswith("BUY ")
    assert "NVDA" in row
    assert "+0.60" in row


def test_fmt_signal_row_sell_no_sentiment():
    row = _mod._fmt_signal_row({
        "ticker": "ASML",
        "signal": -1,
        "signal_label": "sell",
        "strategy": "macd",
        "sentiment_score": None,
        "filtered": False,
    })
    assert "SELL" in row
    assert "sentiment" not in row.lower()


def test_fmt_signal_row_filtered_shows_reason():
    row = _mod._fmt_signal_row({
        "ticker": "TSLA",
        "signal": 1,
        "signal_label": "buy",
        "strategy": "rsi",
        "sentiment_score": 0.10,
        "filtered": True,
        "filter_reason": "low sentiment",
    })
    assert "[low sentiment]" in row


def test_fmt_signal_row_filtered_escapes_underscores():
    """Underscores in filter_reason are escaped for Telegram Markdown safety."""
    row = _mod._fmt_signal_row({
        "ticker": "TSLA",
        "signal": 1,
        "signal_label": "buy",
        "strategy": "rsi",
        "sentiment_score": 0.10,
        "filtered": True,
        "filter_reason": "low_sentiment",
    })
    assert r"low\_sentiment" in row
    assert "[low\\_sentiment]" in row


# ── _load_watchlists ───────────────────────────────────────────────────────────

def test_load_watchlists_missing_file(tmp_path):
    with patch.object(_mod, "WATCHLISTS_PATH", tmp_path / "nope.json"):
        result = _mod._load_watchlists()
    assert result == {}


def test_load_watchlists_existing(tmp_path):
    data = {"default": ["NVDA", "AAPL"], "tr-portfolio": ["ASML"]}
    wl_file = tmp_path / "watchlists.json"
    wl_file.write_text(json.dumps(data))
    with patch.object(_mod, "WATCHLISTS_PATH", wl_file):
        result = _mod._load_watchlists()
    assert result == data


# ── _run_signals ───────────────────────────────────────────────────────────────

def test_run_signals_subprocess_failure():
    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stderr = "some error"
    with patch("subprocess.run", return_value=fake_result):
        result = _mod._run_signals(["NVDA", "AAPL"])
    assert result == []


def test_run_signals_json_decode_error():
    """Returncode 0 but non-JSON stdout returns []."""
    fake = type("R", (), {"returncode": 0, "stderr": "", "stdout": "not json"})()
    with patch("subprocess.run", return_value=fake):
        assert _mod._run_signals(["NVDA"]) == []


# ── _build_message ─────────────────────────────────────────────────────────────

def test_build_message_all_empty_returns_none():
    assert _mod._build_message({}) is None
    assert _mod._build_message({"default": []}) is None


def test_build_message_groups_buy_sell_hold():
    signals = [
        {"ticker": "NVDA", "signal": 1,  "signal_label": "buy",  "strategy": "rsi",  "sentiment_score": 0.5,  "filtered": False},
        {"ticker": "ASML", "signal": -1, "signal_label": "sell", "strategy": "macd", "sentiment_score": -0.3, "filtered": False},
        {"ticker": "AAPL", "signal": 0,  "signal_label": "hold", "strategy": "rsi",  "sentiment_score": None, "filtered": False},
    ]
    with patch.object(_mod, "_run_signals", return_value=signals):
        msg = _mod._build_message({"default": ["NVDA", "ASML", "AAPL"]})
    assert msg is not None
    assert "BUY" in msg
    assert "SELL" in msg
    assert "HOLD" in msg
    assert "*default*" in msg


def test_build_message_skips_empty_lists():
    signals = [
        {"ticker": "NVDA", "signal": 1, "signal_label": "buy", "strategy": "rsi", "sentiment_score": 0.4, "filtered": False},
    ]

    def fake_run_signals(tickers):
        if tickers == ["NVDA"]:
            return signals
        return []

    with patch.object(_mod, "_run_signals", side_effect=fake_run_signals):
        msg = _mod._build_message({"active": ["NVDA"], "empty-list": []})
    assert msg is not None
    assert "*active*" in msg
    assert "empty-list" not in msg


def test_build_message_handles_ticker_error():
    signals = [
        {"ticker": "NVDA", "signal": 1, "signal_label": "buy", "strategy": "rsi", "sentiment_score": 0.5, "filtered": False},
        {"ticker": "FAIL", "error": "timeout fetching data"},
    ]
    with patch.object(_mod, "_run_signals", return_value=signals):
        # Must not raise KeyError
        msg = _mod._build_message({"default": ["NVDA", "FAIL"]})
    assert msg is not None
    assert "ERR" in msg
    assert "FAIL" in msg
