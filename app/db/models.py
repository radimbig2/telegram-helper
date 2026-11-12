"""Database tables."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Connection(Base):
    """Business connection of the bot to the owner's account."""

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    user_chat_id: Mapped[int] = mapped_column(BigInteger)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rights: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Chat(Base):
    """A chat partner / chat. Holds per-chat saving and notification settings."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    save_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Message(Base):
    """A cached message."""

    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("chat_id", "message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger)
    connection_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    from_name: Mapped[str] = mapped_column(String(256), default="")
    is_outgoing: Mapped[bool] = mapped_column(Boolean, default=False)
    text: Mapped[str] = mapped_column(Text, default="")

    media_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_unique_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    media_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    edits: Mapped[list["Edit"]] = relationship(back_populates="message", cascade="all, delete-orphan")


class Edit(Base):
    """A single message edit: before -> after."""

    __tablename__ = "edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_pk: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    old_text: Mapped[str] = mapped_column(Text, default="")
    new_text: Mapped[str] = mapped_column(Text, default="")
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    message: Mapped[Message] = relationship(back_populates="edits")


class Setting(Base):
    """Settings changed from the panel (key -> value)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
