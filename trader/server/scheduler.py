from __future__ import annotations

import asyncio
import json
import shlex
import time
from pathlib import Path
from typing import Literal

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trader.notify import send_telegram
from trader.server.agent import run_job

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CRONS_PATH = ROOT / ".claude" / "crons.json"

# Jobs that run too frequently for completion notifications
_SILENT_JOBS = {"ibkr-healthcheck"}


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs:02d}s" if secs else f"{minutes}m"


async def _notify_cron_result(
    job_id: str,
    status: Literal["ok", "timeout", "error"],
    elapsed_s: float,
    error: str | None = None,
) -> None:
    """Send a Telegram notification when a cron job finishes."""
    if job_id in _SILENT_JOBS:
        return
    if status == "ok":
        msg = f"Cron <b>{job_id}</b> finished in {_fmt_elapsed(elapsed_s)}"
    elif status == "timeout":
        msg = f"Cron <b>{job_id}</b> timed out after {_fmt_elapsed(elapsed_s)}"
    elif status == "error":
        reason = (error or "unknown")[:120]
        msg = f"Cron <b>{job_id}</b> failed after {_fmt_elapsed(elapsed_s)} — {reason}"
    else:
        return
    await asyncio.to_thread(send_telegram, msg)


def load_crons(crons_path: Path = DEFAULT_CRONS_PATH) -> list[dict]:
    """Load and return all job definitions from crons.json."""
    return json.loads(crons_path.read_text())


def is_agent_job(job: dict) -> bool:
    """Return True if this job should be dispatched to the claude-agent-sdk."""
    return job.get("agent", "system") != "system"


# Default timeouts — override per-job via "timeout_minutes" in crons.json
_DEFAULT_AGENT_TIMEOUT_MINUTES: float = 15.0
_DEFAULT_SCRIPT_TIMEOUT_MINUTES: float = 5.0


def _log_timeout_error(job_id: str, timeout_minutes: float) -> None:
    """Centralised timeout logging — also called from tests."""
    log.error("cron_timeout", job=job_id, timeout_minutes=timeout_minutes)


async def _run_agent_job(job: dict) -> None:
    jid = job["id"]
    timeout_min = float(job.get("timeout_minutes", _DEFAULT_AGENT_TIMEOUT_MINUTES))
    log.info("cron_start", job=jid, type="agent", timeout_minutes=timeout_min)
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(
            run_job(prompt=job["prompt"], slot=job.get("slot", jid)),
            timeout=timeout_min * 60,
        )
        elapsed = round(time.monotonic() - t0, 1)
        log.info("cron_done", job=jid, type="agent", elapsed_s=elapsed)
        await _notify_cron_result(jid, "ok", elapsed)
    except asyncio.TimeoutError:
        _log_timeout_error(jid, timeout_min)
        await _notify_cron_result(jid, "timeout", timeout_min * 60)
    except Exception as exc:
        elapsed = round(time.monotonic() - t0, 1)
        log.error("cron_error", job=jid, type="agent", error=str(exc))
        await _notify_cron_result(jid, "error", elapsed, str(exc))
        raise


async def _run_script_job(job: dict) -> None:
    jid = job["id"]
    cmd = job["cmd"]
    timeout_min = float(job.get("timeout_minutes", _DEFAULT_SCRIPT_TIMEOUT_MINUTES))
    log.info("cron_start", job=jid, type="script", cmd=cmd, timeout_minutes=timeout_min)
    t0 = time.monotonic()
    args = shlex.split(cmd)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_min * 60
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        _log_timeout_error(jid, timeout_min)
        await _notify_cron_result(jid, "timeout", timeout_min * 60)
        return

    elapsed = round(time.monotonic() - t0, 1)
    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace")[:300]
        log.error("cron_error", job=jid, type="script", rc=proc.returncode,
                  elapsed_s=elapsed, stderr=err_msg)
        await _notify_cron_result(jid, "error", elapsed, err_msg.split("\n")[-1][:120])
    else:
        log.info("cron_done", job=jid, type="script", elapsed_s=elapsed)
        await _notify_cron_result(jid, "ok", elapsed)


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
