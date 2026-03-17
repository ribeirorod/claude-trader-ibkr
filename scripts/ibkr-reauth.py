#!/usr/bin/env python3
"""
IBKR automatic re-authentication via Playwright.

Paper mode: fills username/password, submits — no MFA needed.
Live mode:  fills username/password, detects MFA prompt, sends Telegram
            asking for the code, waits for reply, completes login.

Triggered automatically by ibkr-healthcheck.py when session is 401.
"""
from __future__ import annotations
import sys
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

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
log = structlog.get_logger("ibkr-reauth")

IBKR_MODE = os.getenv("IBKR_MODE", "paper")
GATEWAY_URL = os.getenv("IBEAM_GATEWAY_BASE_URL", "https://localhost:5001")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
OFFSET_FILE = ROOT / ".trader" / "telegram-offset.txt"
MFA_WAIT_SECONDS = 120  # how long to wait for user to reply with MFA code

if IBKR_MODE == "paper":
    USERNAME = os.getenv("IBKR_USERNAME_PAPER", "")
    PASSWORD = os.getenv("IBKR_PASSWORD_PAPER", "")
else:
    USERNAME = os.getenv("IBKR_USERNAME", "")
    PASSWORD = os.getenv("IBKR_PASSWORD", "")


# ── Telegram polling ──────────────────────────────────────────────────────────

def _load_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def _get_updates(offset: int) -> list[dict]:
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        f"?offset={offset}&timeout=5&allowed_updates=message"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("result", [])
    except Exception as exc:
        log.warning("telegram_get_updates_failed", error=str(exc))
        return []


def wait_for_mfa_code() -> str | None:
    """Poll Telegram for a numeric MFA reply. Returns code or None on timeout."""
    send_telegram(
        "🔐 <b>IBKR Live — MFA required</b>\n\n"
        "Reply to this message with your <b>authenticator code</b> to complete login.\n"
        f"<i>Waiting up to {MFA_WAIT_SECONDS}s…</i>"
    )

    offset = _load_offset()
    deadline = time.time() + MFA_WAIT_SECONDS

    while time.time() < deadline:
        updates = _get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            _save_offset(offset)
            msg = update.get("message", {})
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = msg.get("text", "").strip()
            if chat_id == str(TELEGRAM_CHAT_ID) and text.isdigit():
                log.info("ibkr_mfa_code_received")
                return text
        time.sleep(3)

    log.warning("ibkr_mfa_timeout", waited_s=MFA_WAIT_SECONDS)
    return None


# ── Playwright login ──────────────────────────────────────────────────────────

