"""Authorized user registry — persisted in .trader/allowed-users.json.

The owner is always the TELEGRAM_CHAT_ID from .env and cannot be removed.
Additional users are managed at runtime via /adduser and /removeuser commands
(owner-only). Each entry stores the Telegram numeric user ID plus an optional
username for readability.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
USERS_FILE = ROOT / ".trader" / "allowed-users.json"


def _owner_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


def load() -> list[dict]:
    """Return list of {id, username, label} dicts."""
    try:
        return json.loads(USERS_FILE.read_text())
    except FileNotFoundError:
        return []
    except Exception as exc:
        log.warning("users_load_error", error=str(exc))
        return []


def _save(users: list[dict]) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2))


def is_authorized(user_id: int | str) -> bool:
    uid = str(user_id)
    if uid == _owner_id():
        return True
    return any(str(u["id"]) == uid for u in load())


def is_owner(user_id: int | str) -> bool:
    return str(user_id) == _owner_id()


def add(user_id: int, username: str | None = None, label: str = "") -> bool:
    """Add a user. Returns False if already present."""
    uid = str(user_id)
    if uid == _owner_id():
        return False  # owner is implicit
    users = load()
    if any(str(u["id"]) == uid for u in users):
        return False
    users.append({"id": user_id, "username": username or "", "label": label})
    _save(users)
    log.info("user_added", user_id=user_id, username=username)
    return True


def remove(user_id: int) -> bool:
    """Remove a user. Returns False if not found or is owner."""
    uid = str(user_id)
    if uid == _owner_id():
        return False  # cannot remove owner
    users = load()
    new = [u for u in users if str(u["id"]) != uid]
    if len(new) == len(users):
        return False
    _save(new)
    log.info("user_removed", user_id=user_id)
    return True


def list_all() -> list[dict]:
    """Return all users including the implicit owner entry."""
    owner = _owner_id()
    result = [{"id": int(owner), "username": "", "label": "owner"}] if owner else []
    result += load()
    return result
