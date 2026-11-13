"""Shared fixtures: settings in a temp dir and a fake Telegram that records every Bot API call."""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetBusinessConnection, GetFile, TelegramMethod
from aiogram.types import BusinessConnection, Chat, File, Message, Update, User

from app.animations import load_catalog
from app.config import Settings
from app.main import build_dispatcher, build_services

OWNER = User(id=1, is_bot=False, first_name="Owner")
FRIEND = User(id=42, is_bot=False, first_name="Friend")
STRANGER = User(id=666, is_bot=False, first_name="Stranger")
BOT_USER = User(id=123456, is_bot=True, first_name="Bot")
FRIEND_CHAT = Chat(id=FRIEND.id, type="private", first_name=FRIEND.first_name)
OWNER_CONNECTION = "mine"
NOW = datetime.now(UTC)


class FakeTelegram(BaseSession):
    """Records Bot API calls instead of sending them.

    The connection "mine" belongs to the owner, any other one to a stranger.
    Downloaded files contain their own URL, so tests can tell them apart.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        self.calls.append((type(method).__name__, dict(method)))
        if isinstance(method, GetBusinessConnection):
            user = OWNER if method.business_connection_id == OWNER_CONNECTION else STRANGER
            return BusinessConnection(
                id=method.business_connection_id, user=user, user_chat_id=user.id, date=NOW, is_enabled=True
            )
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="u", file_path=f"files/{method.file_id}")
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield f"content of {url}".encode()

    async def close(self) -> None:
        pass

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def sent(self) -> list[tuple[str, dict[str, Any]]]:
        """Calls that send something to a chat."""
        return [(name, params) for name, params in self.calls if name.startswith("Send")]


@pytest.fixture(scope="session", autouse=True)
def catalog() -> None:
    load_catalog()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]  # _env_file: never read the real .env in tests
        _env_file=None, bot_token=SecretStr("123456:TEST"), owner_id=OWNER.id, data_dir=tmp_path, timezone="UTC"
    )


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def bot(telegram: FakeTelegram) -> Bot:
    return Bot("123456:TEST", session=telegram)


@pytest.fixture
async def services(settings: Settings, bot: Bot) -> AsyncIterator[dict[str, Any]]:
    services = await build_services(settings, bot)
    yield services
    services["engine"].stop(FRIEND_CHAT.id)
    await services["db"].close()


class Feeder:
    """Feeds updates through the real dispatcher and returns the API calls they caused."""

    def __init__(self, dp: Dispatcher, bot: Bot, telegram: FakeTelegram) -> None:
        self._dp, self._bot, self._telegram = dp, bot, telegram
        self._next_id = 1

    async def __call__(self, **update: Any) -> list[str]:
        self._telegram.calls.clear()
        await self._dp.feed_update(self._bot, Update(update_id=self._next_id, **update))
        self._next_id += 1
        return self._telegram.names


@pytest.fixture
def feed(services: dict[str, Any], bot: Bot, telegram: FakeTelegram) -> Iterator[Feeder]:
    dp = build_dispatcher(services)
    yield Feeder(dp, bot, telegram)
    # Routers are module-level singletons and can be attached to one dispatcher at a time.
    for router in dp.sub_routers:
        router._parent_router = None


def private_message(user: User, text: str, message_id: int = 1, chat: Chat | None = None) -> Message:
    chat = chat or Chat(id=user.id, type="private", first_name=user.first_name)
    return Message(message_id=message_id, date=NOW, chat=chat, from_user=user, text=text)


def business_message(
    user: User, message_id: int, text: str | None = None, connection: str = OWNER_CONNECTION, **fields: Any
) -> Message:
    return Message(
        message_id=message_id, date=NOW, chat=FRIEND_CHAT, from_user=user, text=text,
        business_connection_id=connection, **fields,
    )
