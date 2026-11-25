"""End-to-end dialogs with the bot through a fake Telegram."""
from datetime import datetime, timedelta

from aiogram.methods import SendDocument

from bot.db import Booking
from bot.reminders import send_due_reminders
from bot.slots import bookable_days
from bot.texts import BTN_BOOK, BTN_MY, fmt_day


def third_day_label(cfg):
    today = cfg.now().date()
    return fmt_day(bookable_days(today, cfg.days_ahead, cfg.closed_weekdays)[2], today)


async def book(client, cfg, master="Alex", phone="+37255551234"):
    await client.say(BTN_BOOK)
    await client.press("Haircut ·")
    await client.press(master)
    await client.press(third_day_label(cfg))
    await client.press("10:00")
    await client.press("Confirm")
    if phone:
        await client.say(contact=phone)


async def test_full_booking_flow(make_env):
    env = await make_env()
    anna = env.client(1, "Anna")

    await anna.say("/start")
    assert "Welcome to <b>BookMe Barbershop</b>" in anna.last_text

    await anna.say(BTN_BOOK)
    assert any("Haircut ·" in b for b in anna.buttons())
    await anna.press("Haircut ·")
    assert "Any available master" in anna.buttons()[0]
    await anna.press("Alex")
    await anna.press(third_day_label(env.cfg))
    assert "10:00" in anna.buttons()
    await anna.press("10:00")
    assert "Please check your booking" in anna.last_text and "Alex" in anna.last_text

    await anna.press("Confirm")
    assert "Share your phone number" in anna.last_text

    mark = anna.mark()
    await anna.say(contact="+37255551234")
    sent = anna.texts_since(mark)
    assert any("You're booked!" in t for t in sent)
    assert any("Demo: this is the message the owner receives" in t and "+37255551234" in t for t in sent)

    # second booking: phone is remembered, no phone question
    mark = anna.mark()
    await anna.say(BTN_BOOK)
    await anna.press("Beard trim")
    await anna.press("Maria")
    await anna.press(third_day_label(env.cfg))
    await anna.press("12:00")
    await anna.press("Confirm")
    assert any("You're booked!" in t for t in anna.texts_since(mark))

    await anna.say(BTN_MY)
    assert anna.last_text.count("with ") == 2


async def test_taken_slot_hidden_for_that_master_only(make_env):
    env = await make_env()
    await book(env.client(1, "Anna"), env.cfg)

    bob = env.client(2, "Bob")
    await bob.say(BTN_BOOK)
    await bob.press("Haircut ·")
    await bob.press("Alex")
    await bob.press(third_day_label(env.cfg))
    assert "10:00" not in bob.buttons() and "10:30" in bob.buttons()

    await bob.press("Back")
    await bob.press("Back")
    await bob.press("Any available master")
    await bob.press(third_day_label(env.cfg))
    assert "10:00" in bob.buttons()  # Maria is still free


async def test_double_booking_prevented_at_confirm(make_env):
    env = await make_env()
    anna, bob = env.client(1, "Anna"), env.client(2, "Bob")
    # both reach the confirmation screen for the same slot
    for c in (anna, bob):
        await c.say(BTN_BOOK)
        await c.press("Haircut ·")
        await c.press("Alex")
        await c.press(third_day_label(env.cfg))
        await c.press("10:00")
    await anna.press("Confirm")
    await anna.say(contact="+3721")
    mark = bob.mark()
    await bob.press("Confirm")
    await bob.say(contact="+3722")
    assert any("just taken" in t for t in bob.texts_since(mark))
    assert len(await env.repo.all_bookings()) == 1


async def test_client_cancels(make_env):
    env = await make_env()
    anna = env.client(1, "Anna")
    await book(anna, env.cfg)
    await anna.say(BTN_MY)
    await anna.press("Cancel")
    await anna.press("Yes, cancel it")
    assert "cancelled" in anna.last_text
    await anna.say(BTN_MY)
    assert "no upcoming bookings" in anna.last_text


async def test_restart_mid_flow_recovers(make_env):
    env = await make_env()
    anna = env.client(1, "Anna")
    await anna.say(BTN_BOOK)
    await anna.press("Haircut ·")
    await anna.press("Alex")
    await env.dp.storage.close()
    env.dp.fsm.storage = type(env.dp.storage)()  # simulate memory lost on restart
    await anna.press(third_day_label(env.cfg))
    assert "What would you like to book?" in anna.last_text


async def test_demo_admin_sees_only_own_bookings(make_env):
    env = await make_env()
    anna, bob = env.client(1, "Anna"), env.client(2, "Bob")
    await book(anna, env.cfg)
    await book(bob, env.cfg, master="Maria")

    await bob.say("/admin")
    assert "Owner panel" in bob.last_text and "Demo mode" in bob.last_text
    await bob.press("Pick a day")
    await bob.press(third_day_label(env.cfg))
    assert "Bob" in bob.last_text and "Anna" not in bob.last_text

    await bob.press("Back")
    await bob.press("Export CSV")
    docs = [c for c in env.session.calls if isinstance(c, SendDocument)]
    assert docs and docs[-1].chat_id == 2

    await bob.press("Stats")
    assert "Next 7 days:</b> 1 bookings · €25" in bob.last_text

    await bob.press("Back")
    await bob.press("Broadcast")
    await bob.say("Holiday hours: closed on Monday")
    assert "only you" in bob.last_text
    await bob.press("Send")
    assert "sent to 1 of 1" in bob.last_text


async def test_real_owner_sees_all_and_cancels(make_env):
    env = await make_env(admin_ids=frozenset({99}), demo_mode=False)
    anna, owner, bob = env.client(1, "Anna"), env.client(99, "Owner"), env.client(2, "Bob")
    await book(anna, env.cfg)
    assert any("New booking" in t for t in owner.texts_since(0))

    await bob.say("/admin")  # not an admin, demo off → ignored
    assert bob.mark() == 0

    await owner.say("/admin")
    await owner.press("Pick a day")
    await owner.press(third_day_label(env.cfg))
    assert "Anna" in owner.last_text
    mark = anna.mark()
    await owner.press("❌ #")
    assert any("cancelled by the salon" in t for t in anna.texts_since(mark))


async def test_reminders(make_env):
    env = await make_env()
    now = env.cfg.now()
    await env.client(1, "Anna").say("/start")
    async with env.repo.session() as s:
        s.add_all([
            Booking(user_id=1, service_id=1, master_id=1, start=now + timedelta(hours=23),
                    end=now + timedelta(hours=23, minutes=30), created_at=now - timedelta(days=2)),
            Booking(user_id=1, service_id=1, master_id=2, start=now + timedelta(minutes=90),
                    end=now + timedelta(minutes=120), created_at=now - timedelta(days=2)),
            # booked 1 hour ago for in 3 hours → no 24h reminder makes sense
            Booking(user_id=1, service_id=2, master_id=1, start=now + timedelta(hours=3),
                    end=now + timedelta(hours=3, minutes=30), created_at=now - timedelta(hours=1)),
        ])
        await s.commit()
    assert await send_due_reminders(env.bot, env.repo, env.cfg) == 2
    assert await send_due_reminders(env.bot, env.repo, env.cfg) == 0  # never twice
    texts = [c.text for c in env.session.calls if getattr(c, "chat_id", None) == 1 and hasattr(c, "text")]
    assert any("Reminder: your visit is soon" in t for t in texts)
    assert any("Reminder: your visit is" in t and "soon" not in t for t in texts)
