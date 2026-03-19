# tests/unit/server/test_scheduler_timeout.py
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_agent_job_times_out_and_logs():
    """_run_agent_job cancels when job exceeds timeout_minutes and calls _log_timeout_error."""
    from trader.server.scheduler import _run_agent_job

    job = {"id": "test-slow-agent", "prompt": "do something", "slot": "test",
           "timeout_minutes": 0.001}

    async def slow_run(*args, **kwargs):
        await asyncio.sleep(10)

    with patch("trader.server.scheduler.run_job", side_effect=slow_run), \
         patch("trader.server.scheduler._log_timeout_error") as mock_log:
        await _run_agent_job(job)

    mock_log.assert_called_once_with("test-slow-agent", pytest.approx(0.001, abs=0.005))


@pytest.mark.asyncio
async def test_agent_job_completes_within_timeout():
    """_run_agent_job with adequate timeout completes without logging error."""
    from trader.server.scheduler import _run_agent_job

    job = {"id": "test-fast-agent", "prompt": "quick task", "slot": "test",
           "timeout_minutes": 1}
    fast_run = AsyncMock()
    with patch("trader.server.scheduler.run_job", fast_run), \
         patch("trader.server.scheduler._log_timeout_error") as mock_log:
        await _run_agent_job(job)

    fast_run.assert_awaited_once()
    mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_agent_job_uses_default_timeout_when_not_specified():
    """_run_agent_job with no timeout_minutes uses _DEFAULT_AGENT_TIMEOUT_MINUTES."""
    from trader.server import scheduler as sched_module
    from trader.server.scheduler import _run_agent_job

    job = {"id": "test-default", "prompt": "task", "slot": "test"}
    captured = {}

    async def record_timeout(*args, timeout, **kwargs):
        captured["timeout"] = timeout

    with patch("asyncio.wait_for", side_effect=record_timeout):
        with patch("trader.server.scheduler.run_job", new_callable=AsyncMock):
            try:
                await _run_agent_job(job)
            except TypeError:
                pass  # record_timeout returns None, not a coroutine — expected

    assert captured.get("timeout") == sched_module._DEFAULT_AGENT_TIMEOUT_MINUTES * 60


@pytest.mark.asyncio
async def test_script_job_times_out_kills_process():
    """_run_script_job kills subprocess and calls _log_timeout_error on timeout."""
    from trader.server.scheduler import _run_script_job

    job = {"id": "test-slow-script", "cmd": "sleep 60",
           "timeout_minutes": 0.01}  # 0.6s — enough for subprocess to start

    with patch("trader.server.scheduler._log_timeout_error") as mock_log:
        await _run_script_job(job)

    mock_log.assert_called_once_with("test-slow-script", pytest.approx(0.01, abs=0.005))
