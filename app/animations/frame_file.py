"""Frame-file animations: a fixed list of frames described in JSON, no code needed.

    {
      "command": "flip",
      "title": "Table flip",
      "description": "Flips the table",
      "interval": 0.7,
      "aliases": ["tableflip"],
      "default_text": "",
      "frames": [
        "(°-°)    ┬─┬",
        "(╯°□°)╯︵ ┻━┻",
        ["multi-line frame:", "one string per line"],
        "┬─┬ ノ( ゜-゜ノ)  {text}"
      ]
    }

`{text}` is replaced with the text after the command (`.flip done!`), or with `default_text` if
there is none. A frame with `{text}` is skipped when both are empty. Frames are plain text: the
engine escapes them, so the user's text is always safe.
"""

from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.animations.registry import Animation

TOKEN = "{text}"

Frame = str | list[str]


class FrameFileError(ValueError):
    pass


class FrameAnimationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    interval: float = Field(default=0.7, gt=0, le=10)
    usage: str = ""
    aliases: tuple[str, ...] = ()
    default_text: str = ""
    frames: list[Frame] = Field(min_length=1)

    @property
    def uses_text(self) -> bool:
        return any(TOKEN in _join(frame) for frame in self.frames)

    def render(self, args: str) -> Iterator[str]:
        """Frames for `.command args`."""
        text = args.strip() or self.default_text
        for frame in self.frames:
            raw = _join(frame)
            if TOKEN in raw and not text:
                continue
            yield raw.replace(TOKEN, text)

    def to_animation(self) -> Animation:
        usage = self.usage or (f".{self.command} [text]" if self.uses_text else f".{self.command}")
        return Animation(
            command=self.command,
            title=self.title,
            description=self.description,
            frames=self.render,
            interval=self.interval,
            usage=usage,
            aliases=self.aliases,
        )


def _join(frame: Frame) -> str:
    return "\n".join(frame) if isinstance(frame, list) else frame


def load_frame_file(path: Path) -> Animation:
    try:
        spec = FrameAnimationSpec.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise FrameFileError(f"Invalid animation file {path.name}:\n{exc}") from exc
    if spec.command != path.stem:
        raise FrameFileError(f"{path.name}: command '{spec.command}' must match the file name")
    return spec.to_animation()
