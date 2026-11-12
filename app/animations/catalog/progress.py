import random
from collections.abc import Iterator
from html import escape

from app.animations.registry import animation


def _bar(percent: int, width: int = 10) -> str:
    filled = percent * width // 100
    return "▰" * filled + "▱" * (width - filled)


@animation("loading", "Loading", "A progress bar from 0 to 100%", interval=0.5, usage=".loading [what]")
def loading(args: str) -> Iterator[str]:
    label = args or "Loading"
    for percent in range(0, 101, 10):
        yield f"⏳ {label}…\n{_bar(percent)} {percent}%"
    yield f"✅ {label}: done!"


@animation("hack", "Hack", "A fake hack with scrolling code and progress", interval=0.6, html=True, usage=".hack [target]")
def hack(args: str) -> Iterator[str]:
    target = escape(args or "the Pentagon", quote=False)
    steps = [
        "Connecting to server",
        "Bypassing firewall",
        "Brute-forcing password",
        "Decrypting data",
        "Uploading to the cloud",
        "Covering tracks",
    ]
    log: list[str] = []
    for i, step in enumerate(steps):
        percent = (i + 1) * 100 // len(steps)
        log.append(f"> {step}... 0x{random.getrandbits(32):08X}")
        lines = "\n".join(log[-4:])
        yield f"💻 Hacking <b>{target}</b>\n<pre>{lines}\n[{_bar(percent)}] {percent}%</pre>"
    yield f"🟢 <b>ACCESS GRANTED</b>\n{target} is hacked 😎"
