"""`.countdown`: durations, the tick schedule and real-time playback."""

from typing import Any

import pytest
from aiogram import Bot

from app.animations import AnimationEngine, Frame, Target, get_animation
from app.animations.catalog import countdown
from tests.conftest import FRIEND_CHAT, FakeTelegram


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float, *args: Any) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(countdown.time, "monotonic", fake.monotonic)
    monkeypatch.setattr("app.animations.engine.asyncio.sleep", fake.sleep)
    return fake


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ("300", (300, "")),
        ("5m", (300, "")),
        ("1m30s", (90, "")),
        ("1:30", (90, "")),
        ("1:00:00", (3600, "")),
        ("90s pizza is ready", (90, "pizza is ready")),
        ("pizza is ready", (5, "pizza is ready")),
        ("", (5, "")),
        ("0", (1, "")),
        ("99999", (3600, "")),
    ],
)
def test_parse_args(args: str, expected: tuple[int, str]) -> None:
    assert countdown.parse_args(args) == expected


def test_ticks_every_5_seconds_then_every_second_in_the_last_minute() -> None:
    schedule = countdown.ticks(302)
    assert schedule[:3] == [302, 300, 295]
    assert schedule[-60:] == list(range(60, 0, -1)) and schedule[-61] == 65
    assert len(countdown.ticks(10)) == 10


def test_display() -> None:
    assert countdown.display(3600) == "⏳ 1:00:00"
    assert countdown.display(300) == "⏳ 5:00"
    assert countdown.display(45) == "⏳ 0:45"
    assert countdown.display(7) == "💣 7️⃣"


async def test_plays_in_real_time(bot: Bot, telegram: FakeTelegram, clock: FakeClock) -> None:
    anim = get_animation("countdown")
    assert anim is not None
    engine = AnimationEngine(bot, max_frames=40)
    await engine.start(anim, "3 done", Target(FRIEND_CHAT.id, 1))

    edits = [params["text"] for name, params in telegram.calls if name == "EditMessageText"]
    assert edits == ["💣 3️⃣", "💣 2️⃣", "💣 1️⃣", "💥💥💥 done 💥💥💥"]
    assert sum(clock.slept) == pytest.approx(3)


async def test_five_minutes_is_not_cut_by_the_frame_limit(
    bot: Bot, telegram: FakeTelegram, clock: FakeClock
) -> None:
    anim = get_animation("countdown")
    assert anim is not None
    engine = AnimationEngine(bot, max_frames=40)
    await engine.start(anim, "5m", Target(FRIEND_CHAT.id, 1))

    edits = [params["text"] for name, params in telegram.calls if name == "EditMessageText"]
    assert edits[0] == "⏳ 5:00" and edits[-1] == "💥💥💥 BOOM! 💥💥💥"
    assert len(edits) == len(countdown.ticks(300)) + 1
    assert sum(clock.slept) == pytest.approx(300)


def test_late_ticks_are_skipped(clock: FakeClock) -> None:
    """If an edit was delayed (flood control), the countdown jumps to the current value instead of lagging."""
    frames = countdown.countdown("300")
    first = next(iter(frames))
    assert isinstance(first, Frame) and first.text == "⏳ 5:00"
    clock.now += 12  # the next edit happened 12 s later instead of 5
    second = next(iter(frames))
    assert isinstance(second, Frame) and second.text == "⏳ 4:50"
    assert second.hold == pytest.approx(3)
