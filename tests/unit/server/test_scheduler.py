import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


SAMPLE_CRONS = [
    {
        "id": "eu-pre-market",
        "cron": "3 8 * * 1-5",
        "label": "EU pre-market",
        "agent": "portfolio-conductor",
        "slot": "eu-pre-market",
        "prompt": "Run EU pre-market analysis.",
    },
    {
        "id": "ibkr-healthcheck",
        "cron": "*/5 * * * *",
        "label": "IBKR health check",
        "agent": "system",
        "cmd": "uv run python scripts/ibkr-healthcheck.py",
        "prompt": "Run health check.",
    },
]


def test_load_crons_parses_correctly(tmp_path):
    from trader.server.scheduler import load_crons

    crons_file = tmp_path / "crons.json"
    crons_file.write_text(json.dumps(SAMPLE_CRONS))
    jobs = load_crons(crons_file)
    assert len(jobs) == 2
    assert jobs[0]["id"] == "eu-pre-market"
    assert jobs[1]["id"] == "ibkr-healthcheck"


def test_is_agent_job():
    from trader.server.scheduler import is_agent_job

    assert is_agent_job({"agent": "portfolio-conductor"}) is True
    assert is_agent_job({"agent": "system"}) is False


def test_build_scheduler_registers_jobs(tmp_path):
    from trader.server.scheduler import build_scheduler

    crons_file = tmp_path / "crons.json"
    crons_file.write_text(json.dumps(SAMPLE_CRONS))

    with patch("trader.server.scheduler.run_job", new_callable=AsyncMock):
        scheduler = build_scheduler(crons_path=crons_file)
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert "eu-pre-market" in job_ids
        assert "ibkr-healthcheck" in job_ids
