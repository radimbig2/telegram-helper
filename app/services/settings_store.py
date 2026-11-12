"""Settings the owner changes from the panel. Stored in the settings table."""

from dataclasses import dataclass

from app.db import Database, Setting
from app.services.formatting import set_display_timezone
from app.services.timezones import Zone, zone_from_key


@dataclass(frozen=True, slots=True)
class SettingDef:
    key: str
    title: str
    default: str


SETTINGS: dict[str, SettingDef] = {
    "notify_deleted": SettingDef("notify_deleted", "🗑 Notify about deletions", "1"),
    "notify_edited": SettingDef("notify_edited", "✏️ Notify about edits", "1"),
    "save_media": SettingDef("save_media", "🖼 Download media", "1"),
}


class SettingsStore:
    def __init__(self, db: Database, default_timezone: str) -> None:
        self._db = db
        self._defaults = {k: v.default for k, v in SETTINGS.items()}
        self._defaults["timezone"] = default_timezone
        self._cache: dict[str, str] = {}

    async def load(self) -> None:
        async with self._db.session() as s:
            rows = (await s.execute(Setting.__table__.select())).all()
        self._cache = {row.key: row.value for row in rows}
        set_display_timezone(self.timezone().tz)

    def timezone(self) -> Zone:
        """The owner's time zone: default for `.time` and for times shown in the panel."""
        return zone_from_key(self.get("timezone"))

    async def set_timezone(self, zone: Zone) -> None:
        await self.set("timezone", zone.key)
        set_display_timezone(zone.tz)

    def get(self, key: str) -> str:
        return self._cache.get(key, self._defaults[key])

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    async def set(self, key: str, value: str) -> None:
        async with self._db.session() as s:
            await s.merge(Setting(key=key, value=value))
            await s.commit()
        self._cache[key] = value

    async def toggle(self, key: str) -> bool:
        new_value = not self.get_bool(key)
        await self.set(key, "1" if new_value else "0")
        return new_value
