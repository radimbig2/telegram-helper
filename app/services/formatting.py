"""Text formatting for bot messages (HTML)."""

from datetime import datetime, timezone, tzinfo
from html import escape

from app.db import Chat, Message

MEDIA_ICONS: dict[str, str] = {
    "photo": "🖼",
    "video": "🎬",
    "video_note": "⏺",
    "voice": "🎤",
    "audio": "🎵",
    "animation": "🎞",
    "document": "📄",
    "sticker": "🏷",
}


def esc(text: str | None) -> str:
    return escape(text or "", quote=False)


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


_display_tz: tzinfo = timezone.utc


def set_display_timezone(tz: tzinfo) -> None:
    """Sets the time zone used to show times in the panel (the owner's time zone)."""
    global _display_tz
    _display_tz = tz


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:  # SQLite returns naive datetimes; they are always UTC
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_display_tz).strftime("%d.%m %H:%M")


def fmt_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def chat_name(chat: Chat | None, fallback_id: int | None = None) -> str:
    if chat is None:
        return f"chat {fallback_id}"
    if chat.username:
        return f"{chat.title} (@{chat.username})"
    return chat.title or f"chat {chat.id}"


def message_body(msg: Message, limit: int = 600) -> str:
    """Message text plus a media marker."""
    parts: list[str] = []
    if msg.media_type:
        icon = MEDIA_ICONS.get(msg.media_type, "📎")
        saved = "" if msg.media_path else " (file not saved)"
        parts.append(f"{icon} {msg.media_type}{saved}")
    if msg.text:
        parts.append(f"<blockquote>{esc(truncate(msg.text, limit))}</blockquote>")
    return "\n".join(parts) or "<i>empty</i>"
