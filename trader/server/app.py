from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI


def create_app(scheduler: Any = None) -> FastAPI:
    app = FastAPI(title="Trader Server", version="0.1.0")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/status")
    async def status() -> dict:
        sched_running = getattr(scheduler, "running", False)
        jobs: list[dict] = []
        if scheduler and sched_running:
            jobs = [
                {"id": j.id, "next_run": str(j.next_run_time)}
                for j in scheduler.get_jobs()
            ]
        return {
            "scheduler": "running" if sched_running else "stopped",
            "jobs": jobs,
            "ibkr_mode": os.getenv("IBKR_MODE", "paper"),
        }

    return app
