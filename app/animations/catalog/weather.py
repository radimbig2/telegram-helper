import random
from collections.abc import Iterator

from app.animations.registry import animation

ROWS, COLS = 6, 7
EMPTY = "⬛"


def _falling(drop: str, final: str, frames: int = 12) -> Iterator[str]:
    drops: list[tuple[int, int]] = []
    for _ in range(frames):
        drops = [(r + 1, c) for r, c in drops if r + 1 < ROWS]
        drops += [(0, c) for c in random.sample(range(COLS), 2)]
        cells = set(drops)
        yield "\n".join("".join(drop if (r, c) in cells else EMPTY for c in range(COLS)) for r in range(ROWS))
    yield final


@animation("snow", "Snow", "Falling snow", interval=0.6)
def snow(args: str) -> Iterator[str]:
    yield from _falling("❄️", f"☃️ {args or 'Winter is coming'}")


@animation("rain", "Rain", "Rain with a rainbow at the end", interval=0.6)
def rain(args: str) -> Iterator[str]:
    yield from _falling("💧", f"🌈 {args or 'The rain is over'}")
