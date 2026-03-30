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
COOKIES_FILE = ROOT / ".trader" / "ibkr-cookies.json"

# State file — prevents spamming Telegram on every check when already alerted
STATE_FILE = ROOT / ".trader" / "ibkr-health.state"
# Failure counter — triggers full gateway restart after threshold
FAILURE_COUNT_FILE = ROOT / ".trader" / "ibkr-health-failures.txt"
GATEWAY_RESTART_THRESHOLD = 20  # 20 × 5 min = 100 min of consecutive failures (host only)
DOCKER_REAUTH_RETRY_THRESHOLD = 3  # In Docker: restart gateway after 3 failed reauths (15 min)


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _load_cookie_header() -> str | None:
    """Load session cookies saved by ibkr-reauth.py and return as Cookie header."""
    try:
        if COOKIES_FILE.exists():
            cookies = json.loads(COOKIES_FILE.read_text())
            return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    except Exception:
        pass
    return None


def check_auth() -> bool:
    """Returns True if IBKR session is authenticated."""
    try:
        req = urllib.request.Request(AUTH_ENDPOINT)
        cookie_header = _load_cookie_header()
        if cookie_header:
            req.add_header("Cookie", cookie_header)
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
        cookie_header = _load_cookie_header()
        if cookie_header:
            req.add_header("Cookie", cookie_header)
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


def _in_docker() -> bool:
    """True when running inside a Docker container."""
    return Path("/.dockerenv").exists()


def _tmux_session_exists(name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def trigger_gateway_restart() -> None:
    """Handle a gateway that has been unreachable for 100+ minutes.

    In Docker: the gateway container is managed by Docker's restart policy —
    send a Telegram alert and let Docker handle it.
    On host: kill and recreate the tmux session running run.sh.
    """
    mode_label = "📄 Paper" if IBKR_MODE == "paper" else "💼 Live"

    if _in_docker():
        log.warning("ibkr_gateway_restarting_docker")
        # In Docker we can reach the gateway container's health endpoint.
        # The gateway container has restart: unless-stopped, so killing the
        # JVM process inside it will trigger Docker to restart it.
        # We use the /shutdown endpoint if available, otherwise just let
        # the next reauth cycle handle a fresh gateway.
        try:
            req = urllib.request.Request(f"{GATEWAY_URL}/v1/api/logout", method="POST")
            urllib.request.urlopen(req, timeout=5, context=_ssl_ctx())
        except Exception:
            pass  # Best effort — gateway may already be unresponsive
        send_telegram(
            f"🔄 <b>IBKR gateway restarting</b> — {mode_label}\n\n"
            "Sent logout to force session reset. Reauth will run on next cycle."
        )
        return

    # Host path: restart via tmux
    gateway_dir = ROOT / "clientportal.gw"
    run_sh = gateway_dir / "bin" / "run.sh"
    if not run_sh.exists():
        log.warning("clientportal.gw/bin/run.sh not found — skipping gateway restart.")
        return

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
    send_telegram(
        f"🔄 <b>IBKR gateway restarting</b> — {mode_label}\n\n"
        "Session was down 100+ min. Restarting via <code>clientportal.gw/bin/run.sh</code>.\n"
        "<i>Authentication will follow on the next cycle.</i>"
    )
    log.info("ibkr_gateway_restart_initiated", tmux_session="ibkr-gateway")


def trigger_reauth() -> None:
    """Trigger Playwright re-authentication.

    In Docker: call ibkr-reauth.py directly (no tmux available).
    On host:   launch ibkr-start.sh --auth-only so protected-process checks run.
    """
    if _in_docker():
        reauth_script = ROOT / "scripts" / "ibkr-reauth.py"
        log.info("ibkr_reauth_triggering_docker")
        subprocess.Popen(
            [sys.executable, str(reauth_script)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

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

    # In Docker: use a faster escalation path
    restart_threshold = DOCKER_REAUTH_RETRY_THRESHOLD if _in_docker() else GATEWAY_RESTART_THRESHOLD
    log.warning("ibkr_session_not_authenticated", consecutive_failures=failures, threshold=restart_threshold)

    # After threshold: gateway restart (logout + let Docker restart, or tmux restart)
    if failures >= restart_threshold:
        log.warning("ibkr_gateway_restart_threshold_reached", failures=failures)
        set_failure_count(0)
        if IBKR_MODE == "paper":
            # Paper: reset alert so next failure re-alerts and retries cleanly
            set_alert_state("ok")
            trigger_gateway_restart()
        else:
            # Live: keep "alerted" state — don't spam user with repeated
            # "session lost" messages. Gateway restart won't help without MFA.
            # Just stay quiet until user sends /reauth.
            if last_alert_state() != "alerted":
                trigger_gateway_restart()
            else:
                log.info("ibkr_live_suppressing_restart_spam", failures=failures)
        return

    if last_alert_state() == "alerted":
        if IBKR_MODE == "paper":
            # Paper: silently retry reauth each cycle (no MFA needed)
            log.info("ibkr_reauth_retry", attempt=failures)
            trigger_reauth()
        else:
            # Live: do NOT retry — wait for user to send /reauth
            log.info("ibkr_waiting_for_user_reauth", attempt=failures)
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
            "Session expired. <b>Send /reauth when you are ready</b> to provide your MFA code.\n\n"
            "<i>No automatic retries — waiting for your command.</i>"
        )
    ok = send_telegram(msg)
    if ok:
        set_alert_state("alerted")
        log.info("ibkr_alert_sent")
    else:
        log.error("ibkr_alert_failed")

    # Only auto-trigger reauth in paper mode (no MFA needed)
    if IBKR_MODE == "paper":
        trigger_reauth()


if __name__ == "__main__":
    main()
