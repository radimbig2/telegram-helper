# Development

## Project structure

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
│  ├─ registry.py           # registration and catalog loading
│  ├─ frame_file.py         # JSON frame files: format and validation
│  └─ catalog/              # the animations (*.json and *.py), loaded automatically
├─ services/
│  ├─ cache.py              # saving, edits, deletions, queries, size limit
│  ├─ media.py              # file downloads
│  ├─ notifier.py           # notifications to the owner
│  ├─ settings_store.py     # settings changed from the panel
│  ├─ timezones.py          # .time parsing and time zones
│  └─ formatting.py         # HTML formatting helpers
└─ db/                      # SQLite + FTS5, models, lightweight migrations
tests/                      # pytest suite
```

Update flow: update → `OwnerConnectionMiddleware` (the owner's connection only) → `CacheMiddleware` (save)
→ router → services.

## Security model

- Every reply goes to `OWNER_ID` or to the chat where the owner ran a command.
- The panel answers only the owner and only in the private chat with the bot.
- Dot commands run only when the owner sends them.
- Business connections are verified through the API; foreign ones are ignored and nothing from them is cached.
- The bot leaves any group or channel it is added to.
- Text from other people is HTML-escaped; file names from senders are sanitized before writing to disk.
- The container runs as a non-root user and exposes no ports.

## Adding an animation

Everything in `app/animations/catalog/` is loaded automatically: the command works and a preview button
appears in the panel. Pick the kind that fits.

**A fixed list of frames: a JSON file, no code.** `app/animations/catalog/wave.json`
(the file name must match the command):

```json
{
  "command": "wave",
  "title": "Wave",
  "description": "Waves a hand",
  "interval": 0.5,
  "default_text": "Hi!",
  "frames": ["👋", "🖐", "👋", "🖐", ["two-line", "frame"], "👋 {text}"]
}
```

- `{text}` is replaced with the text after the command (`.wave hello`), or with `default_text`.
  A frame with `{text}` is skipped when both are empty.
- A frame is a string, or a list of strings for a multi-line frame.
- Frames are plain text: the user's text is escaped, so it cannot break the markup.
- Optional keys: `aliases`, `usage` (derived automatically). Unknown keys and typos fail at startup.

Examples: `flip.json`, `clock.json`, `moon.json`, `explosion.json`.

**Computed frames: a Python generator.** When the frames depend on randomness, on the user's text,
or are drawn by a formula (`train`, `rainbow`, `dice`, `type`, `hack`, ...):

```python
from collections.abc import Iterator

from app.animations.registry import animation


@animation("wave", "Wave", "Waves a hand", interval=0.5)
def wave(args: str) -> Iterator[str]:
    for hand in ["👋", "🖐", "👋", "🖐"]:
        yield hand
    yield f"👋 {args or 'Hi!'}"
```

New animations are checked by the tests automatically, nothing to add there.

## Running locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m app.main
```

(`.venv/bin/...` on Linux and macOS.)

## Tests and type checks

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m mypy
```

The tests run the real dispatcher against a fake Telegram that records every Bot API call, so nothing
is sent anywhere and the real `.env` is never read. They cover:

- every animation in the catalog, with empty, long, Unicode and markup input: frame count, Telegram's
  text limit, escaping;
- the animation engine: editing, the delete-and-resend fallback, the frame limit, `.stop`;
- security: outsiders get no answers and change nothing, foreign Business accounts are ignored;
- the cache: edits, replaced media, the size limit, database migrations;
- `.time`: parsing, time zones and daylight saving time.

## Deploying

`deploy.sh` uploads the code to a server over SSH and restarts the container
(Git Bash on Windows works). Copy `.deploy.env.example` to `.deploy.env` and set `DEPLOY_HOST`;
`DEPLOY_DIR` defaults to `/srv/telegramHelper`.

```bash
./deploy.sh
```

`.env` is uploaded only on the first run, the data in `./data` is preserved, and old Docker images
and build cache are cleaned up.
