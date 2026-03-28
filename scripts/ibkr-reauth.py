#!/usr/bin/env python3
"""
IBKR automatic re-authentication via Playwright.

Paper mode: fills username/password, toggles to Paper, submits — no MFA needed.
Live mode:  fills username/password (Live is default), selects "Mobile Authenticator App"
            from the 2FA dropdown, sends Telegram asking for the TOTP code, waits for
            reply, fills the code, and submits.

Triggered automatically by ibkr-healthcheck.py when session is 401.
"""
from __future__ import annotations
import sys
import time
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
MFA_PENDING_FILE = ROOT / ".trader" / "mfa-pending"
MFA_CODE_FILE = ROOT / ".trader" / "mfa-code"
MFA_WAIT_SECONDS = 120  # how long to wait for user to reply with MFA code

# Credentials — always use live creds for live, paper creds for paper
if IBKR_MODE == "paper":
    USERNAME = os.getenv("IBKR_USERNAME_PAPER", "")
    PASSWORD = os.getenv("IBKR_PASSWORD_PAPER", "")
else:
    USERNAME = os.getenv("IBKR_USERNAME", "")
    PASSWORD = os.getenv("IBKR_PASSWORD", "")


def _set_mfa_pending() -> None:
    """Signal to the Telegram bot that we're waiting for an MFA code."""
    MFA_PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    MFA_PENDING_FILE.write_text(str(time.time()))
    # Clear any stale code file
    MFA_CODE_FILE.unlink(missing_ok=True)


def _clear_mfa_pending() -> None:
    """Remove the MFA pending flag and code file."""
    MFA_PENDING_FILE.unlink(missing_ok=True)
    MFA_CODE_FILE.unlink(missing_ok=True)


