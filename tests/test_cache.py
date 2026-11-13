"""Message cache: edits, replaced media, migrations and the size limit."""

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aiogram.types import PhotoSize
from sqlalchemy import func, select

from app.bot import views
from app.config import Settings
from app.db import Database, Edit, Message
from app.services.cache import CacheService
from tests.conftest import FRIEND, OWNER, Feeder, FakeTelegram, business_message

MB = 1024 * 1024


def _photo(unique_id: str) -> list[PhotoSize]:
    return [PhotoSize(file_id=f"fid_{unique_id}", file_unique_id=unique_id, width=10, height=10, file_size=100)]


async def test_own_edits_update_text_without_history(services: dict[str, Any]) -> None:
    cache: CacheService = services["cache"]
    await cache.save_message(business_message(OWNER, 1, ".snow"))
    for frame in ["❄️", "❄️❄️", "☃️ Winter"]:
        assert await cache.record_edit(business_message(OWNER, 1, frame)) is None
    own = await cache.message(1)
    assert own is not None and own.text == "☃️ Winter" and not own.is_edited

    await cache.save_message(business_message(FRIEND, 2, "hello"))
    assert await cache.record_edit(business_message(FRIEND, 2, "hello!")) is not None
    stats = await cache.stats()
    assert stats.edited == 1 == (await cache.edits(0, 5)).total


async def test_replaced_photo_sends_old_and_new(feed: Feeder, telegram: FakeTelegram, settings: Settings) -> None:
    await feed(business_message=business_message(FRIEND, 7, photo=_photo("A")))
    await feed(edited_business_message=business_message(FRIEND, 7, photo=_photo("B")))

    sent = telegram.sent()
    assert [name for name, _ in sent] == ["SendMessage", "SendPhoto", "SendPhoto"]
    assert "replaced the photo" in sent[0][1]["text"] and "Before:" not in sent[0][1]["text"]
    assert Path(sent[1][1]["photo"].path).name == "7_A.jpg"
    assert Path(sent[2][1]["photo"].path).name == "7_B.jpg"
    assert sorted(p.name for p in (settings.media_dir / str(FRIEND.id)).iterdir()) == ["7_A.jpg", "7_B.jpg"]


async def test_replaced_photo_with_new_caption_shows_text_diff(feed: Feeder, telegram: FakeTelegram) -> None:
    await feed(business_message=business_message(FRIEND, 7, photo=_photo("A")))
    await feed(edited_business_message=business_message(FRIEND, 7, photo=_photo("B"), caption="new caption"))
    text = telegram.sent()[0][1]["text"]
    assert "Before:" in text and "new caption" in text


async def test_edit_history_replays_replaced_files(
    feed: Feeder, telegram: FakeTelegram, services: dict[str, Any]
) -> None:
    await feed(business_message=business_message(FRIEND, 7, photo=_photo("A")))
    await feed(edited_business_message=business_message(FRIEND, 7, photo=_photo("B")))
    text, keyboard = await views.edits(services["cache"], 0)
    assert "file replaced" in text
    button = keyboard.inline_keyboard[0][0]
    assert button.callback_data and button.callback_data.startswith("act:edit_media:")

    from aiogram.types import CallbackQuery

    await feed(callback_query=CallbackQuery(id="1", from_user=OWNER, chat_instance="x", data=button.callback_data))
    assert [name for name, _ in telegram.sent()] == ["SendMessage", "SendPhoto", "SendPhoto"]


async def test_old_database_gets_new_columns(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE edits (id INTEGER PRIMARY KEY, message_pk INTEGER, old_text TEXT, "
                    "new_text TEXT, edited_at DATETIME)")
    db = Database(path)
    await db.create_schema()
    await db.close()
    with sqlite3.connect(path) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(edits)")}
    assert {"old_media_path", "new_media_path", "new_file_id"} <= columns


async def _fill(cache: CacheService, settings: Settings, count: int = 6, size: int = 300 * 1024) -> None:
    """`count` messages with a file each, oldest first, and one edit on the newest."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with cache._db.session() as s:
        for i in range(count):
            path = settings.media_dir / "42" / f"{i}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * size)
            os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))
            row = Message(chat_id=42, message_id=i, text=f"msg {i}", media_type="photo", media_path=str(path),
                          date=base + timedelta(hours=i))
            s.add(row)
        await s.flush()
        s.add(Edit(message_pk=row.id, old_text="a", new_text="b", old_media_path=str(path)))
        await s.commit()


async def test_size_limit_removes_oldest_files_first(services: dict[str, Any], settings: Settings) -> None:
    cache: CacheService = services["cache"]
    await _fill(cache, settings)

    result = await cache.enforce_size_limit(MB)
    assert result.files_removed >= 3 and result.messages_removed == 0 and result.used_after <= MB * 0.9
    assert "0.jpg" not in {p.name for p in settings.media_dir.rglob("*.jpg")}, "the oldest file goes first"
    async with cache._db.session() as s:
        assert await s.scalar(select(func.count(Message.id))) == 6, "texts stay"
        cleared = await s.scalar(select(func.count()).where(Message.media_path.is_(None)))
    assert cleared == result.files_removed

    again = await cache.enforce_size_limit(MB)
    assert (again.files_removed, again.messages_removed) == (0, 0), "under the limit nothing happens"


async def test_size_limit_removes_messages_when_files_are_not_enough(
    services: dict[str, Any], settings: Settings
) -> None:
    cache: CacheService = services["cache"]
    await _fill(cache, settings)
    result = await cache.enforce_size_limit(1)
    assert result.messages_removed == 6
    async with cache._db.session() as s:
        assert await s.scalar(select(func.count(Edit.id))) == 0, "edits go with their message"


async def test_removed_files_are_forgotten_by_edits(services: dict[str, Any], settings: Settings) -> None:
    cache: CacheService = services["cache"]
    await _fill(cache, settings, count=2)
    edit = (await cache.edits(0, 5)).items[0]
    await cache._forget_media([edit.old_media_path or ""])
    reloaded = await cache.edit(edit.id)
    assert reloaded is not None and reloaded.old_media_path is None
