"""Trader server entry point — wires FastAPI + APScheduler + Telegram polling."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from trader.server.app import create_app
from trader.server.scheduler import build_scheduler
from trader.server.telegram import build_telegram_app

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def _configure_logging() -> None:
    level = logging.DEBUG if os.getenv("IBKR_MODE", "paper") == "paper" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s  %(message)s",
    )


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
    log.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))

    # 2. FastAPI
    app = create_app(scheduler=scheduler)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=int(os.getenv("SERVER_PORT", "8080")),
        log_level="debug" if is_paper else "info",
        reload=False,  # reload not compatible with programmatic uvicorn.Server
    )
    server = uvicorn.Server(config)

    # 3. Telegram
    tg_app = build_telegram_app()
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram polling started")

    # 4. Run until interrupted
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    server_task = asyncio.create_task(server.serve())

    try:
        await stop_event.wait()
    finally:
        log.info("Shutting down...")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        scheduler.shutdown(wait=False)
        server.should_exit = True
        await server_task
        log.info("Shutdown complete")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
