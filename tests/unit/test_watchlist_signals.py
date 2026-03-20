"""Tests for scripts/watchlist-signals.py — TDD, written before the script."""
from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _import():
    spec = _ilu.spec_from_file_location(
        "watchlist_signals",
        Path(__file__).parents[2] / "scripts" / "watchlist-signals.py",
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── _fmt_signal_row ────────────────────────────────────────────────────────────

def test_fmt_signal_row_buy_with_sentiment():
    mod = _import()
    row = mod._fmt_signal_row({
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
    mod = _import()
    row = mod._fmt_signal_row({
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
    mod = _import()
    row = mod._fmt_signal_row({
        "ticker": "TSLA",
        "signal": 1,
        "signal_label": "buy",
        "strategy": "rsi",
        "sentiment_score": 0.10,
        "filtered": True,
        "filter_reason": "low_sentiment",
    })
    assert "[low_sentiment]" in row


# ── _load_watchlists ───────────────────────────────────────────────────────────

def test_load_watchlists_missing_file(tmp_path):
    mod = _import()
    with patch.object(mod, "WATCHLISTS_PATH", tmp_path / "nope.json"):
        result = mod._load_watchlists()
    assert result == {}


def test_load_watchlists_existing(tmp_path):
    mod = _import()
    data = {"default": ["NVDA", "AAPL"], "tr-portfolio": ["ASML"]}
    wl_file = tmp_path / "watchlists.json"
    wl_file.write_text(json.dumps(data))
    with patch.object(mod, "WATCHLISTS_PATH", wl_file):
        result = mod._load_watchlists()
    assert result == data


# ── _run_signals ───────────────────────────────────────────────────────────────

def test_run_signals_subprocess_failure():
    mod = _import()
    fake_result = MagicMock()
    fake_result.returncode = 1
    fake_result.stderr = "some error"
    with patch("subprocess.run", return_value=fake_result):
        result = mod._run_signals(["NVDA", "AAPL"])
    assert result == []


# ── _build_message ─────────────────────────────────────────────────────────────

def test_build_message_all_empty_returns_none():
    mod = _import()
    assert mod._build_message({}) is None
    assert mod._build_message({"default": []}) is None


def test_build_message_groups_buy_sell_hold():
    mod = _import()
    signals = [
        {"ticker": "NVDA", "signal": 1,  "signal_label": "buy",  "strategy": "rsi",  "sentiment_score": 0.5,  "filtered": False},
        {"ticker": "ASML", "signal": -1, "signal_label": "sell", "strategy": "macd", "sentiment_score": -0.3, "filtered": False},
        {"ticker": "AAPL", "signal": 0,  "signal_label": "hold", "strategy": "rsi",  "sentiment_score": None, "filtered": False},
    ]
    with patch.object(mod, "_run_signals", return_value=signals):
        msg = mod._build_message({"default": ["NVDA", "ASML", "AAPL"]})
    assert msg is not None
    assert "BUY" in msg
    assert "SELL" in msg
    assert "HOLD" in msg
    assert "*default*" in msg


def test_build_message_skips_empty_lists():
    mod = _import()
    signals = [
        {"ticker": "NVDA", "signal": 1, "signal_label": "buy", "strategy": "rsi", "sentiment_score": 0.4, "filtered": False},
    ]

    def fake_run_signals(tickers):
        if tickers == ["NVDA"]:
            return signals
        return []

    with patch.object(mod, "_run_signals", side_effect=fake_run_signals):
        msg = mod._build_message({"active": ["NVDA"], "empty-list": []})
    assert msg is not None
    assert "*active*" in msg
    assert "empty-list" not in msg


def test_build_message_handles_ticker_error():
    mod = _import()
    signals = [
        {"ticker": "NVDA", "signal": 1, "signal_label": "buy", "strategy": "rsi", "sentiment_score": 0.5, "filtered": False},
        {"ticker": "FAIL", "error": "timeout fetching data"},
    ]
    with patch.object(mod, "_run_signals", return_value=signals):
        # Must not raise KeyError
        msg = mod._build_message({"default": ["NVDA", "FAIL"]})
    assert msg is not None
    assert "ERR" in msg
    assert "FAIL" in msg
