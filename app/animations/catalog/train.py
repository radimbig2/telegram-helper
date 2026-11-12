from collections.abc import Iterator

from app.animations.registry import animation

TRACK = "➖"
CARS = ["🚂", "🚃", "🚃", "🚃"]
WIDTH = 10


@animation("train", "Train", "A train rides across the line from right to left", interval=0.6, aliases=("choo",))
def train(args: str) -> Iterator[str]:
    for head in range(WIDTH, -len(CARS) - 1, -1):
        cells = [TRACK] * WIDTH
        for i, car in enumerate(CARS):
            pos = head + i
            if 0 <= pos < WIDTH:
                cells[pos] = car
        yield "🚉" + "".join(cells) + "🌳"
    yield f"🚉 {args or 'The train has arrived!'} 🚂"
