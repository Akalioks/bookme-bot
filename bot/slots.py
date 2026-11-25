"""Pure scheduling logic — no database, no Telegram. Easy to test."""
from datetime import date, datetime, time, timedelta

Interval = tuple[datetime, datetime]


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def day_slots(
    day: date,
    open_time: time,
    close_time: time,
    step_min: int,
    duration_min: int,
    busy: list[Interval],
    now: datetime,
    min_lead_min: int = 0,
) -> list[datetime]:
    """Start times on `day` where a service of `duration_min` fits without clashing with `busy`."""
    start = datetime.combine(day, open_time)
    day_end = datetime.combine(day, close_time)
    earliest = now + timedelta(minutes=min_lead_min)
    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)

    result = []
    s = start
    while s + duration <= day_end:
        if s >= earliest and not any(overlaps(s, s + duration, b, e) for b, e in busy):
            result.append(s)
        s += step
    return result


def bookable_days(today: date, days_ahead: int, closed_weekdays: frozenset[int]) -> list[date]:
    days = (today + timedelta(days=i) for i in range(days_ahead + 1))
    return [d for d in days if d.weekday() not in closed_weekdays]
