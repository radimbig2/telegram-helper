"""Entry point: wires services and routers together and starts long polling."""

import asyncio
import logging
import time
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

from app.animations import AnimationEngine, load_catalog
from app.bot.middlewares import CacheMiddleware, ConnectionGuard, OwnerConnectionMiddleware
from app.bot.routers import business, dot_commands, panel
from app.config import Settings, get_settings
from app.db import Database
from app.services.cache import CacheService
from app.services.media import MediaService
from app.services.notifier import Notifier
from app.services.settings_store import SettingsStore

log = logging.getLogger("app")

CACHE_CHECK_INTERVAL_SECONDS = 10 * 60

OWNER_COMMANDS = [
    BotCommand(command="menu", description="Control panel"),
    BotCommand(command="search", description="Search saved messages"),
    BotCommand(command="help", description="Dot commands and animations"),
]


async def cache_limit_loop(cache: CacheService, limit_bytes: int) -> None:
    """Periodically keeps the cache under CACHE_LIMIT_MB."""
    await asyncio.sleep(60)
    while True:
        try:
            await cache.enforce_size_limit(limit_bytes)
        except Exception:
            log.exception("Cache limit check failed")
        await asyncio.sleep(CACHE_CHECK_INTERVAL_SECONDS)


def build_dispatcher(services: dict[str, Any]) -> Dispatcher:
    """Creates the dispatcher. `services` become handler arguments by name (aiogram DI)."""
    dp = Dispatcher(storage=MemoryStorage())
    dp.workflow_data.update(services)

    guard: ConnectionGuard = services["guard"]
    for observer in (dp.business_message, dp.edited_business_message, dp.deleted_business_messages):
        observer.outer_middleware(OwnerConnectionMiddleware(guard))
    dp.business_message.outer_middleware(CacheMiddleware())

    # Order matters: dot commands must match before the catch-all handler in `business`.
    dp.include_routers(panel.router, dot_commands.router, business.router)
    return dp


async def build_services(settings: Settings, bot: Bot) -> dict[str, Any]:
    db = Database(settings.db_path)
    await db.create_schema()
    store = SettingsStore(db, settings.timezone)
    await store.load()

    media = MediaService(bot, settings.media_dir, settings.max_media_mb)
    cache = CacheService(db, media, store, settings.owner_id)
    return {
        "settings": settings,
        "owner_id": settings.owner_id,
        "db": db,
        "store": store,
        "media": media,
        "cache": cache,
        "notifier": Notifier(bot, cache, store, settings.owner_id),
        "engine": AnimationEngine(bot, settings.animation_max_frames),
        "guard": ConnectionGuard(bot, settings.owner_id, on_owner_connection=cache.save_connection),
        "started_at": time.time(),
    }


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    load_catalog()

    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    services = await build_services(settings, bot)
    dp = build_dispatcher(services)
    await bot.set_my_commands(OWNER_COMMANDS, scope=BotCommandScopeChat(chat_id=settings.owner_id))

    # BUSINESS_CONNECTION_ID from .env lets the panel show the connection right after start,
    # before the first business update arrives.
    guard: ConnectionGuard = services["guard"]
    if settings.business_connection_id and not await guard.is_owner_connection(settings.business_connection_id):
        log.warning("BUSINESS_CONNECTION_ID from .env does not belong to OWNER_ID or is not valid")

    cleanup = asyncio.create_task(cache_limit_loop(services["cache"], settings.cache_limit_bytes))
    me = await bot.get_me()
    log.info("Started as @%s, cache limit %d MB", me.username, settings.cache_limit_mb)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        cleanup.cancel()
        await services["db"].close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
