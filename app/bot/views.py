"""Panel screens: every function returns a (text, keyboard) pair."""

import time
from datetime import datetime

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.animations import all_animations
from app.bot.filters import UTILITY_COMMANDS
from app.bot.keyboards import HOME_BUTTON, Act, Action, Nav, Section, add_pager, back_home, home_keyboard
from app.db import Chat, Database, Message
from app.services.cache import CacheService, Page
from app.services.formatting import MEDIA_ICONS, chat_name, esc, fmt_dt, fmt_size, message_body, truncate
from app.services.media import MediaService
from app.services.settings_store import SETTINGS, SettingsStore
from app.services.timezones import utc_offset

PAGE_SIZE = 5
CHATS_PAGE_SIZE = 8

View = tuple[str, InlineKeyboardMarkup]


def commands_help() -> str:
    lines = ["🎬 <b>Animations</b>: type in any chat"]
    for anim in all_animations():
        aliases = "".join(f", .{a}" for a in anim.aliases)
        lines.append(f"<code>{esc(anim.usage)}</code>{aliases} - {esc(anim.description)}")
    lines.append("\n🛠 <b>Utilities</b>:")
    lines += [f"<code>.{cmd}</code> - {desc}" for cmd, desc in UTILITY_COMMANDS.items()]
    return "\n".join(lines)


def _empty(title: str, note: str) -> View:
    return f"{title}\n\n<i>{note}</i>", back_home()


def _author_line(n: int, msg: Message, chats: dict[int, Chat]) -> str:
    return f"<b>{n}.</b> 👤 {esc(msg.from_name)} · 💬 {esc(chat_name(chats.get(msg.chat_id), msg.chat_id))}"


async def home(cache: CacheService) -> View:
    stats = await cache.stats()
    conn = await cache.connection()
    conn_line = (
        "✅ connected"
        if conn and conn.is_enabled
        else "❌ not connected: Settings → Telegram Business → Chatbots"
    )
    text = (
        "🤖 <b>Telegram Helper</b>\n\n"
        f"🔌 {conn_line}\n\n"
        f"📦 Messages: <b>{stats.messages}</b> · 💬 Chats: <b>{stats.chats}</b>\n"
        f"🗑 Deleted: <b>{stats.deleted}</b> · ✏️ Edits: <b>{stats.edited}</b> · 🖼 Media: <b>{stats.media}</b>"
    )
    return text, home_keyboard()


async def deleted(cache: CacheService, page: int, chat_id: int = 0) -> View:
    data = await cache.deleted(page, PAGE_SIZE, chat_id or None)
    title = "🗑 <b>Deleted messages</b>"
    if chat_id:
        title += f" · {esc(chat_name(await cache.chat(chat_id), chat_id))}"
    if not data.items:
        return _empty(title, "Nobody has deleted anything yet.")

    chats = await cache.chats_by_ids({m.chat_id for m in data.items})
    kb = InlineKeyboardBuilder()
    blocks = []
    for n, msg in enumerate(data.items, start=data.first_number):
        blocks.append(
            f"{_author_line(n, msg, chats)}\n"
            f"🕒 {fmt_dt(msg.date)} → 🗑 {fmt_dt(msg.deleted_at)}\n{message_body(msg, 300)}"
        )
        if msg.media_type:
            kb.button(text=f"📎 {n}", callback_data=Act(action=Action.SHOW, id=msg.id))
    kb.adjust(5)
    add_pager(kb, Section.DELETED, page, data.pages, chat_id)
    return f"{title}\n\n" + "\n\n".join(blocks), kb.as_markup()


async def edits(cache: CacheService, page: int) -> View:
    data = await cache.edits(page, PAGE_SIZE)
    title = "✏️ <b>Edit history</b>"
    if not data.items:
        return _empty(title, "No edits yet.")

    chats = await cache.chats_by_ids({e.message.chat_id for e in data.items})
    blocks = [
        f"{_author_line(n, edit.message, chats)} · 🕒 {fmt_dt(edit.edited_at)}\n"
        f"Before: <blockquote>{esc(truncate(edit.old_text, 200)) or '-'}</blockquote>\n"
        f"After: <blockquote>{esc(truncate(edit.new_text, 200)) or '-'}</blockquote>"
        for n, edit in enumerate(data.items, start=data.first_number)
    ]
    kb = InlineKeyboardBuilder()
    add_pager(kb, Section.EDITS, page, data.pages)
    return f"{title}\n\n" + "\n\n".join(blocks), kb.as_markup()


async def _message_list(cache: CacheService, data: Page[Message], title: str, section: Section) -> View:
    chats = await cache.chats_by_ids({m.chat_id for m in data.items})
    kb = InlineKeyboardBuilder()
    blocks = []
    for n, msg in enumerate(data.items, start=data.first_number):
        flags = (" 🗑" if msg.is_deleted else "") + (" ✏️" if msg.is_edited else "")
        blocks.append(f"{_author_line(n, msg, chats)} · 🕒 {fmt_dt(msg.date)}{flags}\n{message_body(msg, 200)}")
        icon = MEDIA_ICONS.get(msg.media_type or "", "📤")
        kb.button(text=f"{icon} {n}", callback_data=Act(action=Action.SHOW, id=msg.id))
    kb.adjust(5)
    add_pager(kb, section, data.page, data.pages)
    return f"{title}\n\n" + "\n\n".join(blocks), kb.as_markup()