def run_login() -> bool:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    log.info("playwright_login_start", mode=IBKR_MODE, user=USERNAME)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        try:
            page.goto(GATEWAY_URL, wait_until="networkidle", timeout=30_000)
            log.info("playwright_navigated", url=page.url)

            # Toggle to paper mode if needed
            if IBKR_MODE == "paper":
                try:
                    page.wait_for_timeout(1_000)
                    toggled = page.evaluate("""() => {
                        // Dump all elements near paper/live toggle for debugging
                        const label = document.querySelector('label[class*="toggle"], label[class*="switch"], .xyz-toggle');
                        if (label) { label.click(); return 'clicked: ' + label.className; }
                        const checkbox = document.querySelector('input[type="checkbox"]');
                        if (checkbox) { checkbox.click(); return 'clicked checkbox id=' + checkbox.id; }
                        // Try clicking by text content
                        const allLabels = [...document.querySelectorAll('label, span, a')];
                        const paperEl = allLabels.find(el => el.textContent.trim() === 'Paper');
                        if (paperEl) { paperEl.click(); return 'clicked text=Paper tag=' + paperEl.tagName; }
                        return 'nothing found';
                    }""")
                    log.info("playwright_paper_toggle", result=toggled)
                    page.wait_for_timeout(1_500)
                    mode = page.evaluate("() => document.querySelector('input[name=\"loginType\"]')?.value ?? 'not found'")
                    log.info("playwright_login_type", value=mode)
                except Exception as e:
                    log.warning("playwright_paper_toggle_failed", error=str(e))

            # Fill credentials AFTER toggle settles
            username_field = page.locator("input[type='text']:visible, input:not([type='hidden']):not([type='password']):not([type='checkbox']):visible").first
            password_field = page.locator("input[type='password']:visible").first
            username_field.wait_for(state="visible", timeout=15_000)
            username_field.fill(USERNAME)
            password_field.fill(PASSWORD)
            log.info("playwright_credentials_filled", user=username_field.input_value())
            page.wait_for_timeout(500)

            # Submit via Enter key and wait for URL to leave the login page
            password_field.press("Enter")
            log.info("playwright_form_submitted")
            page.wait_for_timeout(3_000)
            page.screenshot(path=str(ROOT / ".trader" / "reauth-submit.png"))
            log.info("playwright_post_submit_url", url=page.url)
            try:
                page.wait_for_url(lambda url: "/sso/Login" not in url, timeout=30_000)
            except PWTimeout:
                pass
            page.wait_for_timeout(2_000)
            log.info("playwright_credentials_submitted")

            if IBKR_MODE == "paper":
                # Wait for navigation to complete after form submit
                try:
                    page.wait_for_load_state("networkidle", timeout=30_000)
                except PWTimeout:
                    pass
                final_url = page.url
                page.screenshot(path=str(ROOT / ".trader" / "reauth-debug.png"))
                log.info("playwright_final_url", url=final_url)
                # Success: redirected away from login page
                if "/sso/Login" not in final_url:
                    log.info("playwright_login_success", mode="paper")
                    return True
                log.error("playwright_login_failed", url=final_url, mode="paper")
                return False

            else:
                # Live: wait for MFA field
                try:
                    page.wait_for_selector(
                        "input[id='smscode'], input[name='smscode'], input[placeholder*='code' i]",
                        timeout=15_000,
                    )
                    log.info("playwright_mfa_field_detected")
                except PWTimeout:
                    # Maybe already logged in (no MFA prompt)
                    if GATEWAY_URL in page.url:
                        log.info("playwright_login_success", mode="live", mfa=False)
                        return True
                    log.error("playwright_mfa_field_missing", url=page.url)
                    return False

                code = wait_for_mfa_code()
                if not code:
                    send_telegram("❌ <b>IBKR re-auth failed</b> — MFA code not received in time.")
                    return False

                page.fill(
                    "input[id='smscode'], input[name='smscode'], input[placeholder*='code' i]",
                    code,
                )
                page.click("button[type='submit']")
                page.wait_for_url(f"{GATEWAY_URL}/**", timeout=20_000)
                log.info("playwright_login_success", mode="live", mfa=True)
                return True

        except PWTimeout as exc:
            log.error("playwright_timeout", error=str(exc))
            page.screenshot(path=str(ROOT / ".trader" / "reauth-error.png"))
            return False
        except Exception as exc:
            log.error("playwright_error", error=str(exc))
            return False
        finally:
            browser.close()


def main() -> None:
    if not USERNAME or not PASSWORD:
        log.error("ibkr_credentials_missing", mode=IBKR_MODE)
        send_telegram(f"❌ <b>IBKR re-auth failed</b> — credentials missing for <b>{IBKR_MODE}</b> mode.")
        sys.exit(1)

    success = run_login()

    if success:
        log.info("ibkr_reauth_complete", mode=IBKR_MODE)
        # health check will detect the recovery and send the Telegram confirmation
    else:
        log.error("ibkr_reauth_failed", mode=IBKR_MODE)
        send_telegram(
            f"❌ <b>IBKR re-auth failed</b> ({IBKR_MODE} mode)\n\n"
            "Manual intervention required. Check <code>.trader/reauth-error.png</code> for details."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
