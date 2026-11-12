"""Downloading and storing media files."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aiogram import Bot
from aiogram.types import Message as TgMessage

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MediaInfo:
    type: str
    file_id: str
    file_unique_id: str
    file_size: int | None
    ext: str
    downloadable: bool = True


def _ext_from_name(name: str | None, default: str) -> str:
    if name and "." in name:
        return name.rsplit(".", 1)[1][:10].lower()
    return default


@dataclass(frozen=True, slots=True)
class StoredFile:
    path: Path
    size: int
    modified: float


class _TelegramFile(Protocol):
    """Common shape of Telegram media objects (PhotoSize, Video, Voice, Document, ...)."""

    file_id: str
    file_unique_id: str
    file_size: int | None


def _info(kind: str, file: _TelegramFile, ext: str, downloadable: bool = True) -> MediaInfo:
    return MediaInfo(kind, file.file_id, file.file_unique_id, file.file_size, ext, downloadable)


def extract_media(message: TgMessage) -> MediaInfo | None:
    """Extracts the single media object from a message (if any)."""
    if message.photo:
        return _info("photo", message.photo[-1], "jpg")  # last = largest resolution
    if message.video:
        return _info("video", message.video, _ext_from_name(message.video.file_name, "mp4"))
    if message.video_note:
        return _info("video_note", message.video_note, "mp4")
    if message.voice:
        return _info("voice", message.voice, "ogg")
    if message.audio:
        return _info("audio", message.audio, _ext_from_name(message.audio.file_name, "mp3"))
    if message.animation:
        return _info("animation", message.animation, "mp4")
    if message.document:
        return _info("document", message.document, _ext_from_name(message.document.file_name, "bin"))
    if message.sticker:
        return _info("sticker", message.sticker, "webp", downloadable=False)
    return None


class MediaService:
    def __init__(self, bot: Bot, media_dir: Path, max_media_mb: int) -> None:
        self._bot = bot
        self._dir = media_dir
        self._max_bytes = max_media_mb * 1024 * 1024
        self._dir.mkdir(parents=True, exist_ok=True)

    async def download(self, info: MediaInfo, chat_id: int, message_id: int) -> str | None:
        """Downloads the file to disk. Returns the path, or None if it cannot be downloaded."""
        if not info.downloadable:
            return None
        if info.file_size and info.file_size > self._max_bytes:
            log.info("Skip media %s: %s bytes > limit", info.file_unique_id, info.file_size)
            return None
        target = self._dir / str(chat_id) / f"{message_id}_{info.file_unique_id}.{info.ext}"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._bot.download(info.file_id, destination=target)
        except Exception as exc:  # noqa: BLE001 - Telegram may refuse the file (size limit, view-once media)
            log.warning("Media download failed for %s: %s", info.file_unique_id, exc)
            target.unlink(missing_ok=True)
            return None
        return str(target)

    @staticmethod
    def delete_file(path: str | None) -> None:
        if path:
            Path(path).unlink(missing_ok=True)

    def files_oldest_first(self) -> list[StoredFile]:
        files = [StoredFile(f, st.st_size, st.st_mtime) for f in self._dir.rglob("*") if f.is_file() for st in [f.stat()]]
        return sorted(files, key=lambda f: f.modified)

    def total_size(self) -> int:
        return sum(f.size for f in self.files_oldest_first())
