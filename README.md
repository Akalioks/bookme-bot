# BookMe — Booking Bot for Telegram

[Русская версия](README.ru.md) · **Live demo: [@bookmedemobot](https://t.me/bookmedemobot)**

A Telegram bot for barbershops and salons. Clients pick a service, a master, a day and a time slot with buttons; the bot reminds them before the visit, and the owner manages everything right inside Telegram.

All bot texts live in `bot/texts.py`.

## Features

**Client**
- Book in a few taps: service → master (or "any available") → day → time → confirm.
- Share a phone number with one button; the bot remembers it for next time.
- "My bookings": view upcoming visits and cancel any of them (with confirmation).
- Reminders 24 h and 2 h before the visit, with a "can't make it" button.

**Owner** (`/admin`)
- Schedule for today, tomorrow or any day, with client names and phone numbers.
- Cancel a booking — the client is notified automatically.
- A notification for every new booking and every client cancellation.
- Stats: bookings and expected revenue for the next 7 days, 30-day totals, top services.
- Broadcast to all clients, with a preview before sending.
- Export all bookings to CSV (opens in Excel / Google Sheets).

**Reliability**
- Double bookings are impossible: the slot is re-checked right before saving.
- If the bot restarts while a client is mid-booking, it simply offers to start over instead of breaking.
- Reminders are never sent twice after a restart — their state is stored in the database.

## Demo mode

With `DEMO_MODE=true` any visitor can open `/admin` and try the owner panel, but sees **only their own** bookings, and broadcasts go **only to them**. A potential customer can try both sides of the bot without seeing anyone else's names or phone numbers.

For a real business set `DEMO_MODE=false` and put the owner's Telegram ID into `ADMIN_IDS`.

## Run locally

1. In Telegram, open **@BotFather**, send `/newbot` and copy the token.
2. Get your Telegram ID from **@userinfobot**.
3. In the project folder (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

4. Put the token into `BOT_TOKEN` and your ID into `ADMIN_IDS` in `.env`.
5. Start the bot:

```powershell
.venv\Scripts\python -m bot
```

On first start the bot creates `bookme.db` with sample data (4 services, 2 masters). Change them in `seed_demo_data` in `bot/repo.py`, then delete `bookme.db`.

## Tests

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

13 end-to-end tests drive complete dialogs through a fake Telegram: booking, taken slots, double booking, cancellation, restarts, the owner panel, demo mode and reminders.

## Deployment

- **Docker:**
  `docker build -t bookme .`, then
  `docker run -d --env-file .env -e DATABASE_URL=sqlite+aiosqlite:////app/data/bookme.db -v bookme-data:/app/data --restart always bookme`.
  The `DATABASE_URL` override keeps the database inside the volume so it survives rebuilds.
- **Railway / Render:** connect this repository and add the variables from `.env`.

## Web admin login

The bot also confirms logins to the web panel ([admin-dashboard](https://github.com/Akalioks/admin-dashboard)). The panel shows a link like `t.me/<bot>?start=login_<code>`; the bot asks "Log in to the admin panel?" with Confirm / Cancel and records the answer in the `web_logins` table. Links expire after 5 minutes — see `bot/handlers/weblogin.py`.

## Project structure

```
bot/
  __main__.py      entry point, menu commands, background reminders
  app.py           dispatcher setup, user registration
  config.py        settings from .env
  db.py            tables: users, services, masters, bookings
  repo.py          all database queries and demo data
  slots.py         free-slot calculation (pure logic)
  texts.py         all bot texts
  keyboards.py     all buttons
  reminders.py     24 h / 2 h reminders
  handlers/
    user.py        /start, About, My bookings, cancellation
    booking.py     booking flow
    admin.py       owner panel
    weblogin.py    web admin login confirmation
tests/
```

## Tech stack

Python, aiogram 3, SQLAlchemy 2 (SQLite / PostgreSQL), asyncio, Docker, pytest.

## License

[MIT](LICENSE)
