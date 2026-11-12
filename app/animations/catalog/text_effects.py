import math
import random
from collections.abc import Iterator
from html import escape

from app.animations.registry import animation

NOISE = "!@#$%&*?<>/\\|=+01ABCDEFXYZ"


@animation("type", "Typewriter", "Text is typed letter by letter with a cursor", interval=0.45, usage=".type text")
def typewriter(args: str) -> Iterator[str]:
    text = args or "Hi! I'm typing…"
    step = max(1, math.ceil(len(text) / 20))
    for end in range(step, len(text) + step, step):
        yield text[:end] + ("▌" if end < len(text) else "")
    yield text


@animation("magic", "Decrypt", "Text emerges from random symbols", interval=0.5, html=True, usage=".magic text")
def magic(args: str) -> Iterator[str]:
    text = args or "Magic!"
    steps = 12
    for k in range(steps + 1):
        revealed = len(text) * k // steps
        chars = [c if (i < revealed or c == " ") else random.choice(NOISE) for i, c in enumerate(text)]
        yield f"<code>{escape(''.join(chars), quote=False)}</code>"
    yield f"✨ <b>{escape(text, quote=False)}</b> ✨"
