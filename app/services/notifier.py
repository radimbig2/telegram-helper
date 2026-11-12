"""Sends notifications and cached messages to the owner."""

import logging
from pathlib import Path
from typing import Any, Literal

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BusinessConnection, FSInputFile, InlineKeyboardMarkup

from app.db import Chat, Edit, Message
from app.services.cache import CacheService
from app.services.formatting import MEDIA_ICONS, chat_name, esc, fmt_dt, message_body, truncate
from app.services.settings_store import SettingsStore

log = logging.getLogger(__name__)

SendResult = Literal["with_caption", "without_caption", "failed"]

# Media type -> (bot method, file argument name, supports caption)
_SENDERS = {
    "photo": ("send_photo", "photo", True),
    "video": ("send_video", "video", True),
    "video_note": ("send_video_note", "video_note", False),
    "voice": ("send_voice", "voice", True),
    "audio": ("send_audio", "audio", True),
    "animation": ("send_animation", "animation", True),
    "document": ("send_document", "document", True),
    "sticker": ("send_sticker", "sticker", False),
}


class Notifier:
    def __init__(self, bot: Bot, cache: CacheService, store: SettingsStore, owner_id: int) -> None:
        self._bot = bot
        self._cache = cache
        self._store = store
        self._owner_id = owner_id

    async def text(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        await self._bot.send_message(self._owner_id, text, reply_markup=reply_markup)

    async def _send_file(
        self, media_type: str | None, path: str | None, file_id: str | None, caption: str
    ) -> SendResult:
        """Sends a file: the local copy if it exists, otherwise by file_id."""
        sender = _SENDERS.get(media_type or "")
        file = FSInputFile(path) if path and Path(path).exists() else file_id
        if not sender or not file:
            return "failed"
        method, arg, has_caption = sender
        caption_fits = has_caption and len(caption) <= 1024
        kwargs: dict[str, Any] = {arg: file}
        if caption_fits:
            kwargs["caption"] = caption
        try:
            await getattr(self._bot, method)(self._owner_id, **kwargs)
        except TelegramBadRequest as exc:
            log.warning("Cannot resend %s %s: %s", media_type, path or file_id, exc)
            return "failed"
        return "with_caption" if caption_fits else "without_caption"

    async def send_message_copy(self, msg: Message, header: str) -> None:
        """Sends a cached message to the owner: media (if any) plus text."""
        full = f"{header}\n{message_body(msg)}"
        if not msg.media_type:
            await self.text(full)
            return
        result = await self._send_file(msg.media_type, msg.media_path, msg.file_id, full)
        if result == "failed":
            await self.text(full + "\n<i>⚠️ file is unavailable</i>")
        elif result == "without_caption":
            await self.text(full)

    async def send_edit_media(self, edit: Edit) -> None:
        """Sends the replaced file and the new one, each with its own caption."""
        for label, media_type, path, file_id in (
            ("⬅️ Before", edit.old_media_type, edit.old_media_path, edit.old_file_id),
            ("➡️ After", edit.new_media_type, edit.new_media_path, edit.new_file_id),
        ):
            caption = f"<b>{label}</b>"
            result = await self._send_file(media_type, path, file_id, caption)
            if result == "failed":
                icon = MEDIA_ICONS.get(media_type or "", "📎")
                await self.text(f"{caption}: {icon} {media_type or 'file'} <i>(file is unavailable)</i>")

    def _should_notify(self, msg: Message, chat: Chat | None, setting: str) -> bool:
        if msg.is_outgoing or not self._store.get_bool(setting):
            return False
        return chat is None or chat.notify_enabled

    async def deleted(self, messages: list[Message]) -> None:
        chats = await self._cache.chats_by_ids({m.chat_id for m in messages})
        for msg in messages:
            chat = chats.get(msg.chat_id)
            if not self._should_notify(msg, chat, "notify_deleted"):
                continue
            header = (
                f"🗑 <b>{esc(msg.from_name)}</b> deleted a message\n"
                f"💬 {esc(chat_name(chat, msg.chat_id))} · 🕒 {fmt_dt(msg.date)}"
            )
            await self.send_message_copy(msg, header)

    async def edited(self, msg: Message, edit: Edit) -> None:
        chat = await self._cache.chat(msg.chat_id)
        if not self._should_notify(msg, chat, "notify_edited"):
            return
        await self.text(edit_text(msg, edit, chat))
        if edit.media_replaced:
            await self.send_edit_media(edit)

    async def connection(self, conn: BusinessConnection) -> None:
        if conn.is_enabled:
            await self.text("🔌 <b>Business connection is active.</b> Watching chats, commands are on.")
        else:
            await self.text("🔌 <b>Business connection is off.</b> Reconnect the bot in Settings → Telegram Business.")


def edit_text(msg: Message, edit: Edit, chat: Chat | None) -> str:
    """Notification text for an edit: what was replaced and the text before/after (if it changed)."""
    if edit.media_replaced:
        old_icon = MEDIA_ICONS.get(edit.old_media_type or "", "📎")
        new_icon = MEDIA_ICONS.get(edit.new_media_type or "", "📎")
        if edit.old_media_type == edit.new_media_type:
            what = f"replaced the {edit.new_media_type} {new_icon}"
        else:
            what = f"replaced the {edit.old_media_type or 'file'} {old_icon} with a {edit.new_media_type} {new_icon}"
    else:
        what = "edited a message"
    lines = [
        f"✏️ <b>{esc(msg.from_name)}</b> {what}",
        f"💬 {esc(chat_name(chat, msg.chat_id))} · 🕒 {fmt_dt(edit.edited_at)}",
    ]
    if edit.old_text != edit.new_text:
        lines += [
            "",
            f"<b>Before:</b>\n<blockquote>{esc(truncate(edit.old_text, 1500)) or '-'}</blockquote>",
            f"<b>After:</b>\n<blockquote>{esc(truncate(edit.new_text, 1500)) or '-'}</blockquote>",
        ]
    elif edit.new_text:
        lines += ["", f"<b>Caption:</b>\n<blockquote>{esc(truncate(edit.new_text, 1500))}</blockquote>"]
    return "\n".join(lines)
