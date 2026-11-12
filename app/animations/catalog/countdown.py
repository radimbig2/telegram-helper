from collections.abc import Iterator

from app.animations.registry import animation

KEYCAPS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _parse_start(args: str, default: int = 5) -> int:
    try:
        return max(1, min(10, int(args.split()[0]))) if args else default
    except ValueError:
        return default


@animation("countdown", "Countdown", "Counts down from N to 1 and explodes", interval=1.0, usage=".countdown 5")
def countdown(args: str) -> Iterator[str]:
    for n in range(_parse_start(args), 0, -1):
        yield f"💣 {KEYCAPS[n]}"
    yield "💥💥💥 BOOM! 💥💥💥"
