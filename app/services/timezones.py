"""Time zone lookup and parsing of the `.time` command.

The `.time` message uses Telegram's `date_time` entity: it stores an exact moment and every
reader's app shows it in their own time zone.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from difflib import get_close_matches
from functools import lru_cache
from html import escape
from zoneinfo import ZoneInfo, available_timezones

# Names people actually type that are not the last part of an IANA zone name.
ALIASES: dict[str, str] = {
    "kiev": "Europe/Kyiv",
    "kyiv": "Europe/Kyiv",
    "lviv": "Europe/Kyiv",
    "odessa": "Europe/Kyiv",
    "kharkiv": "Europe/Kyiv",
    "krakow": "Europe/Warsaw",
    "wroclaw": "Europe/Warsaw",
    "gdansk": "Europe/Warsaw",
    "munich": "Europe/Berlin",
    "frankfurt": "Europe/Berlin",
    "milan": "Europe/Rome",
    "barcelona": "Europe/Madrid",
    "petersburg": "Europe/Moscow",
    "st petersburg": "Europe/Moscow",
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "washington": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "sf": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "dallas": "America/Chicago",
    "houston": "America/Chicago",
    "beijing": "Asia/Shanghai",
    "delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "abu dhabi": "Asia/Dubai",
    "bali": "Asia/Makassar",
    "est": "America/New_York",
    "cst": "America/Chicago",
    "pst": "America/Los_Angeles",
    "cet": "Europe/Paris",
    "eet": "Europe/Kyiv",
    "msk": "Europe/Moscow",
}

_OFFSET_RE = re.compile(r"^(?:utc|gmt)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)
_DATE_RE = re.compile(r"^(\d{1,2})[./](\d{1,2})(?:[./](\d{4}|\d{2}))?$")
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")

FUZZY_CUTOFF = 0.8
MAX_ZONE_WORDS = 3
DATE_TIME_FORMAT = "wdt"  # weekday, short date, short time (see Bot API "date-time entity formatting")
MAX_DATE_ENTITY_TEXT = 31  # measured: 32+ characters inside <tg-time> fail with ENTITY_DATE_TOO_LONG


class TimeParseError(ValueError):
    """The `.time` arguments could not be understood; the message is shown to the owner."""


@dataclass(frozen=True, slots=True)
class Zone:
    tz: tzinfo
    key: str  # what is stored in settings: an IANA name or "UTC+02:00"
    label: str  # human-readable name: "Warsaw", "UTC+02:00"


@dataclass(frozen=True, slots=True)
class TimeRequest:
    moment: datetime  # timezone-aware
    zone: Zone
    note: str


# ---------- zones ----------


def _city_of(name: str) -> str:
    return name.rsplit("/", 1)[-1].replace("_", " ")


@lru_cache
def _iana_names() -> dict[str, str]:
    return {name.lower(): name for name in available_timezones()}


@lru_cache
def _city_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for name in sorted(available_timezones()):
        if "/" not in name or name.startswith(("Etc/", "SystemV/", "posix/", "right/")):
            continue
        city = _city_of(name).lower()
        index.setdefault(city, name)
        index.setdefault(city.replace(" ", ""), name)
    index.update(ALIASES)
    return index


def _iana_zone(name: str) -> Zone:
    return Zone(ZoneInfo(name), name, _city_of(name))


def _offset_zone(sign: str, hours: str, minutes: str | None) -> Zone | None:
    delta = timedelta(hours=int(hours), minutes=int(minutes or 0))
    if delta > timedelta(hours=14):
        return None
    label = f"UTC{sign}{int(hours):02d}:{int(minutes or 0):02d}"
    return Zone(timezone(delta if sign == "+" else -delta, label), label, label)


def resolve_zone(query: str) -> Zone | None:
    """Turns "Warsaw", "warshaw", "Europe/Warsaw", "UTC+2" or "+05:30" into a Zone."""
    text = " ".join(query.strip().lower().replace("_", " ").split())
    if not text:
        return None
    if text in ("utc", "gmt", "z"):
        return Zone(UTC, "UTC", "UTC")
    if match := _OFFSET_RE.match(text):
        return _offset_zone(*match.groups())
    if name := _iana_names().get(text.replace(" ", "_")):
        return _iana_zone(name)

    index = _city_index()
    name = index.get(text) or index.get(text.replace(" ", ""))
    if name is None and len(text) >= 4:
        close = get_close_matches(text, index.keys(), n=1, cutoff=FUZZY_CUTOFF)
        name = index[close[0]] if close else None
    return _iana_zone(name) if name else None


def zone_from_key(key: str) -> Zone:
    """Restores a Zone saved in settings (falls back to UTC if the key is unknown)."""
    return resolve_zone(key) or Zone(UTC, "UTC", "UTC")


def utc_offset(moment: datetime) -> str:
    raw: str = moment.strftime("%z") or "+0000"  # "+0100"
    return f"UTC{raw[:3]}:{raw[3:]}"


# ---------- .time parsing ----------


def _parse_date(token: str, today: datetime) -> tuple[int, int, int] | None:
    if iso := _ISO_DATE_RE.match(token):
        year, month, day = (int(g) for g in iso.groups())
        return year, month, day
    if short := _DATE_RE.match(token):
        day_text, month_text, year_text = short.groups()
        year = today.year if year_text is None else int(year_text)
        if year < 100:
            year += 2000
        return year, int(month_text), int(day_text)
    return None


def _parse_time(token: str) -> tuple[int, int] | None:
    match = _TIME_RE.match(token)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _split_zone(words: list[str], default: Zone) -> tuple[Zone, list[str]]:
    """The zone comes right after the time and may be several words ("new york")."""
    for size in range(min(MAX_ZONE_WORDS, len(words)), 0, -1):
        zone = resolve_zone(" ".join(words[:size]))
        if zone:
            return zone, words[size:]
    return default, words


def parse_time_request(args: str, default_zone: Zone, now: datetime | None = None) -> TimeRequest:
    """Parses `[date] HH:MM [zone] [note]`, e.g. "12.02.2026 15:00 Warsaw team call"."""
    words = args.split()
    date: tuple[int, int, int] | None = None
    clock: tuple[int, int] | None = None
    consumed = 0
    now = now or datetime.now(UTC)

    for word in words[:2]:
        if clock is None and (parsed_time := _parse_time(word)):
            clock = parsed_time
        elif date is None and (parsed_date := _parse_date(word, now)):
            date = parsed_date
        else:
            break
        consumed += 1

    if clock is None:
        raise TimeParseError("No time found. Example: <code>.time 15:00 Warsaw</code>")

    zone, note_words = _split_zone(words[consumed:], default_zone)
    if date is None:
        local_today = now.astimezone(zone.tz)
        date = (local_today.year, local_today.month, local_today.day)

    try:
        moment = datetime(*date, *clock, tzinfo=zone.tz)
    except ValueError as exc:
        raise TimeParseError(f"Invalid date or time: {escape(str(exc))}") from exc
    return TimeRequest(moment, zone, " ".join(note_words))


def render_time_message(request: TimeRequest) -> str:
    """HTML with a `date_time` entity; the inner text is shown by apps that don't support it."""
    moment = request.moment
    # Telegram rejects longer inner text with ENTITY_DATE_TOO_LONG, so no zone name here.
    fallback = f"{moment:%d.%m.%Y %H:%M} {utc_offset(moment)}"[:MAX_DATE_ENTITY_TEXT]
    tag = f'<tg-time unix="{int(moment.timestamp())}" format="{DATE_TIME_FORMAT}">{escape(fallback)}</tg-time>'
    note = f"{escape(request.note)}\n" if request.note else ""
    return f"{note}🕒 {tag}"
