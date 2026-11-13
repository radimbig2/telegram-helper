"""A real-time countdown: `.countdown 300`, `.countdown 5m`, `.countdown 1:30 pizza is ready`."""

import re
import time
from collections.abc import Iterator

from app.animations.registry import Frame, animation

KEYCAPS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
DEFAULT_SECONDS = 5
MAX_SECONDS = 60 * 60
EVERY_SECOND_FROM = 60  # the last minute ticks every second; before that, every 5 seconds (fewer edits)
COARSE_STEP = 5

_UNITS_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$", re.IGNORECASE)
_CLOCK_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d{2})$")


def parse_duration(token: str) -> int | None:
    """Seconds from `300`, `90s`, `5m`, `1m30s`, `1h`, `1:30` or `1:00:00`; None if it is not a duration."""
    if match := _CLOCK_RE.match(token):
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    match = _UNITS_RE.match(token)
    if not token or not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def parse_args(args: str) -> tuple[int, str]:
    """(seconds, text for the final frame). Without a duration, the whole input is the text."""
    first, _, rest = args.strip().partition(" ")
    seconds = parse_duration(first)
    if seconds is None:
        return DEFAULT_SECONDS, args.strip()
    return max(1, min(MAX_SECONDS, seconds)), rest.strip()


def ticks(total: int) -> list[int]:
    """Remaining seconds to show, from `total` down to 1."""
    values = [total]
    while values[-1] > 1:
        current = values[-1]
        if current > EVERY_SECOND_FROM:
            values.append(max(EVERY_SECOND_FROM, (current - 1) // COARSE_STEP * COARSE_STEP))
        else:
            values.append(current - 1)
    return values


def display(remaining: int) -> str:
    if remaining <= 10:
        return f"💣 {KEYCAPS[remaining]}"
    hours, rest = divmod(remaining, 3600)
    minutes, seconds = divmod(rest, 60)
    clock = f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"
    return f"⏳ {clock}"


@animation(
    "countdown",
    "Countdown",
    "Counts down in real time (up to an hour) and explodes",
    interval=1.0,
    usage=".countdown 5m [text]",
    max_frames=MAX_SECONDS // COARSE_STEP + EVERY_SECOND_FROM + 2,
)
def countdown(args: str) -> Iterator[str | Frame]:
    total, text = parse_args(args)
    schedule = ticks(total)
    start = time.monotonic()
    for i, remaining in enumerate(schedule):
        is_last = i + 1 == len(schedule)
        next_due = start + total - (0 if is_last else schedule[i + 1])
        hold = next_due - time.monotonic()
        if hold <= 0 and not is_last:
            continue  # already late (flood control): skip straight to the current value
        yield Frame(display(remaining), max(0.0, hold))
    yield Frame(f"💥💥💥 {text or 'BOOM!'} 💥💥💥", hold=0)
