from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(".trader/logs/agent.jsonl")


@dataclass
class LogEvent:
    run_id: str
    agent: str
    event: str
    data: dict[str, Any] = field(default_factory=dict)


class AgentLog:
    def __init__(self, path: Path = DEFAULT_LOG_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: LogEvent) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": event.run_id,
            "agent": event.agent,
            "event": event.event,
            "context": event.data,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_last(self, n: int) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().strip().splitlines()
        if not lines:
            return []
        tail = lines[-n:] if len(lines) >= n else lines
        return [json.loads(line) for line in tail]

    @staticmethod
    def new_run_id() -> str:
        return uuid.uuid4().hex[:8]
