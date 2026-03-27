"""Markdown → Telegram formatter using telegramify-markdown."""
from __future__ import annotations

import telegramify_markdown as tgmd

# Telegram message limit in UTF-16 code units (chars for ASCII)
_MAX_UTF16 = 4000  # stay under Telegram's 4096 limit


def convert_markdown(md: str) -> list[tuple[str, list]]:
    """Convert markdown to Telegram-ready (text, entities) chunks.

    Returns a list of (text, entities) tuples ready for
    bot.send_message(text=text, entities=entities).
    """
    contents = tgmd.convert(md)
    # convert() returns [Text(content, entities), ...] or similar
    # Merge into a single (text, entities) then split
    full_text = ""
    all_entities = []
    for item in contents:
        if hasattr(item, "content") and isinstance(item.content, str):
            text = item.content
            if hasattr(item, "__iter__"):
                # item is (text, entities_list)
                for sub in item:
                    if isinstance(sub, list):
                        # Offset entities by current text length
                        for ent in sub:
                            ent.offset += len(full_text.encode("utf-16-le")) // 2
                            all_entities.append(ent)
            full_text += text

    # If entity merging is complex, fall back to markdownify + MarkdownV2
    if not full_text.strip():
        md_v2 = tgmd.markdownify(md)
        return _split_markdownv2(md_v2)

    return tgmd.split_entities(full_text, all_entities, _MAX_UTF16)


def to_markdownv2(md: str) -> str:
    """Convert markdown to Telegram MarkdownV2 string."""
    return tgmd.markdownify(md)


def split_for_telegram(md_v2: str, max_chars: int = _MAX_UTF16) -> list[str]:
    """Split a MarkdownV2 string into chunks ≤ max_chars."""
    return _split_markdownv2(md_v2, max_chars)


def _split_markdownv2(text: str, max_chars: int = _MAX_UTF16) -> list[str]:
    """Split MarkdownV2 text into chunks at paragraph/line boundaries."""
    chunks: list[str] = []
    remaining = text.strip()

    while len(remaining) > max_chars:
        # Prefer paragraph break
        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, max_chars)
        if split_at == -1:
            split_at = max_chars

        chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip("\n")
        if chunk.strip():
            chunks.append(chunk.strip())

    if remaining.strip():
        chunks.append(remaining.strip())

    return chunks
