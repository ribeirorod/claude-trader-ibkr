"""Tests for scripts/watchlist-signals.py _build_message formatting."""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path


def _load_module():
    spec = _ilu.spec_from_file_location(
        "watchlist_signals",
        Path(__file__).parents[2] / "scripts" / "watchlist-signals.py",
    )
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()


# ── _build_message ─────────────────────────────────────────────────────────────

def test_build_message_empty_returns_none():
    assert _mod._build_message({"total_candidates": 0, "sectors": {}}) is None


def test_build_message_summary_line():
    cs = {
        "regime": "bear",
        "total_candidates": 5,
        "watchlist_count": 3,
        "discovery_count": 2,
        "sectors": {"Tech": [{"ticker": "AAPL", "source": "watchlist", "news": []}]},
        "ticker_sentiment": {},
    }
    msg = _mod._build_message(cs)
    assert msg is not None
    assert "BEAR" in msg
    assert "5 candidates" in msg
    assert "3 WL + 2 scan" in msg


def test_build_message_shows_movers_with_sentiment():
    cs = {
        "regime": "bull",
        "total_candidates": 2,
        "watchlist_count": 2,
        "discovery_count": 0,
        "sectors": {
            "Tech": [
                {"ticker": "MSFT", "source": "watchlist", "news": ["headline1", "headline2"]},
                {"ticker": "AAPL", "source": "watchlist", "news": []},
            ],
        },
        "ticker_sentiment": {"MSFT": -0.28, "AAPL": 0.0},
    }
    msg = _mod._build_message(cs)
    assert "Movers" in msg
    assert "MSFT" in msg
    assert "-0.28" in msg
    # AAPL has 0.0 sentiment and no news — should NOT appear in movers
    assert "AAPL" not in msg


def test_build_message_shows_news_tickers():
    cs = {
        "regime": "caution",
        "total_candidates": 1,
        "watchlist_count": 1,
        "discovery_count": 0,
        "sectors": {
            "Mining": [
                {"ticker": "AAL", "source": "watchlist", "news": ["some headline"]},
            ],
        },
        "ticker_sentiment": {"AAL": 0.0},
    }
    msg = _mod._build_message(cs)
    # AAL has news even though sentiment is 0.0
    assert "AAL" in msg
    assert "(1n)" in msg


def test_build_message_sector_counts():
    cs = {
        "regime": "bull",
        "total_candidates": 6,
        "watchlist_count": 0,
        "discovery_count": 6,
        "sectors": {
            "Gold Mining": [
                {"ticker": "GGP", "source": "scan", "news": []},
                {"ticker": "CDE", "source": "scan", "news": []},
                {"ticker": "AG", "source": "scan", "news": []},
            ],
            "Oil": [
                {"ticker": "PBR", "source": "scan", "news": []},
            ],
            "Tech": [
                {"ticker": "MSFT", "source": "scan", "news": []},
                {"ticker": "AAPL", "source": "scan", "news": []},
            ],
        },
        "ticker_sentiment": {},
    }
    msg = _mod._build_message(cs)
    assert "Sectors" in msg
    assert "Gold Mining (3)" in msg
    assert "Tech (2)" in msg
    assert "Oil (1)" in msg


def test_build_message_skips_unknown_sector():
    cs = {
        "regime": "bull",
        "total_candidates": 3,
        "watchlist_count": 3,
        "discovery_count": 0,
        "sectors": {
            "Unknown": [
                {"ticker": "ARMR", "source": "watchlist", "news": []},
                {"ticker": "BA.", "source": "watchlist", "news": []},
                {"ticker": "RHM", "source": "watchlist", "news": []},
            ],
        },
        "ticker_sentiment": {},
    }
    msg = _mod._build_message(cs)
    # "Unknown" sector should not appear in sector counts
    assert "Unknown" not in msg


def test_build_message_limits_movers_to_15():
    candidates = [{"ticker": f"T{i}", "source": "scan", "news": []} for i in range(20)]
    # All sentiment values have abs > 0.05 so all qualify as movers
    sentiment = {f"T{i}": 0.5 + i * 0.01 for i in range(20)}
    cs = {
        "regime": "bull",
        "total_candidates": 20,
        "watchlist_count": 0,
        "discovery_count": 20,
        "sectors": {"Tech": candidates},
        "ticker_sentiment": sentiment,
    }
    msg = _mod._build_message(cs)
    assert "+5 more" in msg


def test_build_message_uses_html():
    cs = {
        "regime": "bear",
        "total_candidates": 1,
        "watchlist_count": 1,
        "discovery_count": 0,
        "sectors": {"Tech": [{"ticker": "MSFT", "source": "watchlist", "news": []}]},
        "ticker_sentiment": {"MSFT": -0.5},
    }
    msg = _mod._build_message(cs)
    assert "<b>" in msg
    assert "<pre>" in msg
    # Should NOT use Markdown syntax
    assert "```" not in msg
