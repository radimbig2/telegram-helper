"""SQLite connection and schema creation (including FTS5 full-text search)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

# Full-text index over message text. Triggers keep it in sync with the messages table.
_FTS_DDL = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        text, content='messages', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.id, old.text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF text ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.id, old.text);
        INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
    END
    """,
]


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
        event.listen(self.engine.sync_engine, "connect", self._on_connect)
        self._sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for ddl in _FTS_DDL:
                await conn.execute(text(ddl))

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session

    def size_bytes(self) -> int:
        """Size of the database file including WAL/SHM files."""
        return sum(p.stat().st_size for p in self.path.parent.glob(f"{self.path.name}*") if p.is_file())

    async def used_bytes(self) -> int:
        """Space actually used by data. Unlike the file size, it drops right after rows are deleted."""
        async with self.engine.connect() as conn:
            page_size = (await conn.exec_driver_sql("PRAGMA page_size")).scalar_one()
            page_count = (await conn.exec_driver_sql("PRAGMA page_count")).scalar_one()
            free_pages = (await conn.exec_driver_sql("PRAGMA freelist_count")).scalar_one()
        return int((page_count - free_pages) * page_size)

    async def close(self) -> None:
        await self.engine.dispose()