async def media(cache: CacheService, page: int) -> View:
    data = await cache.media(page, PAGE_SIZE)
    title = "🖼 <b>Media</b>"
    if not data.items:
        return _empty(title, "No media yet.")
    return await _message_list(cache, data, f"{title}: tap a number to get the file", Section.MEDIA)


def search_prompt() -> View:
    return "🔍 <b>Search</b>\n\nSend a word or phrase and I'll look through saved messages.", back_home()


async def search_results(cache: CacheService, query: str, page: int) -> View:
    data = await cache.search(query, page, PAGE_SIZE)
    title = f"🔍 <b>Search:</b> {esc(query)} · {data.total} found"
    if not data.items:
        return _empty(title, "Nothing found. Send another query.")
    return await _message_list(cache, data, title, Section.SEARCH_PAGE)


async def chats(cache: CacheService, page: int) -> View:
    data = await cache.chats(page, CHATS_PAGE_SIZE)
    title = "💬 <b>Chats</b>\n💾 save messages · 🔔 send notifications"
    if not data.items:
        return _empty(title, "No chats yet: message someone first.")

    kb = InlineKeyboardBuilder()
    for chat in data.items:
        flags = ("💾" if chat.save_enabled else "⛔") + ("🔔" if chat.notify_enabled else "🔕")
        kb.button(text=f"{flags} {truncate(chat_name(chat), 30)}", callback_data=Act(action=Action.CHAT, id=chat.id))
    kb.adjust(1)
    add_pager(kb, Section.CHATS, page, data.pages)
    return title, kb.as_markup()


async def chat_card(cache: CacheService, chat_id: int) -> View:
    chat = await cache.chat(chat_id)
    if chat is None:
        return _empty("💬 Chat not found", "It may have been removed when the cache was full.")

    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"💾 Save messages: {'on' if chat.save_enabled else 'off'}",
        callback_data=Act(action=Action.CHAT_SAVE, id=chat.id),
    )
    kb.button(
        text=f"🔔 Notifications: {'on' if chat.notify_enabled else 'off'}",
        callback_data=Act(action=Action.CHAT_NOTIFY, id=chat.id),
    )
    kb.button(text="🗑 Deleted in this chat", callback_data=Nav(section=Section.DELETED, chat_id=chat.id))
    kb.button(text="⬅️ Back to chats", callback_data=Nav(section=Section.CHATS))
    kb.adjust(1)
    text = f"💬 <b>{esc(chat_name(chat))}</b>\n🆔 <code>{chat.id}</code> · last message {fmt_dt(chat.last_message_at)}"
    return text, kb.as_markup()


def animations() -> View:
    kb = InlineKeyboardBuilder()
    for anim in all_animations():
        kb.button(text=f"▶️ {anim.title}", callback_data=Act(action=Action.ANIM, key=anim.command))
    kb.adjust(2)
    kb.row(HOME_BUTTON)
    return commands_help() + "\n\n<i>Tap a button to preview the animation here.</i>", kb.as_markup()


def settings(store: SettingsStore) -> View:
    kb = InlineKeyboardBuilder()
    for key, definition in SETTINGS.items():
        state = "✅" if store.get_bool(key) else "❌"
        kb.button(text=f"{state} {definition.title}", callback_data=Act(action=Action.SET, key=key))
    zone = store.timezone()
    kb.button(
        text=f"🕒 Time zone: {zone.label} ({utc_offset(datetime.now(zone.tz))})",
        callback_data=Act(action=Action.TIMEZONE),
    )
    kb.adjust(1)
    kb.row(HOME_BUTTON)
    text = (
        "⚙️ <b>Settings</b>\n\n"
        "Tap an item to toggle it.\n"
        "Per-chat saving and notifications live in 💬 Chats.\n"
        "The time zone is used by <code>.time</code> without a city and for times in this panel."
    )
    return text, kb.as_markup()


def timezone_prompt(store: SettingsStore) -> View:
    zone = store.timezone()
    text = (
        f"🕒 <b>Time zone</b>: {esc(zone.label)} ({utc_offset(datetime.now(zone.tz))})\n\n"
        "Send a city (<code>Warsaw</code>), a zone name (<code>Europe/Warsaw</code>) "
        "or an offset (<code>UTC+2</code>)."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Back to settings", callback_data=Nav(section=Section.SETTINGS))
    return text, kb.as_markup()


def _format_uptime(seconds: int) -> str:
    return f"{seconds // 86400}d {seconds % 86400 // 3600}h {seconds % 3600 // 60}m"


async def status(
    cache: CacheService, db: Database, media_service: MediaService, started_at: float, limit_bytes: int
) -> View:
    conn = await cache.connection()
    stats = await cache.stats()
    used = await cache.used_bytes()
    rights = conn.rights.replace(",", ", ") if conn and conn.rights else "-"
    text = (
        "📊 <b>Status</b>\n\n"
        f"🔌 Connection: {'✅ active' if conn and conn.is_enabled else '❌ none'}\n"
        f"🔑 Rights: <code>{esc(rights)}</code>\n"
        f"⏱ Uptime: {_format_uptime(int(time.time() - started_at))}\n\n"
        f"📦 Messages: {stats.messages} · 💬 Chats: {stats.chats}\n"
        f"🗄 Database: {fmt_size(db.size_bytes())} · 🖼 Media: {fmt_size(media_service.total_size())}\n"
        f"💾 Cache: {fmt_size(used)} of {fmt_size(limit_bytes)} ({used * 100 // max(limit_bytes, 1)}%)"
    )
    return text, back_home()
