#!/usr/bin/env python3
"""
IBKR session health checker.

Polls the Client Portal Gateway auth status every run.
- If authenticated: sends a /tickle to keep the session alive.
- If unauthenticated: sends a Telegram alert and triggers ibkr-reauth.py.
Designed to be run on a schedule (every 5 min).
"""
from __future__ import annotations
import ssl
import sys
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Load .env from project root (two levels up from scripts/)
ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        import os
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

import os
import structlog
sys.path.insert(0, str(ROOT))
from trader.notify import send_telegram

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger("ibkr-health")

GATEWAY_URL = os.getenv("IBEAM_GATEWAY_BASE_URL", "https://localhost:5001")
IBKR_MODE = os.getenv("IBKR_MODE", "paper")
AUTH_ENDPOINT = f"{GATEWAY_URL}/v1/api/iserver/auth/status"
TICKLE_ENDPOINT = f"{GATEWAY_URL}/v1/api/tickle"

# State file — prevents spamming Telegram on every check when already alerted
STATE_FILE = ROOT / ".trader" / "ibkr-health.state"
# Failure counter — triggers full gateway restart after threshold
FAILURE_COUNT_FILE = ROOT / ".trader" / "ibkr-health-failures.txt"
GATEWAY_RESTART_THRESHOLD = 20  # 20 × 5 min = 100 min of consecutive failures


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def check_auth() -> bool:
    """Returns True if IBKR session is authenticated."""
    try:
        req = urllib.request.Request(AUTH_ENDPOINT)
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx()) as resp:
            data = json.loads(resp.read())
            authenticated = data.get("authenticated", False)
            log.info("ibkr_auth_status", authenticated=authenticated, competing=data.get("competing"), connected=data.get("connected"))
            return bool(authenticated)
    except urllib.error.URLError as exc:
        log.warning("ibkr_gateway_unreachable", error=str(exc))
        return False
    except Exception as exc:
        log.error("ibkr_health_check_error", error=str(exc))
        return False


def tickle() -> None:
    """Send /tickle to keep the session alive."""
    try:
        req = urllib.request.Request(TICKLE_ENDPOINT, method="POST")
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx()) as resp:
            log.info("ibkr_tickle_sent", status=resp.status)
    except Exception as exc:
        log.warning("ibkr_tickle_failed", error=str(exc))


def last_alert_state() -> str:
    """Returns 'alerted' or 'ok'."""
    try:
        return STATE_FILE.read_text().strip()
    except FileNotFoundError:
        return "ok"


def set_alert_state(state: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(state)


def get_failure_count() -> int:
    try:
        return int(FAILURE_COUNT_FILE.read_text().strip())
    except Exception:
        return 0


def set_failure_count(n: int) -> None:
    FAILURE_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAILURE_COUNT_FILE.write_text(str(n))


def _tmux_session_exists(name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def trigger_gateway_restart() -> None:
    """Restart the IBKR Client Portal Gateway in a persistent tmux session.

    Always checks `tmux ls` first to avoid duplicate sessions.
    Kills stale ibkr-gateway session only when the gateway is confirmed unreachable.
    """
    gateway_dir = ROOT / "clientportal.gw"
    run_sh = gateway_dir / "bin" / "run.sh"
    if not run_sh.exists():
        log.warning("clientportal.gw/bin/run.sh not found — skipping gateway restart.")
        return

    # Log all current tmux sessions for diagnostics
    result = subprocess.run(["tmux", "ls"], capture_output=True, text=True)
    log.info("tmux_sessions", sessions=result.stdout.strip() or "(none)")

    if _tmux_session_exists("ibkr-gateway"):
        log.info("ibkr_gateway_killing_stale_session")
        subprocess.run(["tmux", "kill-session", "-t", "ibkr-gateway"], capture_output=True)

    log.info("ibkr_gateway_starting", script="clientportal.gw/bin/run.sh")
    subprocess.run(["tmux", "new-session", "-d", "-s", "ibkr-gateway", "-x", "220", "-y", "50"])
    subprocess.run([
        "tmux", "send-keys", "-t", "ibkr-gateway",
        f"cd '{gateway_dir}' && bash bin/run.sh root/conf.yaml", "Enter",
    ])
    mode_label = "📄 Paper" if IBKR_MODE == "paper" else "💼 Live"
    send_telegram(
        f"🔄 <b>IBKR gateway restarting</b> — {mode_label}\n\n"
        "Session was down 100+ min. Restarting via <code>clientportal.gw/bin/run.sh</code>.\n"
        "<i>Authentication will follow on the next cycle.</i>"
    )
    log.info("ibkr_gateway_restart_initiated", tmux_session="ibkr-gateway")


def trigger_reauth() -> None:
    """Launch ibkr-start.sh --auth-only in the background.

    Uses ibkr-start.sh (not ibkr-reauth.py directly) so that the protected
    process list is always checked and the gateway process is never disrupted.
    """
    start_script = ROOT / "scripts" / "ibkr-start.sh"
    if not start_script.exists():
        log.warning("ibkr-start.sh not found — skipping auto-reauth.")
        return
    log.info("ibkr_reauth_triggering")
    subprocess.Popen(
        ["bash", str(start_script), "--auth-only"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    authenticated = check_auth()

    if authenticated:
        log.info("ibkr_session_ok", mode=IBKR_MODE)
        tickle()
        set_failure_count(0)
        if last_alert_state() == "alerted":
            mode_label = "📄 Paper" if IBKR_MODE == "paper" else "💼 Live"
            send_telegram(f"✅ <b>IBKR session restored</b> — {mode_label} gateway is authenticated and ready.")
            set_alert_state("ok")
        return

    # Not authenticated — track consecutive failures
    failures = get_failure_count() + 1
    set_failure_count(failures)
    log.warning("ibkr_session_not_authenticated", consecutive_failures=failures, threshold=GATEWAY_RESTART_THRESHOLD)

    # After threshold: full gateway restart
    if failures >= GATEWAY_RESTART_THRESHOLD:
        log.warning("ibkr_gateway_restart_threshold_reached", failures=failures)
        set_failure_count(0)
        set_alert_state("ok")  # Reset so next failure re-alerts cleanly
        trigger_gateway_restart()
        return

    if last_alert_state() == "alerted":
        log.info("ibkr_alert_already_sent", action="skipping_duplicate")
        return

    log.warning("ibkr_alert_sending", mode=IBKR_MODE)
    mode_label = "📄 Paper" if IBKR_MODE == "paper" else "💼 Live"
    if IBKR_MODE == "paper":
        msg = (
            f"🔴 <b>IBKR session lost</b> — {mode_label}\n\n"
            "Attempting to reconnect automatically...\n\n"
            "<i>You will receive a confirmation once the session is restored.</i>"
        )
    else:
        msg = (
            f"🔴 <b>IBKR session lost</b> — {mode_label}\n\n"
            "Attempting to reconnect...\n\n"
            "⚠️ <b>Get ready to provide your authenticator code.</b>\n"
            "<i>You will receive a follow-up message requesting it shortly.</i>"
        )
    ok = send_telegram(msg)
    if ok:
        set_alert_state("alerted")
        log.info("ibkr_alert_sent")
    else:
        log.error("ibkr_alert_failed")

    trigger_reauth()


if __name__ == "__main__":
    main()
