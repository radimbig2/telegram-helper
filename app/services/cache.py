"""Message cache: saving, edit history, deletions and queries for the panel."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from aiogram.types import BusinessConnection as TgConnection
from aiogram.types import Chat as TgChat
from aiogram.types import Message as TgMessage
from sqlalchemy import Select, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import Chat, Connection, Database, Edit, Message
from app.services.media import MediaService, extract_media
from app.services.settings_store import SettingsStore

log = logging.getLogger(__name__)

ChatFlag = Literal["save_enabled", "notify_enabled"]

EVICTION_TARGET = 0.9  # after hitting the limit, free space down to 90% of it to avoid constant cleanups
EVICTION_BATCH = 500


@dataclass(slots=True)
class EvictionResult:
    used_before: int
    used_after: int = 0
    files_removed: int = 0
    messages_removed: int = 0


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        return max(1, (self.total + self.size - 1) // self.size)

    @property
    def first_number(self) -> int:
        """1-based number of the first item on this page."""
        return self.page * self.size + 1


@dataclass(frozen=True, slots=True)
class Stats:
    messages: int
    deleted: int
    edited: int
    media: int
    chats: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _message_text(message: TgMessage) -> str:
    return message.text or message.caption or ""


def _by_tg_id(chat_id: int, message_id: int) -> Select[tuple[Message]]:
    return select(Message).where(Message.chat_id == chat_id, Message.message_id == message_id)


class CacheService:
    def __init__(self, db: Database, media: MediaService, store: SettingsStore, owner_id: int) -> None:
        self._db = db
        self._media = media
        self._store = store
        self.owner_id = owner_id

    # ---------- writes ----------

    async def _upsert_chat(self, s: AsyncSession, tg_chat: TgChat) -> Chat:
        chat = await s.get(Chat, tg_chat.id)
        title = tg_chat.full_name or tg_chat.title or str(tg_chat.id)
        if chat is None:
            # Explicit values: model defaults apply only on flush, but the flags are read right away.
            chat = Chat(id=tg_chat.id, title=title, username=tg_chat.username, save_enabled=True, notify_enabled=True)
            s.add(chat)
        else:
            chat.title, chat.username = title, tg_chat.username
        chat.last_message_at = _utcnow()
        return chat

    async def save_message(self, message: TgMessage) -> Message | None:
        """Saves a new message. Returns None if saving is disabled for the chat."""
        info = extract_media(message)
        async with self._db.session() as s:
            chat = await self._upsert_chat(s, message.chat)
            existing = await s.scalar(_by_tg_id(message.chat.id, message.message_id))
            if not chat.save_enabled or existing:
                await s.commit()
                return existing if chat.save_enabled else None

            sender = message.from_user
            row = Message(
                chat_id=message.chat.id,
                message_id=message.message_id,
                connection_id=message.business_connection_id,
                from_id=sender.id if sender else None,
                from_name=sender.full_name if sender else "",
                is_outgoing=bool(sender and sender.id == self.owner_id),
                text=_message_text(message),
                media_type=info.type if info else None,
                file_id=info.file_id if info else None,
                file_unique_id=info.file_unique_id if info else None,
                date=message.date or _utcnow(),
            )
            s.add(row)
            await s.commit()

        if info and self._store.get_bool("save_media"):
            await self._attach_media(row, message)
        return row

    async def _attach_media(self, row: Message, message: TgMessage) -> None:
        info = extract_media(message)
        if info is None:
            return
        path = await self._media.download(info, message.chat.id, message.message_id)
        if not path:
            return
        async with self._db.session() as s:
            await s.execute(update(Message).where(Message.id == row.id).values(media_path=path))
            await s.commit()
        row.media_path = path

    async def save_media_now(self, message: TgMessage) -> Message | None:
        """Force-saves a message and its media (the .save command)."""
        row = await self.save_message(message)
        if row is not None and row.media_type and not row.media_path:
            await self._attach_media(row, message)
        return row

    async def record_edit(self, message: TgMessage) -> tuple[Message, Edit] | None:
        """Records an edit. Returns (message, edit) if someone else's message actually changed.

        The owner's own messages only get their text updated, without history: every animation
        frame and every `.time` is an edit of the owner's message and would flood the history.
        """
        new_text = _message_text(message)
        info = extract_media(message)
        async with self._db.session() as s:
            row = await s.scalar(_by_tg_id(message.chat.id, message.message_id))
            if row is None:
                await s.commit()
                await self.save_message(message)
                return None

            media_changed = bool(info and info.file_unique_id != row.file_unique_id)
            if new_text == row.text and not media_changed:
                return None
            if row.is_outgoing:
                row.text = new_text
                await s.commit()
                return None

            edit = Edit(message_pk=row.id, old_text=row.text, new_text=new_text)
            s.add(edit)
            row.text, row.is_edited = new_text, True
            if media_changed and info:
                row.media_type, row.file_id, row.file_unique_id = info.type, info.file_id, info.file_unique_id
                row.media_path = None
            await s.commit()

        if media_changed and self._store.get_bool("save_media"):
            await self._attach_media(row, message)
        return row, edit

    async def mark_deleted(self, chat_id: int, message_ids: list[int]) -> list[Message]:
        """Marks messages as deleted and returns those that were cached."""
        async with self._db.session() as s:
            query = select(Message).where(Message.chat_id == chat_id, Message.message_id.in_(message_ids))
            rows = list(await s.scalars(query))
            now = _utcnow()
            for row in rows:
                row.is_deleted, row.deleted_at = True, now
            await s.commit()
        return rows

    async def save_connection(self, conn: TgConnection) -> None:
        rights = conn.rights.model_dump(exclude_none=True) if conn.rights else {}
        async with self._db.session() as s:
            await s.merge(
                Connection(
                    id=conn.id,
                    user_id=conn.user.id,
                    user_chat_id=conn.user_chat_id,
                    is_enabled=conn.is_enabled,
                    rights=",".join(name for name, enabled in rights.items() if enabled),
                )
            )
            await s.commit()

    # ---------- reads for the panel ----------

    async def _page[T](self, query: Select[tuple[T]], page: int, size: int) -> Page[T]:
        async with self._db.session() as s:
            total = await s.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
            items = list(await s.scalars(query.limit(size).offset(page * size)))
        return Page(items, total, page, size)

    async def deleted(self, page: int, size: int, chat_id: int | None = None) -> Page[Message]:
        query = select(Message).where(Message.is_deleted, ~Message.is_outgoing)
        if chat_id is not None:
            query = query.where(Message.chat_id == chat_id)
        return await self._page(query.order_by(Message.deleted_at.desc()), page, size)

    async def edits(self, page: int, size: int) -> Page[Edit]:
        query = (
            select(Edit)
            .join(Message)
            .where(~Message.is_outgoing)
            .options(selectinload(Edit.message))
            .order_by(Edit.edited_at.desc())
        )
        return await self._page(query, page, size)

    async def media(self, page: int, size: int) -> Page[Message]:
        query = (
            select(Message)
            .where(Message.media_type.is_not(None), ~Message.is_outgoing)
            .order_by(Message.date.desc())
        )
        return await self._page(query, page, size)

    async def search(self, query: str, page: int, size: int) -> Page[Message]:
        tokens = re.findall(r"\w+", query.lower())
        if not tokens:
            return Page([], 0, page, size)
        fts_query = " ".join(f'"{token}"*' for token in tokens)  # prefix match for every word
        ids = select(text("rowid")).select_from(text("messages_fts")).where(text("messages_fts MATCH :q"))
        stmt = select(Message).where(Message.id.in_(ids)).order_by(Message.date.desc()).params(q=fts_query)
        return await self._page(stmt, page, size)

    async def chats(self, page: int, size: int) -> Page[Chat]:
        return await self._page(select(Chat).order_by(Chat.last_message_at.desc()), page, size)

    async def chat(self, chat_id: int) -> Chat | None:
        async with self._db.session() as s:
            return await s.get(Chat, chat_id)

    async def chats_by_ids(self, ids: set[int]) -> dict[int, Chat]:
        if not ids:
            return {}
        async with self._db.session() as s:
            return {chat.id: chat for chat in await s.scalars(select(Chat).where(Chat.id.in_(ids)))}

    async def toggle_chat(self, chat_id: int, flag: ChatFlag) -> Chat | None:
        async with self._db.session() as s:
            chat = await s.get(Chat, chat_id)
            if chat:
                setattr(chat, flag, not getattr(chat, flag))
                await s.commit()
            return chat

    async def message(self, pk: int) -> Message | None:
        async with self._db.session() as s:
            return await s.get(Message, pk)

    async def connection(self) -> Connection | None:
        """The current connection: an active one wins over a newer but disabled (stale) one."""
        query = select(Connection).order_by(Connection.is_enabled.desc(), Connection.updated_at.desc()).limit(1)
        async with self._db.session() as s:
            return await s.scalar(query)

    async def stats(self) -> Stats:
        """Counters for the home screen; each one uses the same filter as its panel section."""
        others = ~Message.is_outgoing
        async with self._db.session() as s:

            async def count(query: Select[tuple[int]]) -> int:
                return await s.scalar(query) or 0

            return Stats(
                messages=await count(select(func.count(Message.id))),
                deleted=await count(select(func.count(Message.id)).where(Message.is_deleted, others)),
                edited=await count(select(func.count(Edit.id)).join(Message).where(others)),
                media=await count(select(func.count(Message.id)).where(Message.media_type.is_not(None), others)),
                chats=await count(select(func.count(Chat.id))),
            )

    # ---------- maintenance ----------

    async def used_bytes(self) -> int:
        """Disk space used by the cache: media files plus database data."""
        return self._media.total_size() + await self._db.used_bytes()

    async def enforce_size_limit(self, limit_bytes: int) -> EvictionResult:
        """Keeps the cache under the limit.

        When the limit is exceeded, frees space down to EVICTION_TARGET of it: first the oldest
        media files (the message text stays), then, if that is not enough, the oldest messages.
        """
        used = await self.used_bytes()
        result = EvictionResult(used_before=used)
        if used <= limit_bytes:
            return result
        target = int(limit_bytes * EVICTION_TARGET)

        removed_paths: list[str] = []
        for file in self._media.files_oldest_first():
            if used <= target:
                break
            file.path.unlink(missing_ok=True)
            removed_paths.append(str(file.path))
            used -= file.size
        await self._forget_media(removed_paths)
        result.files_removed = len(removed_paths)

        while used > target:
            async with self._db.session() as s:
                ids = list(await s.scalars(select(Message.id).order_by(Message.date).limit(EVICTION_BATCH)))
                if not ids:
                    break
                await s.execute(delete(Message).where(Message.id.in_(ids)))
                await s.commit()
            result.messages_removed += len(ids)
            used = await self.used_bytes()

        result.used_after = used
        log.info(
            "Cache limit: %d -> %d bytes, removed %d files and %d messages",
            result.used_before, used, result.files_removed, result.messages_removed,
        )
        return result

    async def _forget_media(self, paths: list[str]) -> None:
        """Clears media_path for files that were removed from disk."""
        for start in range(0, len(paths), EVICTION_BATCH):
            chunk = paths[start : start + EVICTION_BATCH]
            async with self._db.session() as s:
                await s.execute(update(Message).where(Message.media_path.in_(chunk)).values(media_path=None))
                await s.commit()
