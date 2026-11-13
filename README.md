# Telegram Helper

A personal companion bot built on **Telegram Business**. It works inside your own chats:

- **Animated dot commands**: type `.train` and your message turns into a moving train.
- **Deleted and edited messages are kept**: when a contact deletes or edits a message, the bot sends you
  the original, including photos, videos and files. If someone replaces a photo in a sent message,
  you get both the old and the new one.
- **Time in everyone's time zone**: `.time 15:00 Warsaw` shows each reader the time in their own zone.
- **Control panel in the bot chat**: deleted messages, edit history, media, full-text search,
  per-chat settings and an animation catalog with previews.
- **Private by design**: the bot serves only you. Other people get no answers and cannot trigger anything,
  and the bot leaves any group it is added to.

## Stack

Python 3.12 · [aiogram 3](https://aiogram.dev) · SQLite (SQLAlchemy 2 async, FTS5 full-text search) ·
Docker Compose · pytest · mypy

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
| `.explosion [text]` / `.boom` | 💣 a fuse burns down and the bomb goes off |
| `.rainbow [text]` | 🌈 rainbow stripes flow across the message |
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

Utility commands (`.save`, `.info`, `.stop`, `.help`) are removed from the chat right away, so the other
person does not see them. Text that starts with a dot but is not a known command is left untouched.

**`.time` examples:**

- `.time 15:00`: today, in your time zone (set in the panel: *Settings → 🕒 Time zone*);
- `.time 12:00 Warsaw`: the time in Warsaw; typos are fine (`warshaw`), as are `Europe/Warsaw` and `UTC+2`;
- `.time 12.02.2026 15:00 New York team call`: a date, a city and a note shown above the time.

## Bot chat panel

- `/menu`: 🗑 Deleted · ✏️ Edits · 🖼 Media · 🔍 Search · 💬 Chats · 🎬 Animations · ⚙️ Settings · 📊 Status
- `/search word`: search over the saved messages.

## Installation

You need Telegram **Premium** (for Telegram Business) and a machine with Docker.

1. Create a bot with [@BotFather](https://t.me/BotFather) and turn on *Bot Settings → Business Mode*.
2. Clone the repository and create `.env` from the example:

   ```bash
   cp .env.example .env
   ```

   Set `BOT_TOKEN` (from BotFather) and `OWNER_ID` (your Telegram user ID). The other settings are optional:
   `CACHE_LIMIT_MB` (disk space for the cache, 10 GB by default) and `TIMEZONE` (default time zone for `.time`).
3. Start the bot:

   ```bash
   docker compose up -d --build
   ```

4. In Telegram: *Settings → Telegram Business → Chatbots*, add the bot, give it access to your chats and the
   rights to **reply to messages** and **delete sent messages**.
5. Send `/start` to the bot.

Data (database and media) is stored in `./data` and survives restarts and updates.
Logs: `docker compose logs -f`.

To deploy to your own server over SSH, copy `.deploy.env.example` to `.deploy.env`, set `DEPLOY_HOST`
and run `./deploy.sh`.

## Good to know

- **Cache size**: when the cache grows past `CACHE_LIMIT_MB`, the oldest media files are removed first
  (the message text stays), then the oldest messages. Current usage is shown in *📊 Status*.
- **View-once photos** are usually not delivered to bots by Telegram, so they may not be saved.
- **Files larger than 20 MB** cannot be downloaded by bots; the bot keeps only a record of them.

## Development

Project structure, adding animations and running the tests: see [DEVELOPMENT.md](DEVELOPMENT.md).
