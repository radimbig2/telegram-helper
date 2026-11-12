"""Business updates: connection, new messages, edits, deletions."""

from aiogram import Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from app.bot.middlewares import ConnectionGuard
from app.services.cache import CacheService
from app.services.notifier import Notifier

router = Router(name="business")


@router.business_connection()
async def on_connection(
    conn: BusinessConnection, guard: ConnectionGuard, cache: CacheService, notifier: Notifier
) -> None:
    if not guard.remember(conn):
        return  # someone else connected the bot to their account: ignore
    await cache.save_connection(conn)
    await notifier.connection(conn)


@router.business_message()
async def on_message(message: Message) -> None:
    """The message is already saved by CacheMiddleware; nothing else to do."""


@router.edited_business_message()
async def on_edit(message: Message, cache: CacheService, notifier: Notifier) -> None:
    result = await cache.record_edit(message)
    if result:
        await notifier.edited(*result)


@router.deleted_business_messages()
async def on_deleted(event: BusinessMessagesDeleted, cache: CacheService, notifier: Notifier) -> None:
    rows = await cache.mark_deleted(event.chat.id, event.message_ids)
    if rows:
        await notifier.deleted(rows)
