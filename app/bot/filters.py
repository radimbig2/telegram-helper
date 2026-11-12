"""Handler filters."""

import re
from typing import Any

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from app.animations import get_animation

UTILITY_COMMANDS: dict[str, str] = {
    "time": "[date] HH:MM [city] [note]: a time everyone sees in their own time zone",
    "stop": "stop the animation in this chat",
    "save": "as a reply: save the message and its media, send it to the bot chat",
    "info": "as a reply: details about the message and its author",
    "help": "send the command list to the bot chat",
}

_DOT_RE = re.compile(r"^\.([a-zA-Z0-9_]+)(?:\s+(.*))?$", re.DOTALL)


class IsOwner(Filter):
    """Passes only events coming from the bot owner."""

    async def __call__(self, event: Message | CallbackQuery, owner_id: int) -> bool:
        user = event.from_user
        return bool(user and user.id == owner_id)


class DotCommand(Filter):
    """Matches `.command args` and passes `command` and `args` to the handler.

    Unknown commands are ignored, so regular text starting with a dot stays untouched.
    """

    async def __call__(self, message: Message) -> bool | dict[str, Any]:
        match = _DOT_RE.match(message.text or "")
        if not match:
            return False
        command = match.group(1).lower()
        if command not in UTILITY_COMMANDS and get_animation(command) is None:
            return False
        return {"command": command, "args": (match.group(2) or "").strip()}
