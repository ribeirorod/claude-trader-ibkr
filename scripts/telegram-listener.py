#!/usr/bin/env python3
"""
Telegram listener — short-lived stateless poller.

Called by CronCreate every 2 minutes. Polls Telegram for pending messages,
processes each one with a fresh claude-agent-sdk query(), sends the response,
and exits. Auth uses the Claude Code keychain session (Max subscription).

Run manually:
  uv run python scripts/telegram-listener.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

# Use Claude Code keychain session (Max subscription) — not API key billing
os.environ.pop("CLAUDECODE", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

sys.path.insert(0, str(ROOT))
from trader.notify import send_telegram
from trader.config import Config

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram-listener")

TELEGRAM_MAX_CHARS = 4000
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"
OFFSET_FILE = ROOT / ".trader" / "telegram-listener-offset.txt"

SYSTEM_PROMPT = f"""\
You are the portfolio-conductor agent for an automated trading system.
You are being addressed directly by the portfolio owner via Telegram.
Working directory: {ROOT}

━━━ TRADER CLI REFERENCE ━━━

Positions & P&L:
  uv run trader positions list
  uv run trader positions pnl
  uv run trader positions close TICKER

Orders:
  uv run trader orders list [--status open|filled|cancelled|all]
  uv run trader orders buy TICKER QTY [--type market|limit|bracket] [--price N] [--take-profit N] [--stop-loss N]
  uv run trader orders sell TICKER QTY [--type market|limit|stop] [--price N]
  uv run trader orders bracket TICKER QTY --entry N --take-profit N --stop-loss N
  uv run trader orders stop TICKER --price N
  uv run trader orders trailing-stop TICKER --trail-percent N
  uv run trader orders take-profit TICKER --price N
  uv run trader orders cancel ORDER_ID
  uv run trader orders modify ORDER_ID [--price N] [--qty N]

Account:
  uv run trader account summary
  uv run trader account balance
  uv run trader account margin

Watchlists (stored in outputs/watchlists.json):
  uv run trader watchlist list
  uv run trader watchlist add TICKER [TICKER ...] [--list name]
  uv run trader watchlist remove TICKER [--list name]
  uv run trader watchlist show [name] [--signals]
  uv run trader watchlist from-scan SCAN_TYPE [--list name] [--ema200-above] [--mktcap-above N]

Quotes & Signals:
  uv run trader quotes TICKER [TICKER ...]
  uv run trader signals TICKER [--strategy rsi|macd|ma_cross|bnf]

News & Sentiment:
  uv run trader news TICKER [--limit N] [--days N]

Market Scan:
  uv run trader scan run SCAN_TYPE [--market STK.US.MAJOR] [--limit N]
  uv run trader scan markets

Strategies:
  uv run trader strategies list
  uv run trader strategies backtest STRATEGY TICKER [--days N]
  uv run trader strategies optimize STRATEGY TICKER

Reports (generates and sends Telegram message):
  uv run python scripts/daily-report.py --slot open    # BOD brief
  uv run python scripts/daily-report.py --slot close   # EOD summary

Logs & state:
  tail -N .trader/logs/agent.jsonl
  tail -N .trader/logs/portfolio_evolution.jsonl
  cat .trader/profile.json
  cat outputs/watchlists.json

━━━ SCHEDULED CRON JOBS ━━━

  eu-pre-market      Mon-Fri 08:03 CET   — EU pre-market analysis
  eu-market          Mon-Fri 09:07-15:07 CET (hourly) — EU market check
  eu-us-overlap      Mon-Fri 15:03 CET   — Highest liquidity window
  us-market          Mon-Fri 17:07-21:07 CET (hourly) — US market check
  weekly             Sunday 18:03 CET    — Deep portfolio review
  monthly            1st Sunday 18:03 CET — Self-improvement review
  daily-report-bod   Mon-Fri 07:55 CET   — BOD Telegram report
  daily-report-eod   Mon-Fri 22:05 CET   — EOD Telegram report
  ibkr-healthcheck   Every 5 min         — IBKR session keepalive + auto-reauth
  telegram-listener  Every 2 min         — This poller (you)

━━━ RULES ━━━

