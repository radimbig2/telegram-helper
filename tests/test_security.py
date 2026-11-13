"""Outsiders must have no influence: no replies, no state changes, nothing cached from foreign accounts."""

import asyncio
from typing import Any

import pytest
from aiogram.types import BusinessConnection, CallbackQuery, Chat, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated

from app.services.media import _ext_from_name
from tests.conftest import (
    BOT_USER, FRIEND, NOW, OWNER, STRANGER, Feeder, FakeTelegram, business_message, private_message,
)


@pytest.mark.parametrize("text", ["/start", "/menu", "/search x", "/help", "hello", "Warsaw"])
async def test_stranger_in_bot_chat_gets_no_answer(feed: Feeder, text: str) -> None:
    assert await feed(message=private_message(STRANGER, text)) == []


async def test_stranger_cannot_press_panel_buttons(feed: Feeder, services: dict[str, Any]) -> None:
    press = CallbackQuery(id="1", from_user=STRANGER, chat_instance="x", data="act:set:0:save_media")
    assert await feed(callback_query=press) == []
    assert services["store"].get_bool("save_media") is True


async def test_owner_panel_works(feed: Feeder) -> None:
    assert "SendMessage" in await feed(message=private_message(OWNER, "/start"))


async def test_contact_cannot_run_dot_commands(feed: Feeder, services: dict[str, Any]) -> None:
    calls = await feed(business_message=business_message(FRIEND, 70, ".train"))
    assert calls in ([], ["GetBusinessConnection"])
    assert (await services["cache"].stats()).messages == 1, "the message is still cached"


async def test_owner_runs_dot_commands(feed: Feeder, telegram: FakeTelegram) -> None:
    await feed(business_message=business_message(OWNER, 71, ".dice"))
    await asyncio.sleep(0.5)
    assert "EditMessageText" in telegram.names


async def test_foreign_business_account_is_ignored(feed: Feeder, services: dict[str, Any]) -> None:
    connection = BusinessConnection(id="theirs", user=STRANGER, user_chat_id=STRANGER.id, date=NOW, is_enabled=True)
    assert await feed(business_connection=connection) == []
    assert await feed(business_message=business_message(STRANGER, 81, ".train", connection="theirs")) == []
    assert await feed(business_message=business_message(FRIEND, 82, "hi", connection="theirs")) == []
    assert (await services["cache"].stats()).messages == 0
    assert await services["cache"].connection() is None


async def test_bot_leaves_groups(feed: Feeder) -> None:
    group = Chat(id=-100, type="supergroup", title="Spam")
    added = ChatMemberUpdated(
        chat=group, from_user=STRANGER, date=NOW,
        old_chat_member=ChatMemberLeft(user=BOT_USER), new_chat_member=ChatMemberMember(user=BOT_USER),
    )
    assert await feed(my_chat_member=added) == ["LeaveChat"]


async def test_panel_never_answers_in_groups(feed: Feeder) -> None:
    group = Chat(id=-100, type="supergroup", title="Group")
    assert await feed(message=private_message(OWNER, "/menu", chat=group)) == []


@pytest.mark.parametrize(
    ("name", "expected"),
    [("x./../../../etc/passwd", "etcpasswd"), ("a.b/c", "bc"), ("photo.JPG", "jpg"), ("a./..", "bin"), (None, "bin")],
)
def test_file_extensions_from_senders_are_sanitized(name: str | None, expected: str) -> None:
    assert _ext_from_name(name, "bin") == expected
