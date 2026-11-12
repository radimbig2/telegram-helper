"""Dot commands the owner types right in chats: .train, .love, .time, .save, ..."""

import logging
from collections.abc import Awaitable, Callable

from aiogram import Bot, Router
from aiogram.types import Message

from app.animations import AnimationEngine, Target, get_animation
from app.bot.filters import DotCommand, IsOwner
from app.bot.views import commands_help
from app.services.cache import CacheService
from app.services.formatting import esc, fmt_dt
from app.services.notifier import Notifier
from app.services.settings_store import SettingsStore
from app.services.timezones import TimeParseError, parse_time_request, render_time_message

log = logging.getLogger(__name__)

router = Router(name="dot_commands")
router.business_message.filter(IsOwner())

# A utility handler gets the message and the command arguments.
# It returns True if the command message should be deleted from the chat afterwards.
UtilityHandler = Callable[[Message, str], Awaitable[bool]]


def _target(message: Message) -> Target:
    return Target(message.chat.id, message.message_id, message.business_connection_id)


class UtilityCommands:
    """Non-animation dot commands. Each `cmd_<name>` method handles `.name`."""

    def __init__(
        self, engine: AnimationEngine, cache: CacheService, notifier: Notifier, store: SettingsStore
    ) -> None:
        self._engine = engine
        self._cache = cache
        self._notifier = notifier
        self._store = store

    def get(self, name: str) -> UtilityHandler | None:
        handler: UtilityHandler | None = getattr(self, f"cmd_{name}", None)
        return handler

    async def cmd_time(self, message: Message, args: str) -> bool:
        """Replaces the command with a time every reader sees in their own time zone."""
        try:
            request = parse_time_request(args, self._store.timezone())
        except TimeParseError as exc:
            await self._notifier.text(f"🕒 <b>.time</b>: {exc}")
            return False  # keep the message so it can be fixed
        if not await self._engine.replace(_target(message), render_time_message(request)):
            await self._notifier.text("🕒 <b>.time</b>: could not update the message in the chat.")
        return False

    async def cmd_stop(self, message: Message, args: str) -> bool:
        self._engine.stop(message.chat.id)
        return True

    async def cmd_help(self, message: Message, args: str) -> bool:
        await self._notifier.text(commands_help())
        return True

    async def cmd_save(self, message: Message, args: str) -> bool:
        reply = message.reply_to_message
        if reply is None:
            await self._notifier.text("💾 <b>.save</b> works only as a reply to a message.")
            return True
        row = await self._cache.save_media_now(reply)
        if row is None:
            await self._notifier.text("💾 Saving is disabled for this chat in the panel.")
            return True
        header = f"💾 <b>Saved</b> · 👤 {esc(row.from_name)} · 🕒 {fmt_dt(row.date)}"
        if reply.has_protected_content:
            header += "\n<i>⚠️ The message is protected from forwarding; Telegram may not provide the file.</i>"
        await self._notifier.send_message_copy(row, header)
        return True

    async def cmd_info(self, message: Message, args: str) -> bool:
        reply = message.reply_to_message
        if reply is None:
            await self._notifier.text("ℹ️ <b>.info</b> works only as a reply to a message.")
            return True
        user = reply.from_user
        name = esc(user.full_name) if user else "-"
        username = f" (@{user.username})" if user and user.username else ""
        await self._notifier.text(
            "ℹ️ <b>Message info</b>\n"
            f"👤 {name}{username}\n"
            f"🆔 user: <code>{user.id if user else '-'}</code>\n"
            f"💬 chat: <code>{reply.chat.id}</code> · msg: <code>{reply.message_id}</code>\n"
            f"🕒 {fmt_dt(reply.date)}{' · ✏️ edited' if reply.edit_date else ''}"
        )
        return True


async def _delete_command(bot: Bot, message: Message) -> None:
    """Removes a utility command from the chat so the other person does not see it."""
    if not message.business_connection_id:
        return
    try:
        await bot.delete_business_messages(message.business_connection_id, [message.message_id])
    except Exception as exc:  # noqa: BLE001 - no delete right: the command just stays
        log.info("Cannot delete command message: %s", exc)


@router.business_message(DotCommand())
async def on_dot_command(
    message: Message,
    command: str,
    args: str,
    bot: Bot,
    engine: AnimationEngine,
    cache: CacheService,
    notifier: Notifier,
    store: SettingsStore,
) -> None:
    anim = get_animation(command)
    if anim:
        engine.start(anim, args, _target(message))
        return

    handler = UtilityCommands(engine, cache, notifier, store).get(command)
    if handler and await handler(message, args):
        await _delete_command(bot, message)
