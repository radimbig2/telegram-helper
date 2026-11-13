import random
from collections.abc import Iterator

from app.animations.registry import animation

DICE = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
BALL_ANSWERS = [
    "It is certain ✅",
    "Definitely yes 👍",
    "Most likely 🙂",
    "Signs point to yes ✨",
    "Reply hazy, ask again later 🤔",
    "Better not tell you now 🤐",
    "Don't count on it ❌",
    "My reply is no 👎",
    "Very doubtful 😬",
]


@animation("8ball", "Magic 8-ball", "Answers a yes/no question", interval=0.5, usage=".8ball question", aliases=("ball",))
def magic_ball(args: str) -> Iterator[str]:
    question = f"❓ {args}\n" if args else ""
    for dots in ("", ".", "..", "...", "", ".", ".."):
        yield f"{question}🎱 Shaking the ball{dots}"
    yield f"{question}🎱 {random.choice(BALL_ANSWERS)}"


@animation("dice", "Dice", "The dice rolls and lands on a number", interval=0.35, aliases=("roll",))
def dice(args: str) -> Iterator[str]:
    previous = None
    for _ in range(8):
        previous = random.choice([d for d in DICE if d != previous])
        yield f"🎲 {previous}"
    result = random.randint(1, 6)
    yield f"🎲 {DICE[result - 1]} You rolled: {result}"