- Use Bash to run trader CLI commands and read files as needed
- Do NOT place buy/sell orders unless the user explicitly says to place an order
- For order placement, confirm ticker, qty, and price before executing
- Be precise and to the point — lead with the answer, skip preamble
- Use Markdown: *bold* for headers, `code` for tickers/values, code blocks for tables
- No emojis, no icons
- For analysis: key facts only — no restating the question, no filler sentences
"""


# ── Telegram helpers ──────────────────────────────────────────────────────────

def _load_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(str(offset))


def _tg(token: str, method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params).encode() if params else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.warning("%s failed: %s", method, exc)
        return {}


def _get_updates(token: str, offset: int) -> list[dict]:
    res = _tg(token, "getUpdates", offset=offset, timeout=5, allowed_updates=["message"])
    return res.get("result", [])


def _reply(cfg: Config, text: str) -> None:
    chunks = []
    while len(text) > TELEGRAM_MAX_CHARS:
        split_at = text.rfind("\n", 0, TELEGRAM_MAX_CHARS)
        if split_at == -1:
            split_at = TELEGRAM_MAX_CHARS
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    chunks.append(text)
    for chunk in chunks:
        if not send_telegram(chunk, config=cfg, parse_mode="Markdown"):
            send_telegram(chunk, config=cfg)


# ── Media helpers ─────────────────────────────────────────────────────────────

def _download_file(token: str, file_id: str) -> bytes:
    info = _tg(token, "getFile", file_id=file_id)
    file_path = info.get("result", {}).get("file_path", "")
    if not file_path:
        raise ValueError("Could not resolve file_path from Telegram")
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _optimise_image(data: bytes, max_dim: int = 1280, quality: int = 82) -> bytes:
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    import groq
    client = groq.Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
    transcription = client.audio.transcriptions.create(
        model=GROQ_WHISPER_MODEL,
        file=(filename, audio_bytes),
        response_format="text",
    )
    return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()


# ── Agent query ───────────────────────────────────────────────────────────────

async def _ask(text: str) -> str:
    options = ClaudeAgentOptions(
        cwd=str(ROOT),
        allowed_tools=["Bash", "Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        system_prompt=SYSTEM_PROMPT,
        model="claude-opus-4-6",
        max_turns=30,
        # Force OAuth (Max subscription) — override any custom API key stored in
        # Claude Code config/keychain that may have insufficient credits.
        env={"ANTHROPIC_API_KEY": ""},
    )
    parts: list[str] = []
    async for message in query(prompt=text, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(message, ResultMessage):
            if message.is_error:
                log.error("SDK ResultMessage error: %s", message)
                raise RuntimeError(str(message))
            if message.result:
                parts.append(message.result)
    return "\n".join(parts).strip()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    cfg = Config()
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        log.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        sys.exit(1)

    authorized_chat = str(cfg.telegram_chat_id)
    offset = _load_offset()

    updates = _get_updates(cfg.telegram_bot_token, offset)
    if not updates:
        log.info("No pending messages.")
        return

    for update in updates:
        offset = update["update_id"] + 1
        _save_offset(offset)

        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        if chat_id != authorized_chat:
            continue

        # Voice
        voice = msg.get("voice")
        if voice and not text:
            log.info("Voice message (duration=%ss)", voice.get("duration", "?"))
            try:
                audio = await asyncio.to_thread(_download_file, cfg.telegram_bot_token, voice["file_id"])
                text = await asyncio.to_thread(_transcribe, audio)
                log.info("Transcribed: %s", text[:100])
            except Exception as exc:
                log.error("Transcription failed: %s", exc)
                send_telegram(f"Transcription failed: {exc}", config=cfg)
                continue

        # Document
        document = msg.get("document")
        if document and not text and not msg.get("photo"):
            fname = document.get("file_name", f"document-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
            caption = msg.get("caption", "").strip()
            try:
                doc_bytes = await asyncio.to_thread(_download_file, cfg.telegram_bot_token, document["file_id"])
                tmp_dir = ROOT / ".trader" / "tmp"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                doc_path = tmp_dir / fname
                doc_path.write_bytes(doc_bytes)
                text = f"{caption}\n\n[Document saved at: {doc_path}]" if caption else f"[Document saved at: {doc_path}]"
            except Exception as exc:
                log.error("Document download failed: %s", exc)
                send_telegram(f"Could not download document: {exc}", config=cfg)
                continue

        # Photo
        photos = msg.get("photo")
        if photos:
            best = max(photos, key=lambda p: p.get("file_size", 0))
            caption = msg.get("caption", "").strip()
            try:
                img_bytes = await asyncio.to_thread(_download_file, cfg.telegram_bot_token, best["file_id"])
                tmp_dir = ROOT / ".trader" / "tmp"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                img_path = tmp_dir / f"tg-photo-{ts}.jpg"
                img_bytes = await asyncio.to_thread(_optimise_image, img_bytes)
                img_path.write_bytes(img_bytes)
                text = f"{caption}\n\n[Image saved at: {img_path}]" if caption else f"[Image saved at: {img_path}]"
            except Exception as exc:
                log.error("Photo download failed: %s", exc)
                send_telegram(f"Could not download image: {exc}", config=cfg)
                continue

        if not text:
            continue

        now = datetime.now().strftime("%a %d %b %Y  %H:%M CET")
        log.info("Processing: %s", text[:100])
        try:
            response = await _ask(f"[{now}]\n{text}")
            _reply(cfg, response)
        except Exception as exc:
            tb = traceback.format_exc()
            log.error("Dispatch error: %s\n%s", exc, tb)
            # Send first 800 chars of the traceback so the cause is visible in Telegram
            short = str(exc)
            if "exit code" in short.lower() or len(short) < 20:
                short = tb.strip().splitlines()[-1]
            send_telegram(f"Agent error: {short}\n\nCheck `.trader/logs/` for full traceback.", config=cfg)


if __name__ == "__main__":
    asyncio.run(main())
