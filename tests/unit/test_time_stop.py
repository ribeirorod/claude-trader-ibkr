import json
import tempfile
from datetime import datetime
from pathlib import Path

from trader.models import Position
from trader.risk.time_stop import TimeStopResult, check_time_stops, log_time_stop_review


def make_position(ticker="AAPL", qty=10, avg_cost=150.0, unrealized_pnl=-45.0):
    return Position(
        ticker=ticker,
        qty=qty,
        avg_cost=avg_cost,
        market_value=qty * avg_cost,
        unrealized_pnl=unrealized_pnl,
    )


def write_agent_log(path: Path, entries: list[dict]):
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def make_order_intent(ticker: str, ts: str) -> dict:
    return {
        "ts": ts,
        "run_id": "test-run",
        "agent": "pipeline",
        "event": "ORDER_INTENT",
        "ticker": ticker,
        "side": "buy",
        "qty": 10,
    }


# ── Trading day calculation ───────────────────────────────────────────────


def test_trading_days_weekdays_only():
    """A position opened on Monday, checked on next Monday = 5 trading days."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        # Monday 2026-03-23
        write_agent_log(log_path, [make_order_intent("AAPL", "2026-03-23T09:30:00")])
        positions = [make_position("AAPL")]
        # Check on Monday 2026-03-30 -> 5 trading days (Mon-Fri)
        results = check_time_stops(
            positions=positions,
            regime="bull",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 1
        assert results[0].days_held == 5


def test_trading_days_excludes_weekends():
    """Friday to Monday = 1 trading day, not 3 calendar days."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        # Friday 2026-03-27
        write_agent_log(log_path, [make_order_intent("AAPL", "2026-03-27T09:30:00")])
        positions = [make_position("AAPL")]
        # Check on Monday 2026-03-30 -> 1 trading day
        results = check_time_stops(
            positions=positions,
            regime="bull",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 1
        assert results[0].days_held == 1


# ── Regime-based thresholds ───────────────────────────────────────────────


def test_bull_regime_under_threshold_ok():
    """Position held 5 days in bull regime (max 20) -> action='ok'."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        write_agent_log(log_path, [make_order_intent("AAPL", "2026-03-23T09:30:00")])
        positions = [make_position("AAPL")]
        results = check_time_stops(
            positions=positions,
            regime="bull",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 1
        assert results[0].action == "ok"
        assert results[0].max_days == 20


def test_bear_regime_over_threshold_review():
    """Position held 12 trading days in bear regime (max 10) -> action='review'."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        write_agent_log(log_path, [make_order_intent("AAPL", "2026-03-12T09:30:00")])
        positions = [make_position("AAPL", unrealized_pnl=-45.0)]
        results = check_time_stops(
            positions=positions,
            regime="bear",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 1
        assert results[0].action == "review"
        assert results[0].days_held == 12
        assert results[0].max_days == 10
        assert results[0].unrealized_pnl == -45.0


def test_caution_regime_threshold():
    """Caution regime uses 15-day default threshold."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        write_agent_log(log_path, [make_order_intent("MSFT", "2026-03-23T09:30:00")])
        positions = [make_position("MSFT")]
        results = check_time_stops(
            positions=positions,
            regime="caution",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 1
        assert results[0].max_days == 15
        assert results[0].action == "ok"


# ── Edge cases ────────────────────────────────────────────────────────────


def test_no_matching_entry_skipped():
    """Position with no ORDER_INTENT in agent.jsonl is skipped."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        write_agent_log(log_path, [make_order_intent("AAPL", "2026-03-23T09:30:00")])
        positions = [make_position("MSFT")]
        results = check_time_stops(
            positions=positions,
            regime="bull",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 0


def test_empty_agent_log():
    """Empty agent.jsonl -> no results, no crash."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        log_path.write_text("")
        positions = [make_position("AAPL")]
        results = check_time_stops(
            positions=positions,
            regime="bull",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 0


def test_missing_agent_log_file():
    """Missing agent.jsonl file -> no results, no crash."""
    positions = [make_position("AAPL")]
    results = check_time_stops(
        positions=positions,
        regime="bull",
        agent_log_path=Path("/nonexistent/agent.jsonl"),
        today=datetime(2026, 3, 30),
    )
    assert len(results) == 0


def test_multiple_order_intents_uses_earliest():
    """If multiple ORDER_INTENT for same ticker, use the earliest."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        write_agent_log(log_path, [
            make_order_intent("AAPL", "2026-03-10T09:30:00"),
            make_order_intent("AAPL", "2026-03-20T09:30:00"),
        ])
        positions = [make_position("AAPL")]
        results = check_time_stops(
            positions=positions,
            regime="bull",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
        )
        assert len(results) == 1
        assert results[0].entry_date == "2026-03-10"
        assert results[0].days_held == 14


def test_multiple_positions():
    """Multiple positions: each checked independently."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        write_agent_log(log_path, [
            make_order_intent("AAPL", "2026-03-23T09:30:00"),
            make_order_intent("MSFT", "2026-03-10T09:30:00"),
        ])
        positions = [
            make_position("AAPL", unrealized_pnl=100.0),
            make_position("MSFT", unrealized_pnl=-30.0),
        ]
        results = check_time_stops(
            positions=positions,
            regime="bear",
            agent_log_path=log_path,
            today=datetime(2026, 3, 30),
            bear_max_days=10,
        )
        assert len(results) == 2
        aapl = next(r for r in results if r.ticker == "AAPL")
        msft = next(r for r in results if r.ticker == "MSFT")
        assert aapl.action == "ok"
        assert msft.action == "review"


# ── Logging tests ────────────────────────────────────────────────────────


def test_log_time_stop_review_appends_jsonl():
    """log_time_stop_review appends a valid JSONL entry to agent.jsonl."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "logs" / "agent.jsonl"
        result = TimeStopResult(
            ticker="AAPL",
            days_held=12,
            max_days=10,
            entry_date="2026-03-12",
            unrealized_pnl=-45.0,
            action="review",
        )
        log_time_stop_review(result, log_path)

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "TIME_STOP_REVIEW"
        assert entry["agent"] == "time-stop"
        assert entry["ticker"] == "AAPL"
        assert entry["days_held"] == 12
        assert entry["max_days"] == 10
        assert entry["unrealized_pnl"] == -45.0
        assert entry["action"] == "review"
        assert "ts" in entry


def test_log_time_stop_review_appends_to_existing():
    """log_time_stop_review appends (does not overwrite) existing entries."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "agent.jsonl"
        log_path.write_text('{"event": "existing"}\n')

        result = TimeStopResult(
            ticker="MSFT",
            days_held=5,
            max_days=20,
            entry_date="2026-03-23",
            unrealized_pnl=100.0,
            action="ok",
        )
        log_time_stop_review(result, log_path)

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "existing"
        assert json.loads(lines[1])["event"] == "TIME_STOP_REVIEW"


def test_log_creates_parent_directories():
    """log_time_stop_review creates parent dirs if they don't exist."""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "deep" / "nested" / "agent.jsonl"
        result = TimeStopResult(
            ticker="AAPL", days_held=5, max_days=20,
            entry_date="2026-03-23", unrealized_pnl=0.0, action="ok",
        )
        log_time_stop_review(result, log_path)
        assert log_path.exists()
