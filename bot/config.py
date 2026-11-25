"""Settings are read from the .env file (see .env.example)."""
import os
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def _ids(raw: str) -> frozenset[int]:
    return frozenset(int(x) for x in raw.replace(" ", "").split(",") if x)


def _bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    demo_mode: bool
    tz: ZoneInfo
    database_url: str
    business_name: str
    address: str
    phone: str
    open_time: time
    close_time: time
    slot_step_min: int
    days_ahead: int
    closed_weekdays: frozenset[int]  # 0 = Monday … 6 = Sunday
    min_lead_min: int                # can't book earlier than N minutes from now

    def now(self) -> datetime:
        """Current local time of the business (naive, used everywhere in the DB)."""
        return datetime.now(self.tz).replace(tzinfo=None)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_config(**overrides) -> Config:
    load_dotenv()
    env = os.getenv
    values: dict[str, Any] = dict(
        bot_token=env("BOT_TOKEN", ""),
        admin_ids=_ids(env("ADMIN_IDS", "")),
        demo_mode=_bool(env("DEMO_MODE", "true")),
        tz=ZoneInfo(env("TIMEZONE", "Europe/Tallinn")),
        database_url=env("DATABASE_URL", "sqlite+aiosqlite:///bookme.db"),
        business_name=env("BUSINESS_NAME", "BookMe Barbershop"),
        address=env("BUSINESS_ADDRESS", "Viru 1, Tallinn"),
        phone=env("BUSINESS_PHONE", "+372 5555 0000"),
        open_time=time.fromisoformat(env("OPEN_TIME", "10:00")),
        close_time=time.fromisoformat(env("CLOSE_TIME", "19:00")),
        slot_step_min=int(env("SLOT_STEP_MIN", "30")),
        days_ahead=int(env("DAYS_AHEAD", "7")),
        closed_weekdays=_ids(env("CLOSED_WEEKDAYS", "6")),
        min_lead_min=int(env("MIN_LEAD_MIN", "30")),
    )
    values.update(overrides)
    return Config(**values)
