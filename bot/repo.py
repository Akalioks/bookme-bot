"""All database queries live here, so handlers stay short and readable."""
from datetime import date, datetime, time, timedelta
from time import time as unix_now

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from .config import Config
from .db import Base, Booking, Master, Service, User, WebLogin
from .slots import day_slots, overlaps

WEB_LOGIN_TTL_SEC = 300  # a login link from the admin panel works for 5 minutes
REMINDERS = {"24h": timedelta(hours=24), "2h": timedelta(hours=2)}


class Repo:
    def __init__(self, engine: AsyncEngine, cfg: Config):
        self.engine = engine
        self.cfg = cfg
        self.session = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    async def create(cls, cfg: Config) -> "Repo":
        engine = create_async_engine(cfg.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return cls(engine, cfg)

    async def close(self) -> None:
        await self.engine.dispose()

    # ---------- users ----------
    async def ensure_user(self, user_id: int, full_name: str, username: str | None) -> User:
        async with self.session() as s:
            user = await s.get(User, user_id)
            if user is None:
                user = User(id=user_id, full_name=full_name, username=username, created_at=self.cfg.now())
                s.add(user)
            else:
                user.full_name, user.username = full_name, username
            await s.commit()
            return user

    async def get_user(self, user_id: int) -> User | None:
        async with self.session() as s:
            return await s.get(User, user_id)

    async def set_phone(self, user_id: int, phone: str) -> None:
        async with self.session() as s:
            user = await s.get(User, user_id)
            if user:
                user.phone = phone
                await s.commit()

    async def all_user_ids(self) -> list[int]:
        async with self.session() as s:
            return list((await s.scalars(select(User.id))).all())

    # ---------- catalog ----------
    async def services(self) -> list[Service]:
        async with self.session() as s:
            return list((await s.scalars(select(Service).where(Service.active).order_by(Service.id))).all())

    async def service(self, service_id: int) -> Service | None:
        async with self.session() as s:
            return await s.get(Service, service_id)

    async def masters(self) -> list[Master]:
        async with self.session() as s:
            return list((await s.scalars(select(Master).where(Master.active).order_by(Master.id))).all())

    async def master(self, master_id: int) -> Master | None:
        async with self.session() as s:
            return await s.get(Master, master_id)

    # ---------- availability ----------
    async def _busy(self, s, master_id: int, day: date) -> list[tuple[datetime, datetime]]:
        day_start = datetime.combine(day, time.min)
        rows = await s.execute(
            select(Booking.start, Booking.end).where(
                Booking.master_id == master_id,
                Booking.status == "active",
                Booking.start >= day_start,
                Booking.start < day_start + timedelta(days=1),
            )
        )
        return [(r.start, r.end) for r in rows]

    async def free_slots(self, service: Service, master_id: int | None, day: date) -> list[datetime]:
        """Free start times. master_id=None means 'any master' (union of everyone's free time)."""
        cfg = self.cfg
        master_ids = [master_id] if master_id else [m.id for m in await self.masters()]
        found: set[datetime] = set()
        async with self.session() as s:
            for mid in master_ids:
                busy = await self._busy(s, mid, day)
                found.update(day_slots(day, cfg.open_time, cfg.close_time, cfg.slot_step_min,
                                       service.duration_min, busy, cfg.now(), cfg.min_lead_min))
        return sorted(found)

    async def create_booking(self, user_id: int, service_id: int, master_id: int | None,
                             start: datetime) -> Booking | None:
        """Books the slot, re-checking it is still free. Returns None if someone took it first."""
        async with self.session() as s:
            service = await s.get(Service, service_id)
            if service is None or start < self.cfg.now():
                return None
            end = start + timedelta(minutes=service.duration_min)
            candidates = [master_id] if master_id else [m.id for m in await self.masters()]
            for mid in candidates:
                busy = await self._busy(s, mid, start.date())
                if not any(overlaps(start, end, b, e) for b, e in busy):
                    booking = Booking(user_id=user_id, service_id=service_id, master_id=mid,
                                      start=start, end=end, created_at=self.cfg.now())
                    s.add(booking)
                    await s.commit()
                    return await s.get(Booking, booking.id, populate_existing=True)
            return None

    # ---------- bookings ----------
    async def booking(self, booking_id: int) -> Booking | None:
        async with self.session() as s:
            return await s.get(Booking, booking_id)

    async def upcoming_for_user(self, user_id: int) -> list[Booking]:
        async with self.session() as s:
            q = (select(Booking).where(Booking.user_id == user_id, Booking.status == "active",
                                       Booking.start >= self.cfg.now()).order_by(Booking.start))
            return list((await s.scalars(q)).unique().all())

    async def cancel(self, booking_id: int, only_user_id: int | None = None) -> Booking | None:
        """Cancels an active booking. With only_user_id, cancels it only if it belongs to that user."""
        async with self.session() as s:
            b = await s.get(Booking, booking_id)
            if b is None or b.status != "active" or (only_user_id and b.user_id != only_user_id):
                return None
            b.status = "cancelled"
            await s.commit()
            return b

    async def bookings_on(self, day: date, user_id: int | None = None) -> list[Booking]:
        start = datetime.combine(day, time.min)
        q = select(Booking).where(Booking.status == "active", Booking.start >= start,
                                  Booking.start < start + timedelta(days=1))
        if user_id:
            q = q.where(Booking.user_id == user_id)
        async with self.session() as s:
            return list((await s.scalars(q.order_by(Booking.start, Booking.master_id))).unique().all())

    async def all_bookings(self, user_id: int | None = None) -> list[Booking]:
        q = select(Booking).order_by(Booking.start)
        if user_id:
            q = q.where(Booking.user_id == user_id)
        async with self.session() as s:
            return list((await s.scalars(q)).unique().all())

    async def stats(self, start: datetime, end: datetime, user_id: int | None = None) -> dict:
        q = (select(Service.name, func.count(Booking.id), func.sum(Service.price))
             .join(Service, Booking.service_id == Service.id)
             .where(Booking.status == "active", Booking.start >= start, Booking.start < end)
             .group_by(Service.name).order_by(func.count(Booking.id).desc()))
        if user_id:
            q = q.where(Booking.user_id == user_id)
        async with self.session() as s:
            rows = (await s.execute(q)).all()
        return {
            "count": sum(r[1] for r in rows),
            "revenue": sum(r[2] or 0 for r in rows),
            "by_service": [(r[0], r[1]) for r in rows],
        }

    # ---------- reminders ----------
    async def due_reminders(self) -> list[tuple[Booking, str]]:
        """Bookings whose 24h / 2h reminder is due now.

        A reminder is skipped if the booking was made after its moment
        (no 'see you tomorrow' for a booking made 3 hours ahead).
        """
        now = self.cfg.now()
        async with self.session() as s:
            q = select(Booking).where(Booking.status == "active", Booking.start > now,
                                      Booking.start <= now + REMINDERS["24h"])
            bookings = (await s.scalars(q)).unique().all()
        due = []
        for b in bookings:
            # check the closest reminder first: if the bot was offline, don't send a stale "tomorrow"
            for kind in ("2h", "24h"):
                delta = REMINDERS[kind]
                already = b.reminded_24h if kind == "24h" else b.reminded_2h
                if not already and now >= b.start - delta and b.created_at < b.start - delta:
                    due.append((b, kind))
                    break
        return due

    async def mark_reminded(self, booking_id: int, kind: str) -> None:
        async with self.session() as s:
            b = await s.get(Booking, booking_id)
            if b:
                b.reminded_24h = True  # the 2h reminder also makes the 24h one pointless
                if kind == "2h":
                    b.reminded_2h = True
                await s.commit()


    # ---------- web admin panel logins ----------
    async def web_login(self, token: str) -> WebLogin | None:
        """A login request from the admin panel that is still waiting for an answer."""
        async with self.session() as s:
            row = await s.get(WebLogin, token)
            if row is None or row.status != "pending" or unix_now() - row.created_at > WEB_LOGIN_TTL_SEC:
                return None
            return row

    async def answer_web_login(self, token: str, approve: bool, user_id: int, first_name: str,
                               last_name: str | None, username: str | None) -> bool:
        """Approves or denies a pending login. False if it expired or was already answered."""
        async with self.session() as s:
            row = await s.get(WebLogin, token)
            if row is None or row.status != "pending" or unix_now() - row.created_at > WEB_LOGIN_TTL_SEC:
                return False
            row.status = "approved" if approve else "denied"
            row.user_id, row.first_name, row.last_name, row.username = user_id, first_name, last_name, username
            await s.commit()
            return True


async def seed_demo_data(repo: Repo) -> None:
    """Fills an empty database with a sample barbershop. Edit to taste."""
    async with repo.session() as s:
        if await s.scalar(select(func.count(Service.id))):
            return
        s.add_all([
            Service(name="Haircut", emoji="✂️", duration_min=30, price=25),
            Service(name="Beard trim", emoji="🧔", duration_min=30, price=15),
            Service(name="Haircut + Beard", emoji="💈", duration_min=60, price=35),
            Service(name="Kids haircut", emoji="👦", duration_min=30, price=18),
            Master(name="Alex"),
            Master(name="Maria"),
        ])
        await s.commit()