def wait_for_mfa_code() -> str | None:
    """Wait for MFA code via file-based IPC with the Telegram bot.

    The Telegram bot is the sole consumer of getUpdates. When it sees
    .trader/mfa-pending and receives a 6+ digit number from the owner,
    it writes the code to .trader/mfa-code for us to pick up.
    """
    _set_mfa_pending()

    send_telegram(
        "🔐 <b>IBKR Live — MFA required</b>\n\n"
        "Open your <b>authenticator app</b> and reply with the 6-digit code.\n"
        f"<i>Waiting up to {MFA_WAIT_SECONDS}s…</i>"
    )
    log.info("ibkr_mfa_waiting_for_code_file")

    deadline = time.time() + MFA_WAIT_SECONDS

    try:
        while time.time() < deadline:
            if MFA_CODE_FILE.exists():
                code = MFA_CODE_FILE.read_text().strip()
                if code.isdigit() and len(code) >= 6:
                    log.info("ibkr_mfa_code_received")
                    return code
            time.sleep(2)

        log.warning("ibkr_mfa_timeout", waited_s=MFA_WAIT_SECONDS)
        return None
    finally:
        _clear_mfa_pending()


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

            # ── Toggle handling ───────────────────────────────────────────
            # The login page has a Live/Paper toggle (checkbox id="toggle1").
            # Default state: unchecked = Live. Checked = Paper.
            is_paper_checked = page.evaluate(
                "document.getElementById('toggle1')?.checked ?? false"
            )

            if IBKR_MODE == "paper" and not is_paper_checked:
                # Switch to Paper
                page.click('label[for="toggle1"]')
                page.wait_for_timeout(1_000)
                log.info("playwright_toggled_to_paper")
            elif IBKR_MODE != "paper" and is_paper_checked:
                # Switch to Live (uncheck Paper toggle)
                page.click('label[for="toggle1"]')
                page.wait_for_timeout(1_000)
                log.info("playwright_toggled_to_live")
            else:
                log.info("playwright_toggle_correct", mode=IBKR_MODE)

            # ── Fill credentials ──────────────────────────────────────────
            page.fill("#xyz-field-username", USERNAME)
            page.fill("#xyz-field-password", PASSWORD)
            log.info("playwright_credentials_filled")
            page.wait_for_timeout(500)

            if IBKR_MODE == "paper":
                # Paper: just submit — no MFA
                page.click("button[type='submit']")
                log.info("playwright_form_submitted")
                page.wait_for_timeout(3_000)
                page.screenshot(path=str(ROOT / ".trader" / "reauth-submit.png"))
                try:
                    page.wait_for_url(
                        lambda url: "/sso/Login" not in url, timeout=30_000
                    )
                except PWTimeout:
                    pass
                page.wait_for_timeout(2_000)

                final_url = page.url
                page.screenshot(path=str(ROOT / ".trader" / "reauth-debug.png"))
                if "/sso/Login" not in final_url:
                    log.info("playwright_login_success", mode="paper")
                    return True
                log.error("playwright_login_failed", url=final_url, mode="paper")
                return False

            # ── Live mode: submit creds, select 2FA device, enter code ─────
            # Submit credentials first
            page.click("button[type='submit']")
            log.info("playwright_credentials_submitted")
            page.wait_for_timeout(3_000)
            page.screenshot(path=str(ROOT / ".trader" / "reauth-submit.png"))

            # Check if already logged in (no MFA for this session)
            if "/sso/Login" not in page.url:
                log.info("playwright_login_success", mode="live", mfa=False)
                return True

            # Wait for the 2FA dropdown to become visible
            try:
                page.wait_for_selector(
                    "select.xyz-multipleselect:visible", timeout=10_000
                )
            except PWTimeout:
                # Dropdown may not exist — check if code field is already shown
                code_field = page.query_selector("#xyz-field-silver-response")
                if code_field and code_field.is_visible():
                    log.info("playwright_mfa_field_already_visible")
                else:
                    log.error("playwright_2fa_not_found", url=page.url)
                    page.screenshot(
                        path=str(ROOT / ".trader" / "reauth-error.png")
                    )
                    return False

            # Select "Mobile Authenticator App" (value="4") if dropdown is visible
            dropdown = page.query_selector("select.xyz-multipleselect")
            if dropdown and dropdown.is_visible():
                try:
                    page.select_option("select.xyz-multipleselect", value="4")
                    log.info("playwright_selected_authenticator_app")
                    page.wait_for_timeout(2_000)
                except Exception as exc:
                    log.error(
                        "playwright_2fa_dropdown_failed", error=str(exc)
                    )
                    page.screenshot(
                        path=str(ROOT / ".trader" / "reauth-error.png")
                    )
                    return False

            # Wait for the TOTP code input field to appear
            try:
                page.wait_for_selector(
                    "#xyz-field-silver-response:visible", timeout=10_000
                )
                log.info("playwright_mfa_field_detected")
            except PWTimeout:
                log.error("playwright_mfa_field_missing", url=page.url)
                page.screenshot(
                    path=str(ROOT / ".trader" / "reauth-error.png")
                )
                return False

            page.screenshot(
                path=str(ROOT / ".trader" / "reauth-mfa-prompt.png")
            )

            # Ask for MFA code via Telegram
            code = wait_for_mfa_code()
            if not code:
                send_telegram(
                    "❌ <b>IBKR re-auth failed</b> — MFA code not received in time."
                )
                return False

            # Fill the code and submit via Enter key (multiple submit buttons
            # exist on the page — only one is visible, Enter targets the
            # active form reliably)
            code_input = page.locator("#xyz-field-silver-response")
            code_input.fill(code)
            log.info("playwright_mfa_code_filled")
            code_input.press("Enter")
            log.info("playwright_mfa_submitted")

            # Wait for redirect away from login page
            try:
                page.wait_for_url(
                    lambda url: "/sso/Login" not in url, timeout=20_000
                )
            except PWTimeout:
                page.screenshot(
                    path=str(ROOT / ".trader" / "reauth-error.png")
                )
                log.error("playwright_mfa_redirect_timeout", url=page.url)
                send_telegram(
                    "❌ <b>IBKR re-auth failed</b> — MFA code may have been "
                    "incorrect or expired."
                )
                return False

            page.wait_for_timeout(2_000)
            log.info("playwright_mfa_redirect_ok", url=page.url)

            # Activate the API session by hitting auth/status from the
            # authenticated browser context.  The gateway links the SSO
            # session to the REST API only after this call.
            for attempt in range(5):
                try:
                    resp = page.evaluate("""
                        fetch('/v1/api/iserver/auth/status', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: '{}'
                        }).then(r => r.text())
                    """)
                    log.info("playwright_auth_status_poll", attempt=attempt, body=resp[:200] if resp else "")
                    if resp and "authenticated" in resp and "true" in resp.lower():
                        break
                except Exception as exc:
                    log.warning("playwright_auth_status_poll_error", attempt=attempt, error=str(exc))
                page.wait_for_timeout(3_000)

            page.screenshot(path=str(ROOT / ".trader" / "reauth-debug.png"))
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
        send_telegram(
            f"❌ <b>IBKR re-auth failed</b> — credentials missing for <b>{IBKR_MODE}</b> mode."
        )
        sys.exit(1)

    success = run_login()

    if success:
        log.info("ibkr_reauth_complete", mode=IBKR_MODE)
        send_telegram(
            f"✅ <b>IBKR authenticated</b> ({IBKR_MODE} mode)"
        )
    else:
        log.error("ibkr_reauth_failed", mode=IBKR_MODE)
        send_telegram(
            f"❌ <b>IBKR re-auth failed</b> ({IBKR_MODE} mode)\n\n"
            "Manual intervention required. Check <code>.trader/reauth-error.png</code> for details."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
