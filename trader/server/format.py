"""Markdown → Telegram HTML formatter and conversational message splitter."""
from __future__ import annotations

import re

_MAX_CHUNK = 2000  # well under Telegram's 4096 limit; feels conversational


# ── Conversion ────────────────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    """Escape bare HTML entities outside of tags we'll produce."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_telegram_html(md: str) -> str:
    """Convert a markdown string to Telegram-compatible HTML.

    Handles: headers, bold, italic, inline code, fenced code blocks,
    horizontal rules, and bullet lists.  Leaves plain text untouched.
    """
    # 1. Extract fenced code blocks and replace with placeholders so we
    #    don't mess with their content during the other transformations.
    blocks: list[str] = []

    def _stash_block(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        code = _escape_html(m.group(2))
        tag = f'<pre><code class="language-{lang}">{code}</code></pre>' if lang else f"<pre>{code}</pre>"
        blocks.append(tag)
        return f"\x00BLOCK{len(blocks) - 1}\x00"

    md = re.sub(r"```(\w*)\n?(.*?)```", _stash_block, md, flags=re.DOTALL)

    # 2. Inline code  (`text`)
    inline_codes: list[str] = []

    def _stash_inline(m: re.Match) -> str:
        inline_codes.append(f"<code>{_escape_html(m.group(1))}</code>")
        return f"\x00INLINE{len(inline_codes) - 1}\x00"

    md = re.sub(r"`([^`\n]+)`", _stash_inline, md)

    # 3. Escape remaining HTML special chars
    md = _escape_html(md)

    # 4. Headers (## Header → <b>Header</b>) — strip leading #s
    md = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", md, flags=re.MULTILINE)

    # 5. Bold — **text** or __text__
    md = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", md)
    md = re.sub(r"__(.+?)__", r"<b>\1</b>", md)

    # 6. Italic — *text* or _text_ (but not ** or __)
    md = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", md)
    md = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", md)

    # 7. Horizontal rules → blank line
    md = re.sub(r"^[-*_]{3,}\s*$", "", md, flags=re.MULTILINE)

    # 8. Bullet lists: leading `- ` or `* ` → `• `
    md = re.sub(r"^[\-\*]\s+", "• ", md, flags=re.MULTILINE)

    # 9. Restore placeholders
    for i, tag in enumerate(blocks):
        md = md.replace(f"\x00BLOCK{i}\x00", tag)
    for i, tag in enumerate(inline_codes):
        md = md.replace(f"\x00INLINE{i}\x00", tag)

    return md.strip()


# ── Splitting ─────────────────────────────────────────────────────────────────

def split_for_telegram(text: str, max_chars: int = _MAX_CHUNK) -> list[str]:
    """Split HTML text into conversational chunks ≤ max_chars.

    Splits preferring paragraph boundaries (double newline), then single
    newlines, then hard-cuts at max_chars.  Never splits inside a <pre> block.
    """
    chunks: list[str] = []
    remaining = text.strip()

    while len(remaining) > max_chars:
        # Avoid splitting inside a <pre> block
        pre_start = remaining.find("<pre")
        pre_end = remaining.find("</pre>")
        if 0 <= pre_start < max_chars <= pre_end:
            # The <pre> straddles the limit — push the whole block as one chunk
            # and continue with the rest.
            end = pre_end + len("</pre>")
            chunk, remaining = remaining[:end], remaining[end:].lstrip("\n")
            if chunk.strip():
                chunks.append(chunk.strip())
            continue

        # Prefer paragraph break
        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at == -1:
            # Fall back to single newline
            split_at = remaining.rfind("\n", 0, max_chars)
        if split_at == -1:
            # Hard cut
            split_at = max_chars

        chunk, remaining = remaining[:split_at], remaining[split_at:].lstrip("\n")
        if chunk.strip():
            chunks.append(chunk.strip())

    if remaining.strip():
        chunks.append(remaining.strip())

    return chunks
