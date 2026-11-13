"""Business connection guard and the connection status in the panel."""

from typing import Any

from aiogram import Bot
from aiogram.types import BusinessConnection, User

from app.bot import views
from app.bot.middlewares import ConnectionGuard
from app.services.cache import CacheService
from tests.conftest import NOW, OWNER, FakeTelegram


def _connection(connection_id: str, enabled: bool, user: User = OWNER) -> BusinessConnection:
    return BusinessConnection(id=connection_id, user=user, user_chat_id=user.id, date=NOW, is_enabled=enabled)


async def test_guard_verifies_and_saves_only_the_owners_connection(
    services: dict[str, Any], bot: Bot, telegram: FakeTelegram
) -> None:
    cache: CacheService = services["cache"]
    guard = ConnectionGuard(bot, OWNER.id, on_owner_connection=cache.save_connection)
    assert "not connected" in (await views.home(cache))[0]

    assert await guard.is_owner_connection("stranger") is False
    assert await cache.connection() is None

    assert await guard.is_owner_connection("mine") is True
    assert await guard.is_owner_connection("mine") is True
    assert telegram.names.count("GetBusinessConnection") == 2, "results are cached in memory"
    assert "✅ connected" in (await views.home(cache))[0]


async def test_active_connection_wins_over_stale_one(services: dict[str, Any]) -> None:
    cache: CacheService = services["cache"]
    await cache.save_connection(_connection("mine", enabled=True))
    await cache.save_connection(_connection("old", enabled=False))  # newer, but disabled
    current = await cache.connection()
    assert current is not None and current.id == "mine"

    await cache.save_connection(_connection("mine", enabled=False))
    assert "not connected" in (await views.home(cache))[0]
