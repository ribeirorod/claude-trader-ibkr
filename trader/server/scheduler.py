from __future__ import annotations

import asyncio
import json
import logging
import shlex
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.server.agent import run_job

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CRONS_PATH = ROOT / ".claude" / "crons.json"


def load_crons(crons_path: Path = DEFAULT_CRONS_PATH) -> list[dict]:
    """Load and return all job definitions from crons.json."""
    return json.loads(crons_path.read_text())


def is_agent_job(job: dict) -> bool:
    """Return True if this job should be dispatched to the claude-agent-sdk."""
    return job.get("agent", "system") != "system"


async def _run_agent_job(job: dict) -> None:
    await run_job(prompt=job["prompt"], slot=job.get("slot", job["id"]))


async def _run_script_job(job: dict) -> None:
    cmd = job["cmd"]
    log.info("scheduler: running script job id=%s cmd=%s", job["id"], cmd)
    args = shlex.split(cmd)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        log.error(
            "scheduler: script job failed id=%s rc=%d stderr=%s",
            job["id"],
            proc.returncode,
            stderr.decode(errors="replace")[:500],
        )
    else:
        log.info("scheduler: script job done id=%s", job["id"])


def build_scheduler(crons_path: Path = DEFAULT_CRONS_PATH) -> AsyncIOScheduler:
    """Create, populate, and return an AsyncIOScheduler (not yet started)."""
    scheduler = AsyncIOScheduler()
    jobs = load_crons(crons_path)

    for job in jobs:
        trigger = CronTrigger.from_crontab(job["cron"])
        if is_agent_job(job):
            scheduler.add_job(
                _run_agent_job,
                trigger=trigger,
                args=[job],
                id=job["id"],
                replace_existing=True,
            )
        else:
            scheduler.add_job(
                _run_script_job,
                trigger=trigger,
                args=[job],
                id=job["id"],
                replace_existing=True,
            )
        log.info("scheduler: registered %s [%s]", job["id"], job["cron"])

    return scheduler
