"""Animation registry.

To add an animation, create a module in app/animations/catalog/ with a frame generator:

    @animation("wave", "Wave", "Waves a hand 👋")
    def wave(args: str) -> Iterator[str]:
        for hand in ["👋", "🖐", "👋", "🖐"]:
            yield hand

Nothing else needs registering: catalog modules are loaded automatically.
"""

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass

FrameFn = Callable[[str], Iterable[str]]


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


_REGISTRY: dict[str, Animation] = {}
_ORDERED: list[Animation] = []


def animation(
    command: str,
    title: str,
    description: str,
    *,
    interval: float = 0.7,
    html: bool = False,
    usage: str = "",
    aliases: tuple[str, ...] = (),
) -> Callable[[FrameFn], FrameFn]:
    """Decorator that registers a frame generator under `.command` and its aliases."""

    def decorator(fn: FrameFn) -> FrameFn:
        anim = Animation(command, title, description, fn, interval, html, usage or f".{command}", aliases)
        for name in (command, *aliases):
            if name in _REGISTRY:
                raise ValueError(f"Animation command '.{name}' is already registered")
            _REGISTRY[name] = anim
        _ORDERED.append(anim)
        return fn

    return decorator


def get_animation(name: str) -> Animation | None:
    return _REGISTRY.get(name.lower())


def all_animations() -> list[Animation]:
    return list(_ORDERED)


def load_catalog() -> None:
    from app.animations import catalog

    for module in pkgutil.iter_modules(catalog.__path__):
        importlib.import_module(f"{catalog.__name__}.{module.name}")
