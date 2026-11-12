"""Sends notifications and cached messages to the owner."""

import logging
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BusinessConnection, FSInputFile, InlineKeyboardMarkup

from app.db import Chat, Edit, Message
from app.services.cache import CacheService
from app.services.formatting import chat_name, esc, fmt_dt, message_body, truncate
from app.services.settings_store import SettingsStore

log = logging.getLogger(__name__)

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

    async def send_message_copy(self, msg: Message, header: str) -> None:
        """Sends a cached message to the owner: media (if any) plus text."""
        body = message_body(msg)
        full = f"{header}\n{body}"
        sender = _SENDERS.get(msg.media_type or "")
        if not sender:
            await self.text(full)
            return

        method, arg, has_caption = sender
        file = FSInputFile(msg.media_path) if msg.media_path and Path(msg.media_path).exists() else msg.file_id
        if not file:
            await self.text(full)
            return

        caption_fits = has_caption and len(full) <= 1024
        kwargs: dict[str, Any] = {arg: file}
        if caption_fits:
            kwargs["caption"] = full
        try:
            await getattr(self._bot, method)(self._owner_id, **kwargs)
        except TelegramBadRequest as exc:
            log.warning("Cannot resend media %s: %s", msg.id, exc)
            await self.text(full + "\n<i>⚠️ file is unavailable</i>")
            return
        if not caption_fits:
            await self.text(full)

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
        await self.text(
            f"✏️ <b>{esc(msg.from_name)}</b> edited a message\n"
            f"💬 {esc(chat_name(chat, msg.chat_id))} · 🕒 {fmt_dt(edit.edited_at)}\n\n"
            f"<b>Before:</b>\n<blockquote>{esc(truncate(edit.old_text, 1500)) or '-'}</blockquote>\n"
            f"<b>After:</b>\n<blockquote>{esc(truncate(edit.new_text, 1500)) or '-'}</blockquote>"
        )

    async def connection(self, conn: BusinessConnection) -> None:
        if conn.is_enabled:
            await self.text("🔌 <b>Business connection is active.</b> Watching chats, commands are on.")
        else:
            await self.text("🔌 <b>Business connection is off.</b> Reconnect the bot in Settings → Telegram Business.")
