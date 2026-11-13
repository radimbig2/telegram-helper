"""Every animation in the catalog must play well in Telegram, whatever the user types after the command."""

import random
from html.parser import HTMLParser
from itertools import islice

import pytest

from app.animations import Animation, Frame, all_animations, load_catalog
from app.config import Settings

load_catalog()  # parametrization below runs at collection time, before fixtures

TELEGRAM_TEXT_LIMIT = 4096
MAX_FRAMES = Settings.model_fields["animation_max_frames"].default
ARGS = ["", "hello", "<b>&{text}</b>", "x" * 300, "多言語 文字 🎉"]
SEEDS = range(5)


def _limit(anim: Animation) -> int:
    return anim.max_frames or MAX_FRAMES


def _frames(anim: Animation, args: str) -> list[str]:
    # one frame past the limit, to notice animations that would be cut off
    items = islice(anim.frames(args), _limit(anim) + 1)
    return [item.text if isinstance(item, Frame) else item for item in items]


def test_catalog_is_loaded() -> None:
    commands = {anim.command for anim in all_animations()}
    assert {"train", "love", "flip", "clock", "moon", "dice"} <= commands


@pytest.mark.parametrize("anim", all_animations(), ids=lambda a: a.command)
@pytest.mark.parametrize("args", ARGS, ids=["empty", "word", "markup", "long", "unicode"])
def test_frames_fit_telegram(anim: Animation, args: str) -> None:
    for seed in SEEDS:
        random.seed(seed)
        frames = _frames(anim, args)
        assert frames, "at least one frame"
        assert len(frames) <= _limit(anim), "would be cut off by the frame limit"
        assert all(frame.strip() for frame in frames), "empty frames are skipped by the engine"
        assert all(len(frame) <= TELEGRAM_TEXT_LIMIT for frame in frames)
        assert len(set(frames)) > 1, "an animation must change"


class _StrictHTML(HTMLParser):
    ALLOWED = {"b", "i", "u", "s", "code", "pre", "blockquote", "tg-spoiler"}

    def __init__(self) -> None:
        super().__init__()
        self.open: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        assert tag in self.ALLOWED, f"unexpected tag <{tag}>"
        self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.open and self.open.pop() == tag, f"unbalanced </{tag}>"


@pytest.mark.parametrize("anim", [a for a in all_animations() if a.html], ids=lambda a: a.command)
def test_html_animations_escape_user_text(anim: Animation) -> None:
    for frame in _frames(anim, "<script>&</script>"):
        assert "<script>" not in frame
        parser = _StrictHTML()
        parser.feed(frame)
        parser.close()
        assert not parser.open, f"unclosed tags {parser.open}"


def test_commands_and_aliases_are_unique() -> None:
    names = [name for anim in all_animations() for name in (anim.command, *anim.aliases)]
    assert len(names) == len(set(names))
