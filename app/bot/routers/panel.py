"""Control panel in the private chat with the bot (owner only)."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.animations import AnimationEngine, Target, get_animation
from app.bot import views
from app.bot.filters import IsOwner
from app.bot.keyboards import Act, Action, Nav, Section
from app.config import Settings
from app.db import Database
from app.services.cache import CacheService, ChatFlag
from app.services.formatting import chat_name, esc, fmt_dt
from app.services.media import MediaService
from app.services.notifier import Notifier
from app.services.settings_store import SETTINGS, SettingsStore
from app.services.timezones import resolve_zone

router = Router(name="panel")
router.message.filter(F.chat.type == "private", IsOwner())
router.callback_query.filter(IsOwner())


class SearchFlow(StatesGroup):
    waiting_query = State()


class TimezoneFlow(StatesGroup):
    waiting_zone = State()


async def _show(callback: CallbackQuery, view: views.View) -> None:
    """Replaces the panel message with a new screen (or sends a new one if editing fails)."""
    text, markup = view
    message = callback.message
    if isinstance(message, Message):
        try:
            await message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                await message.answer(text, reply_markup=markup)
    await callback.answer()


async def _send(message: Message, view: views.View) -> None:
    text, markup = view
    await message.answer(text, reply_markup=markup)


# ---------- commands ----------


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext, cache: CacheService) -> None:
    await state.set_state(None)
    await _send(message, await views.home(cache))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(views.commands_help())


@router.message(Command("search"))
async def cmd_search(message: Message, command: CommandObject, state: FSMContext, cache: CacheService) -> None:
    if not command.args:
        await state.set_state(SearchFlow.waiting_query)
        await _send(message, views.search_prompt())
        return
    await state.update_data(query=command.args)
    await _send(message, await views.search_results(cache, command.args, 0))


@router.message(TimezoneFlow.waiting_zone, F.text)
async def on_timezone_input(message: Message, state: FSMContext, store: SettingsStore) -> None:
    zone = resolve_zone(message.text or "")
    if zone is None:
        await message.answer("🤔 Unknown time zone. Try a city like <code>Warsaw</code> or <code>UTC+2</code>.")
        return
    await store.set_timezone(zone)
    await state.set_state(None)
    await message.answer(f"✅ Time zone set: <b>{esc(zone.label)}</b>")
    await _send(message, views.settings(store))


@router.message(SearchFlow.waiting_query, F.text)
async def on_search_query(message: Message, state: FSMContext, cache: CacheService) -> None:
    query = message.text or ""
    await state.update_data(query=query)
    await _send(message, await views.search_results(cache, query, 0))


# ---------- navigation ----------


@router.callback_query(Nav.filter())
async def on_nav(
    callback: CallbackQuery,
    callback_data: Nav,
    state: FSMContext,
    cache: CacheService,
    store: SettingsStore,
    db: Database,
    media: MediaService,
    started_at: float,
    settings: Settings,
) -> None:
    page = callback_data.page
    if callback_data.section not in (Section.SEARCH, Section.SEARCH_PAGE):
        await state.set_state(None)

    match callback_data.section:
        case Section.HOME:
            view = await views.home(cache)
        case Section.DELETED:
            view = await views.deleted(cache, page, callback_data.chat_id)
        case Section.EDITS:
            view = await views.edits(cache, page)
        case Section.MEDIA:
            view = await views.media(cache, page)
        case Section.SEARCH:
            await state.set_state(SearchFlow.waiting_query)
            view = views.search_prompt()
        case Section.SEARCH_PAGE:
            query = (await state.get_data()).get("query")
            view = await views.search_results(cache, query, page) if query else views.search_prompt()
        case Section.CHATS:
            view = await views.chats(cache, page)
        case Section.ANIMS:
            view = views.animations()
        case Section.SETTINGS:
            view = views.settings(store)
        case Section.STATUS:
            view = await views.status(cache, db, media, started_at, settings.cache_limit_bytes)
    await _show(callback, view)


# ---------- actions ----------


@router.callback_query(Act.filter(F.action == Action.NOOP))
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(Act.filter(F.action == Action.SHOW))
async def on_show(callback: CallbackQuery, callback_data: Act, cache: CacheService, notifier: Notifier) -> None:
    msg = await cache.message(callback_data.id)
    if msg is None:
        await callback.answer("The message is no longer in the cache", show_alert=True)
        return
    chat = await cache.chat(msg.chat_id)
    header = f"📤 👤 {esc(msg.from_name)} · 💬 {esc(chat_name(chat, msg.chat_id))} · 🕒 {fmt_dt(msg.date)}"
    await notifier.send_message_copy(msg, header)
    await callback.answer()


@router.callback_query(Act.filter(F.action == Action.CHAT))
async def on_chat(callback: CallbackQuery, callback_data: Act, cache: CacheService) -> None:
    await _show(callback, await views.chat_card(cache, callback_data.id))


@router.callback_query(Act.filter(F.action.in_({Action.CHAT_SAVE, Action.CHAT_NOTIFY})))
async def on_chat_toggle(callback: CallbackQuery, callback_data: Act, cache: CacheService) -> None:
    flag: ChatFlag = "save_enabled" if callback_data.action == Action.CHAT_SAVE else "notify_enabled"
    await cache.toggle_chat(callback_data.id, flag)
    await _show(callback, await views.chat_card(cache, callback_data.id))


@router.callback_query(Act.filter(F.action == Action.SET))
async def on_setting(callback: CallbackQuery, callback_data: Act, store: SettingsStore) -> None:
    if callback_data.key in SETTINGS:
        await store.toggle(callback_data.key)
    await _show(callback, views.settings(store))


@router.callback_query(Act.filter(F.action == Action.TIMEZONE))
async def on_timezone(callback: CallbackQuery, state: FSMContext, store: SettingsStore) -> None:
    await state.set_state(TimezoneFlow.waiting_zone)
    await _show(callback, views.timezone_prompt(store))


@router.callback_query(Act.filter(F.action == Action.ANIM))
async def on_anim_preview(callback: CallbackQuery, callback_data: Act, engine: AnimationEngine) -> None:
    anim = get_animation(callback_data.key)
    if anim is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    preview = await callback.message.answer(f"▶️ .{anim.command}")
    engine.start(anim, "", Target(preview.chat.id, preview.message_id))
    await callback.answer(anim.title)
