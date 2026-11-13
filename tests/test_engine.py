"""Animation engine: editing frames, fallback when the message cannot be edited, stopping."""

import asyncio
from dataclasses import replace
from typing import Any

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import Message

from app.animations import Animation, AnimationEngine, Target, get_animation
from tests.conftest import FRIEND_CHAT, NOW, FakeTelegram


class UneditableMessage(FakeTelegram):
    """The original message (id 1) cannot be edited; a newly sent one can."""

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        if isinstance(method, EditMessageText) and method.message_id == 1:
            self.calls.append(("EditMessageText", dict(method)))
            raise TelegramBadRequest(method, "message can't be edited")
        if isinstance(method, SendMessage):
            self.calls.append(("SendMessage", dict(method)))
            return Message(message_id=99, date=NOW, chat=FRIEND_CHAT, text=method.text)
        return await super().make_request(bot, method, timeout)


def _anim(name: str, interval: float = 0) -> Animation:
    anim = get_animation(name)
    assert anim is not None
    return replace(anim, interval=interval)


async def _play(engine: AnimationEngine, anim: Animation, args: str = "") -> None:
    await asyncio.wait_for(engine.start(anim, args, Target(FRIEND_CHAT.id, 1, "mine")), timeout=5)


def _edits(telegram: FakeTelegram) -> list[str]:
    return [params["text"] for name, params in telegram.calls if name == "EditMessageText"]


async def test_frames_are_played_by_editing(bot: Bot, telegram: FakeTelegram) -> None:
    anim = _anim("flip")
    await _play(AnimationEngine(bot, 40), anim, "done")
    assert _edits(telegram) == list(anim.frames("done"))


async def test_user_text_is_escaped_in_plain_frames(bot: Bot, telegram: FakeTelegram) -> None:
    await _play(AnimationEngine(bot, 40), _anim("clock"), "<b>x</b>")
    assert _edits(telegram)[-1] == "⏰ &lt;b&gt;x&lt;/b&gt;"


async def test_fallback_sends_first_then_deletes() -> None:
    telegram = UneditableMessage()
    bot = Bot("123456:TEST", session=telegram)
    await _play(AnimationEngine(bot, 40), _anim("moon"))
    names = telegram.names
    assert names.index("SendMessage") < names.index("DeleteBusinessMessages"), "the original must survive a failed send"
    edited_ids = {params["message_id"] for name, params in telegram.calls if name == "EditMessageText"}
    assert edited_ids == {1, 99}


async def test_frame_limit(bot: Bot, telegram: FakeTelegram) -> None:
    await _play(AnimationEngine(bot, 3), _anim("moon"))
    assert len(_edits(telegram)) == 3


async def test_stop(bot: Bot, telegram: FakeTelegram) -> None:
    engine = AnimationEngine(bot, 40)
    engine.start(_anim("moon", interval=0.05), "", Target(FRIEND_CHAT.id, 1))
    await asyncio.sleep(0.12)
    assert engine.stop(FRIEND_CHAT.id) is True
    played = len(telegram.calls)
    await asyncio.sleep(0.2)
    assert len(telegram.calls) == played
    assert 0 < played < 17
    assert engine.stop(FRIEND_CHAT.id) is False


@pytest.mark.parametrize("name", ["train", "love", "dice", "magic"])
async def test_generators_play_to_the_end(bot: Bot, telegram: FakeTelegram, name: str) -> None:
    anim = _anim(name)
    await _play(AnimationEngine(bot, 40), anim, "ok")
    assert len(_edits(telegram)) >= 2


async def test_animations_in_different_messages_run_in_parallel(bot: Bot, telegram: FakeTelegram) -> None:
    engine = AnimationEngine(bot, 40)
    slow = _anim("moon", interval=0.05)
    first = engine.start(slow, "", Target(FRIEND_CHAT.id, 1))
    second = engine.start(slow, "", Target(FRIEND_CHAT.id, 2))
    await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
    edited = [params["message_id"] for name, params in telegram.calls if name == "EditMessageText"]
    assert edited.count(1) == edited.count(2) == 17
    assert edited[:2] == [1, 2], "both play at the same time, not one after another"


async def test_oldest_animation_stops_over_the_chat_limit(bot: Bot) -> None:
    engine = AnimationEngine(bot, 40, max_per_chat=3)
    slow = _anim("moon", interval=0.05)
    tasks = [engine.start(slow, "", Target(FRIEND_CHAT.id, message_id)) for message_id in range(1, 5)]
    await asyncio.sleep(0)
    assert tasks[0].cancelled() or tasks[0].cancelling()
    assert engine.running(FRIEND_CHAT.id) == 3
    assert engine.start(slow, "", Target(FRIEND_CHAT.id + 1, 1)) and engine.running(FRIEND_CHAT.id + 1) == 1
    engine.stop(FRIEND_CHAT.id + 1)


async def test_restarting_in_the_same_message_replaces_the_animation(bot: Bot) -> None:
    engine = AnimationEngine(bot, 40)
    old = engine.start(_anim("moon", interval=0.05), "", Target(FRIEND_CHAT.id, 1))
    new = engine.start(_anim("clock", interval=0.05), "", Target(FRIEND_CHAT.id, 1))
    await asyncio.sleep(0)
    assert old.cancelling() and engine.running(FRIEND_CHAT.id) == 1
    assert engine.stop(FRIEND_CHAT.id) is True
    await asyncio.sleep(0)
    assert new.cancelled()


async def test_stop_stops_every_animation_in_the_chat(bot: Bot, telegram: FakeTelegram) -> None:
    engine = AnimationEngine(bot, 40)
    tasks = [engine.start(_anim("moon", interval=0.05), "", Target(FRIEND_CHAT.id, m)) for m in (1, 2, 3)]
    await asyncio.sleep(0.07)
    assert engine.stop(FRIEND_CHAT.id) is True
    await asyncio.sleep(0)
    assert all(task.cancelled() for task in tasks)
    assert engine.running(FRIEND_CHAT.id) == 0
