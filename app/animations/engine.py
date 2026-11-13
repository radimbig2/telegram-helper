"""Animation engine: plays frames by editing a single message."""

import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from html import escape
from itertools import islice

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.animations.registry import Animation, Frame

log = logging.getLogger(__name__)


@dataclass
class Target:
    """Which message to animate."""

    chat_id: int
    message_id: int
    business_connection_id: str | None = None


class AnimationEngine:
    def __init__(self, bot: Bot, max_frames: int) -> None:
        self._bot = bot
        self._max_frames = max_frames
        self._tasks: dict[int, asyncio.Task[None]] = {}

    def start(self, anim: Animation, args: str, target: Target) -> None:
        """Starts an animation in the background. Any previous animation in this chat is stopped."""
        self.stop(target.chat_id)
        task = asyncio.create_task(self._run(anim, args, target), name=f"anim:{anim.command}:{target.chat_id}")
        self._tasks[target.chat_id] = task
        task.add_done_callback(partial(self._forget, target.chat_id))

    def stop(self, chat_id: int) -> bool:
        task = self._tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def _forget(self, chat_id: int, task: asyncio.Task[None]) -> None:
        if self._tasks.get(chat_id) is task:
            del self._tasks[chat_id]
        if not task.cancelled() and task.exception():
            log.error("Animation failed", exc_info=task.exception())

    async def _run(self, anim: Animation, args: str, target: Target) -> None:
        # Frames are pulled lazily, each one only after the previous pause: a generator may look at
        # the clock (a countdown stays exact even if Telegram's flood control delayed an edit).
        last: str | None = None
        for item in islice(anim.frames(args), anim.max_frames or self._max_frames):
            text, hold = (item.text, item.hold) if isinstance(item, Frame) else (item, anim.interval)
            frame = text if anim.html else escape(text, quote=False)
            if not frame.strip() or frame == last:
                continue
            shown = await self._edit(target, frame) if last is not None else await self.replace(target, frame)
            if not shown:
                return
            last = frame
            await asyncio.sleep(hold)

    async def replace(self, target: Target, html: str) -> bool:
        """Replaces the message text once (edit, or delete-and-resend as a fallback)."""
        return await self._edit(target, html) or await self._fallback(target, html)

    async def _edit(self, target: Target, text: str) -> bool:
        for _ in range(3):
            try:
                await self._bot.edit_message_text(
                    text=text,
                    chat_id=target.chat_id,
                    message_id=target.message_id,
                    business_connection_id=target.business_connection_id,
                )
                return True
            except TelegramRetryAfter as exc:
                log.info("Flood control, sleeping %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc):
                    return True
                log.warning("Cannot edit message %s: %s", target.message_id, exc)
                return False
        return False

    async def _fallback(self, target: Target, first_frame: str) -> bool:
        """If the owner's message cannot be edited, delete it and animate a new one sent on the owner's behalf."""
        if not target.business_connection_id:
            return False
        # Send first, delete after: if sending fails, the owner's original message must survive.
        try:
            sent = await self._bot.send_message(
                target.chat_id, first_frame, business_connection_id=target.business_connection_id
            )
        except TelegramBadRequest as exc:
            log.warning("Fallback: cannot send message: %s", exc)
            return False
        try:
            await self._bot.delete_business_messages(target.business_connection_id, [target.message_id])
        except TelegramBadRequest as exc:
            log.info("Fallback: cannot delete original command: %s", exc)
        target.message_id = sent.message_id
        return True
