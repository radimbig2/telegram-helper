"""Callback data and keyboard builders for the panel."""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class Section(StrEnum):
    HOME = "home"
    DELETED = "deleted"
    EDITS = "edits"
    MEDIA = "media"
    SEARCH = "search"
    SEARCH_PAGE = "search_page"
    CHATS = "chats"
    ANIMS = "anims"
    SETTINGS = "settings"
    STATUS = "status"


class Action(StrEnum):
    NOOP = "noop"
    SHOW = "show"  # resend a cached message
    CHAT = "chat"  # open a chat card
    CHAT_SAVE = "chat_save"
    CHAT_NOTIFY = "chat_notify"
    ANIM = "anim"  # preview an animation
    SET = "set"  # toggle a setting
    TIMEZONE = "timezone"  # ask for a new time zone


class Nav(CallbackData, prefix="nav"):
    """Open a panel section (optionally a page and a chat filter)."""

    section: Section
    page: int = 0
    chat_id: int = 0


class Act(CallbackData, prefix="act"):
    """Perform an action on an item identified by `id` or `key`."""

    action: Action
    id: int = 0
    key: str = ""


HOME_BUTTON = InlineKeyboardButton(text="🏠 Menu", callback_data=Nav(section=Section.HOME).pack())

_HOME_ITEMS: list[tuple[str, Section]] = [
    ("🗑 Deleted", Section.DELETED),
    ("✏️ Edits", Section.EDITS),
    ("🖼 Media", Section.MEDIA),
    ("🔍 Search", Section.SEARCH),
    ("💬 Chats", Section.CHATS),
    ("🎬 Animations", Section.ANIMS),
    ("⚙️ Settings", Section.SETTINGS),
    ("📊 Status", Section.STATUS),
]


def home_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for text, section in _HOME_ITEMS:
        kb.button(text=text, callback_data=Nav(section=section))
    kb.adjust(2)
    return kb.as_markup()


def add_pager(kb: InlineKeyboardBuilder, section: Section, page: int, pages: int, chat_id: int = 0) -> None:
    """Appends a `◀️ 1/5 ▶️` row and a menu row."""

    def nav(to_page: int) -> str:
        return Nav(section=section, page=to_page, chat_id=chat_id).pack()

    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️", callback_data=nav(page - 1)))
    row.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=Act(action=Action.NOOP).pack()))
    if page + 1 < pages:
        row.append(InlineKeyboardButton(text="▶️", callback_data=nav(page + 1)))
    kb.row(*row)
    kb.row(HOME_BUTTON)


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[HOME_BUTTON]])
