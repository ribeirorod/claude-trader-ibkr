from __future__ import annotations

import asyncio
import json
import shlex
import time
from pathlib import Path

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.server.agent import run_job

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CRONS_PATH = ROOT / ".claude" / "crons.json"


def load_crons(crons_path: Path = DEFAULT_CRONS_PATH) -> list[dict]:
    """Load and return all job definitions from crons.json."""
    return json.loads(crons_path.read_text())


def is_agent_job(job: dict) -> bool:
    """Return True if this job should be dispatched to the claude-agent-sdk."""
    return job.get("agent", "system") != "system"


async def _run_agent_job(job: dict) -> None:
    jid = job["id"]
    log.info("cron_start", job=jid, type="agent")
    t0 = time.monotonic()
    try:
        await run_job(prompt=job["prompt"], slot=job.get("slot", jid))
        log.info("cron_done", job=jid, type="agent", elapsed_s=round(time.monotonic() - t0, 1))
    except Exception as exc:
        log.error("cron_error", job=jid, type="agent", error=str(exc))
        raise


async def _run_script_job(job: dict) -> None:
    jid = job["id"]
    cmd = job["cmd"]
    log.info("cron_start", job=jid, type="script", cmd=cmd)
    t0 = time.monotonic()
    args = shlex.split(cmd)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    elapsed = round(time.monotonic() - t0, 1)
    if proc.returncode != 0:
        log.error(
            "cron_error",
            job=jid,
            type="script",
            rc=proc.returncode,
            elapsed_s=elapsed,
            stderr=stderr.decode(errors="replace")[:300],
        )
    else:
        log.info("cron_done", job=jid, type="script", elapsed_s=elapsed)


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
        log.debug("cron_registered", job=job["id"], cron=job["cron"])

    return scheduler
