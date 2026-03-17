from __future__ import annotations
import urllib.request
import urllib.parse
import json
import logging

from trader.config import Config

logger = logging.getLogger(__name__)


def send_telegram(message: str, config: Config | None = None, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message. Returns True on success.

    parse_mode: "HTML" (default, for alerts) or "Markdown" (for reports).
    """
    cfg = config or Config()
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        logger.warning("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing)")
        return False

    url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": cfg.telegram_chat_id,
        "text": message,
        "parse_mode": parse_mode,
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)
        return False
