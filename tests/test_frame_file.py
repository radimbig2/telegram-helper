"""JSON frame-file animations: format, `{text}` token and validation."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.animations import get_animation
from app.animations.frame_file import FrameAnimationSpec, FrameFileError, load_frame_file

BASE: dict[str, Any] = {"command": "wave", "title": "Wave", "description": "Waves", "frames": ["👋", "🖐", "👋 {text}"]}


def _write(tmp_path: Path, data: dict[str, Any], name: str = "wave") -> Path:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_token_is_replaced_with_user_text() -> None:
    spec = FrameAnimationSpec.model_validate(BASE)
    assert list(spec.render("hi there")) == ["👋", "🖐", "👋 hi there"]


def test_default_text_is_used_without_args() -> None:
    spec = FrameAnimationSpec.model_validate({**BASE, "default_text": "Hello"})
    assert list(spec.render("   ")) == ["👋", "🖐", "👋 Hello"]


def test_frame_with_token_is_skipped_without_any_text() -> None:
    spec = FrameAnimationSpec.model_validate(BASE)
    assert list(spec.render("")) == ["👋", "🖐"]


def test_braces_in_user_text_are_kept_as_is() -> None:
    spec = FrameAnimationSpec.model_validate(BASE)
    assert list(spec.render("{0} {text}"))[-1] == "👋 {0} {text}"


def test_multiline_frames() -> None:
    spec = FrameAnimationSpec.model_validate({**BASE, "frames": [["⬛⬛", "⬛🟥"], "done"]})
    assert list(spec.render("")) == ["⬛⬛\n⬛🟥", "done"]


def test_usage_is_derived_from_the_token() -> None:
    assert FrameAnimationSpec.model_validate(BASE).to_animation().usage == ".wave [text]"
    no_token = FrameAnimationSpec.model_validate({**BASE, "frames": ["a", "b"]})
    assert no_token.to_animation().usage == ".wave"


def test_frames_are_plain_text() -> None:
    """The engine escapes plain-text frames, so the user's text cannot inject markup."""
    assert FrameAnimationSpec.model_validate(BASE).to_animation().html is False


@pytest.mark.parametrize(
    "broken",
    [
        {**BASE, "frames": []},
        {**BASE, "command": "Bad Name"},
        {**BASE, "interval": 0},
        {**BASE, "speed": 1},  # unknown key: probably a typo
        {key: value for key, value in BASE.items() if key != "title"},
    ],
    ids=["no-frames", "bad-command", "zero-interval", "unknown-key", "missing-title"],
)
def test_invalid_files_fail_loudly(tmp_path: Path, broken: dict[str, Any]) -> None:
    with pytest.raises(FrameFileError):
        load_frame_file(_write(tmp_path, broken))


def test_command_must_match_file_name(tmp_path: Path) -> None:
    with pytest.raises(FrameFileError, match="file name"):
        load_frame_file(_write(tmp_path, BASE, name="other"))


def test_catalog_frame_files_are_registered() -> None:
    flip = get_animation("flip")
    assert flip is not None
    assert list(flip.frames(""))[-1] == "┬─┬ ノ( ゜-゜ノ)"
    last = list(flip.frames("done"))[-1]
    assert isinstance(last, str) and last.endswith("done")
