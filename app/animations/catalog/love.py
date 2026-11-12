from collections.abc import Iterator

from app.animations.registry import animation

HEART = [
    "0110110",
    "1111111",
    "1111111",
    "0111110",
    "0011100",
    "0001000",
]
BACKGROUND = "🤍"
COLORS = ["❤️", "🧡", "💛", "💚", "💙", "💜", "❤️"]


def _draw(rows: int, fill: str) -> str:
    return "\n".join(
        "".join(fill if (cell == "1" and r < rows) else BACKGROUND for cell in row) for r, row in enumerate(HEART)
    )


@animation("love", "Heart", "A heart is drawn row by row and shimmers in colors", interval=0.6, aliases=("heart",))
def love(args: str) -> Iterator[str]:
    for rows in range(1, len(HEART) + 1):
        yield _draw(rows, "❤️")
    for color in COLORS:
        yield _draw(len(HEART), color)
    yield f"❤️ {args or 'Love you'} ❤️"
