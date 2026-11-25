from datetime import date, datetime, time

from bot.slots import bookable_days, day_slots

DAY = date(2030, 1, 7)  # a Monday
NOW = datetime(2030, 1, 1, 9, 0)


def hm(h, m=0):
    return datetime.combine(DAY, time(h, m))


def test_full_free_day():
    slots = day_slots(DAY, time(10), time(12), 30, 30, [], NOW)
    assert slots == [hm(10), hm(10, 30), hm(11), hm(11, 30)]


def test_long_service_must_fit_before_closing():
    slots = day_slots(DAY, time(10), time(12), 30, 60, [], NOW)
    assert slots[-1] == hm(11)


def test_busy_interval_blocks_overlaps_only():
    busy = [(hm(10, 30), hm(11, 30))]
    assert day_slots(DAY, time(10), time(12), 30, 30, busy, NOW) == [hm(10), hm(11, 30)]
    # a 60-min service at 10:00 would run into the 10:30 booking
    assert day_slots(DAY, time(10), time(13), 30, 60, busy, NOW) == [hm(11, 30), hm(12)]


def test_past_and_lead_time_excluded():
    now = hm(10, 10)
    assert day_slots(DAY, time(10), time(12), 30, 30, [], now, min_lead_min=30)[0] == hm(11)


def test_closed_weekdays_skipped():
    days = bookable_days(DAY, 6, frozenset({6}))  # Mon..Sun, Sunday closed
    assert len(days) == 6 and all(d.weekday() != 6 for d in days)
