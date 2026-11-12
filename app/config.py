"""Application settings, read from environment variables / the .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    owner_id: int
    business_connection_id: str | None = None

    data_dir: Path = Path("data")
    max_media_mb: int = 20
    cache_limit_mb: int = 10240  # disk space for the cache (media + database)
    animation_max_frames: int = 40
    log_level: str = "INFO"
    timezone: str = "Europe/Kyiv"

    @field_validator("business_connection_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def cache_limit_bytes(self) -> int:
        return self.cache_limit_mb * 1024 * 1024

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
