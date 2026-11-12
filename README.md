# Telegram Helper

A personal companion bot built on **Telegram Business**:

- **Animated dot commands right in your chats**: type `.train` and the message turns into a moving train.
- **Chat cache**: messages your contacts delete or edit don't disappear, the bot sends them to you.
  If someone replaces a photo or file in a sent message, you get both the old and the new one.
- **Control panel in the bot chat**: deleted messages, edits, media, search, per-chat settings, animation catalog.

## Setup

1. Create a bot with @BotFather and enable *Bot Settings → Business Mode*.
2. In Telegram (requires **Premium**): *Settings → Telegram Business → Chatbots*, add the bot, give it access
   to your chats and the rights to **reply to messages** and **delete sent messages**.
3. Fill in `.env` (see `.env.example`): `BOT_TOKEN`, `OWNER_ID`.
4. Send `/start` to the bot.

The bot serves only its owner (`OWNER_ID`):

- it never answers anyone else: other people's messages, commands and button presses in the bot chat are ignored;
- dot commands work only when the owner sends them; the other person in a chat cannot trigger anything;
- if someone connects the bot to their own Business account, those updates are ignored and nothing is cached;
- if someone adds the bot to a group or channel, it leaves right away;
- file names from senders are sanitized before anything is written to disk.

## Chat commands

| Command | What it does |
|---|---|
| `.train [text]` | 🚂 a train rides across the line |
| `.love [text]` / `.heart` | ❤️ a heart is drawn and shimmers in colors |
| `.type text` | typewriter effect with a cursor |
| `.magic text` | text emerges from random symbols |
| `.loading [what]` | progress bar from 0 to 100% |
| `.hack [target]` | fake hack with scrolling code |
| `.countdown 5` | countdown and 💥 |
| `.rocket [text]` | 🚀 a rocket takes off |
| `.moon [text]` | 🌑 → 🌕 moon phases |
| `.snow` / `.rain` | falling snow / rain |
| `.clock` | clock hands make a full circle |
| `.flip` | (╯°□°)╯︵ ┻━┻ |
| `.8ball question` | magic 8-ball |
| `.dice` / `.roll` | dice roll |
| `.time [date] HH:MM [city] [note]` | 🕒 a time everyone sees in their own time zone |
| `.stop` | stop the animation in this chat |
| `.save` *(as a reply)* | save the message and its media, send it to the bot chat |
| `.info` *(as a reply)* | message and author details, sent to the bot chat |
| `.help` | command list, sent to the bot chat |

### `.time`

The command message is replaced with Telegram's date-time entity: it stores an exact moment, and every reader's
app shows it in their own time zone.

- `.time 15:00`: today, in your time zone (*Settings → 🕒 Time zone* in the panel).
- `.time 12:00 Warsaw`: the time is taken in Warsaw; typos are fine (`warshaw`), as are `Europe/Warsaw` and `UTC+2`.
- `.time 12.02.2026 15:00 New York team call`: date, time, city, and a note shown above the time.

Apps that don't support the entity show plain text such as `12.02.2026 15:00 UTC+01:00`
(Telegram allows at most 31 characters inside the entity).

Utility commands (`.save`, `.info`, `.stop`, `.help`) are deleted from the chat right away so the other person
does not see them. Text that starts with a dot but is not a known command is left untouched.

## Bot chat panel

`/menu`: 🗑 Deleted · ✏️ Edits · 🖼 Media · 🔍 Search · 💬 Chats · 🎬 Animations · ⚙️ Settings · 📊 Status
`/search word`: full-text search over the cache.

## Cache size

The cache (media files + database) lives on disk in `./data` and is limited by `CACHE_LIMIT_MB` in `.env`
(default `10240`, i.e. 10 GB). The bot checks it every 10 minutes; when the limit is exceeded it frees space
down to 90% of it: first the oldest media files (the message text stays), then, if needed, the oldest messages.
Current usage is shown in *📊 Status*.

## Telegram limitations

- **View-once / self-destructing photos** are usually not provided by the Bot API. The bot downloads every media
  file it receives; for view-once media you can try `.save` as a reply, but there is no guarantee.
- The Bot API cannot download files larger than **20 MB**; only a record of them is kept.
- If your command message cannot be edited, the bot deletes it and plays the animation in a new message sent
  on your behalf.

## Architecture

```
app/
├─ main.py                  # wires services and routers, starts polling
├─ config.py                # settings from .env
├─ bot/
│  ├─ routers/
│  │  ├─ business.py        # connection, new messages, edits, deletions
│  │  ├─ dot_commands.py    # the owner's .commands in chats
│  │  ├─ panel.py           # control panel in the bot chat
│  │  └─ membership.py      # leaves any group or channel the bot is added to
│  ├─ views.py              # panel screens (text + keyboard)
│  ├─ keyboards.py          # callback data, sections, pagination
│  ├─ filters.py            # IsOwner, DotCommand
│  └─ middlewares.py        # foreign-connection guard, automatic message caching
├─ animations/
│  ├─ engine.py             # plays frames by editing a message
│  ├─ registry.py           # @animation(...) registration
│  └─ catalog/              # the animations, loaded automatically
├─ services/
│  ├─ cache.py              # saving, edits, deletions, queries, size limit
│  ├─ media.py              # file downloads
│  ├─ notifier.py           # notifications to the owner
│  ├─ settings_store.py     # settings changed from the panel
│  └─ formatting.py         # HTML formatting helpers
└─ db/                      # SQLite + FTS5, models
```

Update flow: update → `OwnerConnectionMiddleware` (owner's connection only) → `CacheMiddleware` (save) → router → services.

### Adding an animation

Create a module in `app/animations/catalog/`:

```python
from collections.abc import Iterator

from app.animations.registry import animation


@animation("wave", "Wave", "Waves a hand", interval=0.5)
def wave(args: str) -> Iterator[str]:
    for hand in ["👋", "🖐", "👋", "🖐"]:
        yield hand
    yield f"👋 {args or 'Hi!'}"
```

That's it: `.wave` works and a preview button appears in the panel.

## Running

Locally:

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m app.main
```

Docker:

```bash
docker compose up -d --build
```

Deploy to the server from your machine (Git Bash on Windows). Copy `.deploy.env.example` to `.deploy.env`
and set `DEPLOY_HOST`, then run:

```bash
./deploy.sh
```

The code goes to `/srv/telegramHelper`, `.env` is uploaded on the first run, the database in `./data` is preserved.
Server logs: `cd /srv/telegramHelper && docker compose logs -f`.
