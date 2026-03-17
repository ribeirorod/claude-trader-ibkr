"""Trader server entry point — wires FastAPI + APScheduler + Telegram polling."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import structlog
import uvicorn
from dotenv import load_dotenv

from trader.server.app import create_app
from trader.server.scheduler import build_scheduler
from trader.server.telegram import build_telegram_app

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent

_NOISY_LOGGERS = [
    "httpcore",
    "httpx",
    "telegram.ext.ExtBot",
    "telegram.ext.Updater",
    "telegram.ext",
    "apscheduler.executors",
    "apscheduler.scheduler",
    "uvicorn.access",
    "claude_agent_sdk",
]


def _configure_logging() -> None:
    is_paper = os.getenv("IBKR_MODE", "paper") == "paper"
    root_level = logging.DEBUG if is_paper else logging.INFO

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(root_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Bridge stdlib logging (uvicorn, APScheduler, PTB) through structlog renderer
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(root_level)

    # Silence chatty third-party loggers
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


async def _run() -> None:
    # Force Claude Code OAuth — remove API key from process env before SDK is used
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("CLAUDECODE", None)

    load_dotenv(ROOT / ".env")
    _configure_logging()
    is_paper = os.getenv("IBKR_MODE", "paper") == "paper"

    # 1. Scheduler
    scheduler = build_scheduler()
    scheduler.start()
    log.info("scheduler_ready", job_count=len(scheduler.get_jobs()), mode="paper" if is_paper else "live")

    # 2. FastAPI
    app = create_app(scheduler=scheduler)
    port = int(os.getenv("SERVER_PORT", "9090"))
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",   # uvicorn access logs silenced; structlog handles startup msgs
        reload=False,
    )
    server = uvicorn.Server(config)

    # 3. Telegram
    tg_app = build_telegram_app()
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("telegram_ready", status="polling")

    log.info("server_ready", host="0.0.0.0", port=port, mode="paper" if is_paper else "live")

    # 4. Run until interrupted
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("signal_received", action="shutdown")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    server_task = asyncio.create_task(server.serve())

    try:
        await stop_event.wait()
    finally:
        log.info("shutdown_started")
        for coro in (tg_app.updater.stop, tg_app.stop, tg_app.shutdown):
            try:
                await coro()
            except Exception as exc:
                log.debug("shutdown_step_error", step=coro.__name__, error=str(exc))
        scheduler.shutdown(wait=False)
        server.should_exit = True
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, SystemExit, Exception):
            pass
        log.info("shutdown_complete")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
