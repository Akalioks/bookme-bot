"""Database tables. SQLite by default, PostgreSQL works by changing DATABASE_URL."""
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # Telegram user id
    full_name: Mapped[str] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    phone: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime]


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    emoji: Mapped[str] = mapped_column(String(8), default="")
    duration_min: Mapped[int]
    price: Mapped[int]  # whole euros
    active: Mapped[bool] = mapped_column(default=True)


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(default=True)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    master_id: Mapped[int] = mapped_column(ForeignKey("masters.id"), index=True)
    start: Mapped[datetime] = mapped_column(index=True)
    end: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | cancelled
    created_at: Mapped[datetime]
    reminded_24h: Mapped[bool] = mapped_column(default=False)
    reminded_2h: Mapped[bool] = mapped_column(default=False)

    user: Mapped[User] = relationship(lazy="joined")
    service: Mapped[Service] = relationship(lazy="joined")
    master: Mapped[Master] = relationship(lazy="joined")


class WebLogin(Base):
    """Logins to the web admin panel, confirmed in Telegram.
    The panel creates a 'pending' row and shows a t.me link; the bot asks the person and marks it approved."""
    __tablename__ = "web_logins"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[int]  # unix seconds
    browser: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | denied | used
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))
    username: Mapped[str | None] = mapped_column(String(64))
