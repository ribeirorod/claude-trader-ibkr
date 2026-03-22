"""Telegram handler — persistent python-telegram-bot Application with command and message handlers."""
from __future__ import annotations

import asyncio
import io
import os
import traceback
from datetime import datetime
from pathlib import Path

import structlog
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from trader.server import agent, users
from trader.server.format import split_for_telegram, to_telegram_html

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
TMP_DIR = ROOT / ".trader" / "tmp"
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"


def _is_authorized(update: Update) -> bool:
    return users.is_authorized(update.effective_user.id)


def _is_owner(update: Update) -> bool:
    return users.is_owner(update.effective_user.id)


# ── Media helpers ─────────────────────────────────────────────────────────────

def _transcribe_voice(file_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Sync — runs in thread pool via asyncio.to_thread."""
    import groq
    client = groq.Groq(api_key=os.getenv("GROQ_API_KEY", ""))
    transcription = client.audio.transcriptions.create(
        model=GROQ_WHISPER_MODEL,
        file=(filename, file_bytes),
        response_format="text",
    )
    return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()


def _optimise_image(data: bytes, max_dim: int = 1280, quality: int = 82) -> bytes:
    """Sync — runs in thread pool via asyncio.to_thread."""
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


# ── Send helpers ──────────────────────────────────────────────────────────────

async def _send_response(update: Update, text: str) -> None:
    """Convert markdown → Telegram HTML, split into conversational chunks, send."""
    html = to_telegram_html(text)
    for chunk in split_for_telegram(html):
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except Exception:
            try:
                await update.message.reply_text(chunk)
            except Exception as exc:
                log.error("telegram_send_error", error=str(exc))


async def _keep_typing(update: Update, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await update.message.chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        await asyncio.sleep(4)


# ── Command handlers ──────────────────────────────────────────────────────────

async def _handle_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    is_own = _is_owner(update)
    admin = "\n/users — list authorized users\n/adduser &lt;id&gt; — grant access\n/removeuser &lt;id&gt; — revoke access" if is_own else ""
    await update.message.reply_text(
        "<b>Trader Bot</b>\n\nAvailable commands:\n"
        "/status — quick positions summary\n"
        f"/reset — clear this conversation session{admin}\n\n"
        "Or just send any message, voice note, image, or file.",
        parse_mode=ParseMode.HTML,
    )


async def _handle_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    await update.message.reply_text("Session cleared. Starting fresh.")


async def _handle_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    all_users = users.list_all()
    if not all_users:
        await update.message.reply_text("No authorized users.")
        return
    lines = []
    for u in all_users:
        tag = f"@{u['username']}" if u.get("username") else f"id:{u['id']}"
        label = f"  <i>{u['label']}</i>" if u.get("label") else ""
        lines.append(f"• <code>{u['id']}</code> {tag}{label}")
    await update.message.reply_text(
        f"<b>Authorized users ({len(all_users)})</b>\n\n" + "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


async def _handle_adduser(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /adduser <user_id> [label]"""
    if not _is_owner(update):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("Usage: /adduser <user_id> [label]")
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("user_id must be a number. Ask the user to send /start so you can see their ID in the logs.")
        return
    label = " ".join(args[1:])
    added = users.add(user_id, label=label)
    if added:
        await update.message.reply_text(f"User <code>{user_id}</code> added.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"User <code>{user_id}</code> is already authorized.", parse_mode=ParseMode.HTML)


async def _handle_removeuser(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Usage: /removeuser <user_id>"""
    if not _is_owner(update):
        return
    args = ctx.args or []
    if not args:
        await update.message.reply_text("Usage: /removeuser <user_id>")
        return
    try:
        user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("user_id must be a number.")
        return
    removed = users.remove(user_id)
    if removed:
        await update.message.reply_text(f"User <code>{user_id}</code> removed.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"User <code>{user_id}</code> not found (or is the owner).", parse_mode=ParseMode.HTML)


async def _handle_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return
    chat_id = str(update.effective_chat.id)
    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update, stop))
    try:
        response = await agent.ask("Show current positions and account summary.", chat_id=chat_id)
    except Exception as exc:
        response = f"Error: {exc}"
    finally:
        stop.set()
        typing_task.cancel()
    await _send_response(update, response)


# ── Message handler ───────────────────────────────────────────────────────────

async def _handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        u = update.effective_user
        log.warning("unauthorized_message", user_id=u.id, username=u.username)
        return

    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()

    # Voice — transcribe to text
    if update.message.voice and not text:
        try:
            voice_file = await ctx.bot.get_file(update.message.voice.file_id)
            audio_bytes = await voice_file.download_as_bytearray()
            text = await asyncio.to_thread(_transcribe_voice, bytes(audio_bytes))
            log.info("voice_transcribed", preview=text[:80])
        except Exception as exc:
            log.error("voice_transcription_error", error=str(exc))
            await update.message.reply_text(f"Transcription failed: {exc}")
            return

    # Document — save and pass path to agent
    if update.message.document and not text and not update.message.photo:
        doc = update.message.document
        fname = doc.file_name or f"document-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        caption = (update.message.caption or "").strip()
        try:
            doc_file = await ctx.bot.get_file(doc.file_id)
            doc_bytes = await doc_file.download_as_bytearray()
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            doc_path = TMP_DIR / fname
            doc_path.write_bytes(bytes(doc_bytes))
            text = f"{caption}\n\n[Document saved at: {doc_path}]" if caption else f"[Document saved at: {doc_path}]"
        except Exception as exc:
            await update.message.reply_text(f"Could not download document: {exc}")
            return

    # Photo — optimise and pass path to agent
    if update.message.photo:
        best = max(update.message.photo, key=lambda p: p.file_size or 0)
        caption = (update.message.caption or "").strip()
        try:
            photo_file = await ctx.bot.get_file(best.file_id)
            img_bytes = await photo_file.download_as_bytearray()
            img_bytes = await asyncio.to_thread(_optimise_image, bytes(img_bytes))
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            img_path = TMP_DIR / f"tg-photo-{ts}.jpg"
            img_path.write_bytes(img_bytes)
            text = f"{caption}\n\n[Image saved at: {img_path}]" if caption else f"[Image saved at: {img_path}]"
        except Exception as exc:
            await update.message.reply_text(f"Could not download image: {exc}")
            return

    if not text:
        return

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(update, stop))
    try:
        response = await agent.ask(text, chat_id=chat_id)
        await _send_response(update, response)
    except Exception as exc:
        tb = traceback.format_exc()
        log.error("agent_error", error=str(exc), traceback=tb.strip().splitlines()[-1])
        short = str(exc)
        if "exit code" in short.lower() or len(short) < 20:
            short = tb.strip().splitlines()[-1]
        await update.message.reply_text(
            f"Agent error: {short}\n\nCheck <code>.trader/logs/</code> for full traceback.",
            parse_mode=ParseMode.HTML,
        )
    finally:
        stop.set()
        typing_task.cancel()


def build_telegram_app() -> Application:
    """Build and return the Telegram Application (not yet started)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN must be set")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("reset", _handle_reset))
    app.add_handler(CommandHandler("status", _handle_status))
    app.add_handler(CommandHandler("users", _handle_users))
    app.add_handler(CommandHandler("adduser", _handle_adduser))
    app.add_handler(CommandHandler("removeuser", _handle_removeuser))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, _handle_message))
    return app
