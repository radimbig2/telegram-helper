from collections.abc import Iterator

from app.animations.registry import animation

COLORS = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪"]
ROWS, COLS = 5, 6
STEPS = 12


def _stripes(shift: int) -> str:
    """Diagonal rainbow stripes moved by `shift` cells."""
    return "\n".join(
        "".join(COLORS[(r + c + shift) % len(COLORS)] for c in range(COLS)) for r in range(ROWS)
    )


@animation("rainbow", "Rainbow", "Rainbow stripes flow across the message", interval=0.45, usage=".rainbow [text]")
def rainbow(args: str) -> Iterator[str]:
    for shift in range(STEPS, 0, -1):
        yield _stripes(shift)
    yield f"🌈 {args or 'Rainbow!'} 🌈"
