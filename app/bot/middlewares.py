"""Middlewares for business updates."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import BusinessConnection, Message, TelegramObject

from app.services.cache import CacheService

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ConnectionGuard:
    """Remembers which business connections belong to the owner.

    Anyone can connect the bot to their own Business account; such updates are ignored.
    """

    def __init__(
        self,
        bot: Bot,
        owner_id: int,
        on_owner_connection: Callable[[BusinessConnection], Awaitable[None]] | None = None,
    ) -> None:
        self._bot = bot
        self._owner_id = owner_id
        self._on_owner_connection = on_owner_connection  # e.g. save it so the panel shows the status
        self._allowed: set[str] = set()
        self._denied: set[str] = set()

    def remember(self, conn: BusinessConnection) -> bool:
        is_owner = conn.user.id == self._owner_id
        (self._allowed if is_owner else self._denied).add(conn.id)
        (self._denied if is_owner else self._allowed).discard(conn.id)
        return is_owner

    async def is_owner_connection(self, connection_id: str | None) -> bool:
        if not connection_id or connection_id in self._denied:
            return False
        if connection_id in self._allowed:
            return True
        try:
            conn = await self._bot.get_business_connection(connection_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cannot verify business connection %s: %s", connection_id, exc)
            return False
        is_owner = self.remember(conn)
        if is_owner and self._on_owner_connection:
            await self._on_owner_connection(conn)
        return is_owner


class OwnerConnectionMiddleware(BaseMiddleware):
    """Lets through only updates that come from the owner's connection."""

    def __init__(self, guard: ConnectionGuard) -> None:
        self._guard = guard

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if await self._guard.is_owner_connection(getattr(event, "business_connection_id", None)):
            return await handler(event, data)
        return None


class CacheMiddleware(BaseMiddleware):
    """Saves every new business message to the cache before handlers process it."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        cache: CacheService = data["cache"]
        if isinstance(event, Message):
            try:
                await cache.save_message(event)
            except Exception:
                log.exception("Failed to cache message")
        return await handler(event, data)
