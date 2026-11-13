"""`.time`: parsing, time zones (including DST) and the date-time entity."""

from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.types import Message

from app.bot.filters import DotCommand
from app.services.settings_store import SettingsStore
from app.services.timezones import (
    MAX_DATE_ENTITY_TEXT, TimeParseError, parse_time_request, render_time_message, resolve_zone,
)
from tests.conftest import OWNER, Feeder, FakeTelegram, business_message

WARSAW = resolve_zone("Europe/Warsaw")
NOW = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize("query", ["warsaw", "Warsaw", "warshaw", "Europe/Warsaw"])
def test_city_names_and_typos(query: str) -> None:
    zone = resolve_zone(query)
    assert zone is not None and zone.key == "Europe/Warsaw"


def test_offsets_and_unknown_zones() -> None:
    zone = resolve_zone("UTC+2")
    assert zone is not None and zone.key == "UTC+02:00"
    assert resolve_zone("Atlantisville") is None


def test_summer_time_is_respected() -> None:
    assert WARSAW is not None
    summer = parse_time_request("10:23", WARSAW, NOW).moment
    winter = parse_time_request("12.01.2026 10:23", WARSAW, NOW).moment
    assert (summer.astimezone(UTC).hour, winter.astimezone(UTC).hour) == (8, 9)


def test_date_zone_and_note() -> None:
    assert WARSAW is not None
    request = parse_time_request("12.02.2026 15:00 new york team call", WARSAW, NOW)
    assert request.zone.key == "America/New_York"
    assert request.note == "team call"
    assert request.moment.astimezone(UTC) == datetime(2026, 2, 12, 20, 0, tzinfo=UTC)


@pytest.mark.parametrize("args", ["oops", "25:00", "31.02.2026 10:00", ""])
def test_bad_input(args: str) -> None:
    assert WARSAW is not None
    with pytest.raises(TimeParseError):
        parse_time_request(args, WARSAW, NOW)


def test_entity_text_fits_telegram_limit() -> None:
    zone = resolve_zone("UTC+05:45")
    assert zone is not None
    html = render_time_message(parse_time_request("31.12.2026 23:59 <b>note</b>", zone, NOW))
    inner = html.split('">', 1)[1].split("</tg-time>", 1)[0]
    assert len(inner) <= MAX_DATE_ENTITY_TEXT
    assert "&lt;b&gt;note&lt;/b&gt;" in html


async def test_dot_time_replaces_the_owners_message(
    feed: Feeder, telegram: FakeTelegram, services: dict[str, Any]
) -> None:
    store: SettingsStore = services["store"]
    zone = resolve_zone("warsaw")
    assert zone is not None
    await store.set_timezone(zone)

    await feed(business_message=business_message(OWNER, 5, ".time 15:00"))
    edits = [params["text"] for name, params in telegram.calls if name == "EditMessageText"]
    assert len(edits) == 1 and "<tg-time unix=" in edits[0]
    assert "DeleteBusinessMessages" not in telegram.names


async def test_dot_time_error_goes_to_the_owner_only(feed: Feeder, telegram: FakeTelegram) -> None:
    await feed(business_message=business_message(OWNER, 5, ".time oops"))
    sent = telegram.sent()
    assert [params["chat_id"] for _, params in sent] == [OWNER.id]
    assert "EditMessageText" not in telegram.names


async def test_dot_command_filter() -> None:
    message: Message = business_message(OWNER, 1, ".time 15:00")
    assert await DotCommand()(message) == {"command": "time", "args": "15:00"}
    assert await DotCommand()(business_message(OWNER, 2, ".unknown thing")) is False
