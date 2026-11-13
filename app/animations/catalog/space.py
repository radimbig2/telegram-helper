import random
from collections.abc import Iterator

from app.animations.registry import animation

SKY = "⬛"
STAR = "✨"
ROWS, COLS = 7, 5


def _rocket_cell(r: int, c: int, rocket_row: int, stars: set[tuple[int, int]]) -> str:
    if c == COLS // 2:
        trail = {rocket_row: "🚀", rocket_row + 1: "🔥", rocket_row + 2: "💨"}
        if r in trail:
            return trail[r]
    return STAR if (r, c) in stars else SKY


@animation("rocket", "Rocket", "A rocket takes off into space", interval=0.55)
def rocket(args: str) -> Iterator[str]:
    stars = {(random.randrange(ROWS), random.randrange(COLS)) for _ in range(5)}
    for rocket_row in range(ROWS - 1, -2, -1):
        yield "\n".join(
            "".join(_rocket_cell(r, c, rocket_row, stars) for c in range(COLS)) for r in range(ROWS)
        )
    yield f"🌌 {args or 'We are in space!'} 👨‍🚀"

