"""The bot serves only its owner: it leaves any group or channel someone adds it to."""

import logging

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated

log = logging.getLogger(__name__)

router = Router(name="membership")


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_added(event: ChatMemberUpdated, bot: Bot) -> None:
    if event.chat.type == ChatType.PRIVATE:
        return
    added_by = event.from_user.id if event.from_user else None
    log.info("Added to %s %s by %s, leaving", event.chat.type, event.chat.id, added_by)
    try:
        await bot.leave_chat(event.chat.id)
    except Exception as exc:  # noqa: BLE001 - already removed or no access: nothing else to do
        log.info("Cannot leave chat %s: %s", event.chat.id, exc)
