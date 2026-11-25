"""Every text the bot sends. Change wording here — no need to touch the logic."""
from datetime import date, timedelta
from html import escape

BTN_BOOK = "📅 Book an appointment"
BTN_MY = "🗓 My bookings"
BTN_ABOUT = "ℹ️ About us"
BTN_SKIP = "Skip"

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_day(d: date, today: date) -> str:
    if d == today:
        return f"Today, {d:%d %b}"
    if d == today + timedelta(days=1):
        return f"Tomorrow, {d:%d %b}"
    return f"{WEEKDAYS[d.weekday()]}, {d:%d %b}"


def welcome(name: str, business: str, demo: bool) -> str:
    text = (f"👋 Hi, {escape(name)}!\n\nWelcome to <b>{escape(business)}</b>. "
            "Book a visit in 30 seconds — pick a service, a master and a time that suits you.\n\n"
            "I'll remind you before the visit, and you can cancel any time.")
    if demo:
        text += ("\n\n🧪 <i>This is a demo bot. Send /admin to see the owner's panel "
                 "(in demo mode it shows only your own bookings).</i>")
    return text


def about(business: str, address: str, phone: str, hours: str, closed: str) -> str:
    return (f"<b>{escape(business)}</b>\n\n📍 {escape(address)}\n📞 {escape(phone)}\n"
            f"🕙 {hours}" + (f", closed on {closed}" if closed else ""))


def booking_line(b, today: date) -> str:
    return (f"<b>{fmt_day(b.start.date(), today)}, {b.start:%H:%M}</b>\n"
            f"{b.service.emoji} {escape(b.service.name)} with {escape(b.master.name)} · €{b.service.price}")


def summary(service, master_name: str, start, today: date) -> str:
    return ("Please check your booking:\n\n"
            f"{service.emoji} <b>{escape(service.name)}</b> · {service.duration_min} min · €{service.price}\n"
            f"👤 {escape(master_name)}\n"
            f"📅 {fmt_day(start.date(), today)} at <b>{start:%H:%M}</b>")


def booked(b, today: date, address: str) -> str:
    return (f"✅ <b>You're booked!</b>\n\n{booking_line(b, today)}\n📍 {escape(address)}\n\n"
            "I'll remind you 24 hours and 2 hours before. See you! 👋")


def owner_new_booking(b, today: date) -> str:
    phone = escape(b.user.phone) if b.user.phone else "no phone"
    username = f" @{escape(b.user.username)}" if b.user.username else ""
    return (f"🆕 <b>New booking #{b.id}</b>\n\n{booking_line(b, today)}\n"
            f"👤 {escape(b.user.full_name)}{username} · {phone}")


def reminder(b, kind: str, address: str, today: date) -> str:
    if kind == "2h":
        when = "soon"
    else:
        when = "tomorrow" if b.start.date() == today + timedelta(days=1) else "today"
    return (f"⏰ Reminder: your visit is {when}, at <b>{b.start:%H:%M}</b>.\n\n"
            f"{b.service.emoji} {escape(b.service.name)} with {escape(b.master.name)}\n📍 {escape(address)}")


ASK_SERVICE = "What would you like to book?"
ASK_MASTER = "Choose a master:"
ASK_DAY = "Choose a day:"
ASK_PHONE = ("Almost done! Share your phone number so we can reach you if something changes — "
             "or tap <b>Skip</b>.")
NO_SLOTS = "😔 No free time on {day}. Please choose another day:"
SLOT_TAKEN = "😔 Sorry, that time was just taken. Please choose another one:"
SESSION_EXPIRED = "This menu has expired — let's start again."
ABORTED = "Booking cancelled. Tap <b>📅 Book an appointment</b> whenever you're ready."
NO_BOOKINGS = "You have no upcoming bookings."
