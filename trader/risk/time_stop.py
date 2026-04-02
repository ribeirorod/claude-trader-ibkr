from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from trader.models import Position


@dataclass
class TimeStopResult:
    ticker: str
    days_held: int
    max_days: int
    entry_date: str
    unrealized_pnl: float | None
    action: str  # "review" | "ok"


def _count_trading_days(start: datetime, end: datetime) -> int:
    """Count weekdays (Mon-Fri) between start (exclusive) and end (inclusive).

    Both start and end are normalized to dates (time-of-day is ignored).
    """
    start_date = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end.replace(hour=0, minute=0, second=0, microsecond=0)
    if end_date <= start_date:
        return 0
    count = 0
    current = start_date + timedelta(days=1)
    while current <= end_date:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _parse_entry_dates(agent_log_path: Path) -> dict[str, datetime]:
    """Parse agent.jsonl and return earliest ORDER_INTENT datetime per ticker."""
    entries: dict[str, datetime] = {}
    if not agent_log_path.exists():
        return entries
    for line in agent_log_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") != "ORDER_INTENT":
            continue
        ticker = record.get("ticker")
        ts_str = record.get("ts")
        if not ticker or not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            continue
        if ticker not in entries or ts < entries[ticker]:
            entries[ticker] = ts
    return entries


def check_time_stops(
    positions: list[Position],
    regime: str,
    agent_log_path: Path,
    bull_max_days: int = 20,
    bear_max_days: int = 10,
    caution_max_days: int = 15,
    today: datetime | None = None,
) -> list[TimeStopResult]:
    """Check all positions against regime-dependent time-stop thresholds."""
    if today is None:
        today = datetime.now()

    max_days_map = {
        "bull": bull_max_days,
        "caution": caution_max_days,
        "bear": bear_max_days,
    }
    max_days = max_days_map.get(regime, caution_max_days)

    entry_dates = _parse_entry_dates(agent_log_path)

    results: list[TimeStopResult] = []
    for pos in positions:
        entry_dt = entry_dates.get(pos.ticker)
        if entry_dt is None:
            continue
        days_held = _count_trading_days(entry_dt, today)
        action = "review" if days_held > max_days else "ok"
        results.append(TimeStopResult(
            ticker=pos.ticker,
            days_held=days_held,
            max_days=max_days,
            entry_date=entry_dt.strftime("%Y-%m-%d"),
            unrealized_pnl=pos.unrealized_pnl,
            action=action,
        ))
    return results


def log_time_stop_review(result: TimeStopResult, agent_log_path: Path) -> None:
    """Append a TIME_STOP_REVIEW event to agent.jsonl for a flagged position."""
    agent_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "agent": "time-stop",
        "event": "TIME_STOP_REVIEW",
        "ticker": result.ticker,
        "days_held": result.days_held,
        "max_days": result.max_days,
        "unrealized_pnl": result.unrealized_pnl,
        "action": result.action,
    }
    with open(agent_log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
