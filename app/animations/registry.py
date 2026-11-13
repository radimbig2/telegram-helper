"""Animation registry.

There are two kinds of animations, both live in app/animations/catalog/ and are loaded automatically:

* Frame files (`*.json`): a fixed list of frames with a `{text}` token for the user's text.
  This is the default choice: no code needed. See app/animations/frame_file.py for the format.

* Generators (`*.py`): for animations computed by an algorithm (random, depend on the text, drawn by a formula):

    @animation("wave", "Wave", "Waves a hand")
    def wave(args: str) -> Iterator[str]:
        for hand in ["👋", "🖐", "👋", "🖐"]:
            yield hand
"""

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Frame:
    """A frame with its own timing: `hold` seconds until the next frame (instead of the animation's interval)."""

    text: str
    hold: float


FrameFn = Callable[[str], Iterable[str | Frame]]


@dataclass(frozen=True, slots=True)
class Animation:
    command: str
    title: str
    description: str
    frames: FrameFn
    interval: float = 0.7
    html: bool = False  # True: frames are already HTML; False: the engine escapes the text
    usage: str = ""
    aliases: tuple[str, ...] = ()
    max_frames: int | None = None  # overrides ANIMATION_MAX_FRAMES for long animations such as a countdown


_REGISTRY: dict[str, Animation] = {}
_ORDERED: list[Animation] = []
_loaded = False


def register(anim: Animation) -> Animation:
    """Registers an animation under `.command` and its aliases."""
    for name in (anim.command, *anim.aliases):
        if name in _REGISTRY:
            raise ValueError(f"Animation command '.{name}' is already registered")
    for name in (anim.command, *anim.aliases):
        _REGISTRY[name] = anim
    _ORDERED.append(anim)
    return anim


def animation(
    command: str,
    title: str,
    description: str,
    *,
    interval: float = 0.7,
    html: bool = False,
    usage: str = "",
    aliases: tuple[str, ...] = (),
    max_frames: int | None = None,
) -> Callable[[FrameFn], FrameFn]:
    """Decorator that registers a frame generator."""

    def decorator(fn: FrameFn) -> FrameFn:
        register(
            Animation(command, title, description, fn, interval, html, usage or f".{command}", aliases, max_frames)
        )
        return fn

    return decorator


def get_animation(name: str) -> Animation | None:
    return _REGISTRY.get(name.lower())


def all_animations() -> list[Animation]:
    return list(_ORDERED)


def load_catalog() -> None:
    """Loads every animation from the catalog: generator modules and frame files, in file name order."""
    global _loaded
    if _loaded:
        return
    from app.animations import catalog
    from app.animations.frame_file import load_frame_file

    catalog_dir = Path(catalog.__file__).parent
    for path in sorted(catalog_dir.iterdir(), key=lambda p: p.stem):
        if path.suffix == ".json":
            register(load_frame_file(path))
        elif path.suffix == ".py" and not path.name.startswith("_"):
            importlib.import_module(f"{catalog.__name__}.{path.stem}")
    _loaded = True
