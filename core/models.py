"""Модели базы данных отдела PAI.

Одна и та же база используется и Discord-ботом, и веб-панелью,
поэтому вся структура данных живёт в одном месте.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Position(str, enum.Enum):
    """Должности состава PAI, в порядке иерархии (сверху вниз)."""
    ADVISOR_CHIEF = "Advisor Chief"
    ASSISTANT_CHIEF = "Assistant Chief"
    CURATOR = "Curator of Department"
    HEAD = "Head of Department"
    DEPUTY_HEAD = "Deputy Head of Department"
    INSTRUCTOR = "Instructor of Department"


class WarningLevel(str, enum.Enum):
    WARN_1 = "1 варн"
    WARN_2 = "2 варна"
    DEMOTION = "Понижение"


class Member(Base):
    """Сотрудник отдела."""
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    static_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    position: Mapped[Position] = mapped_column(Enum(Position))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    reports: Mapped[list["WeeklyReport"]] = relationship(back_populates="member", cascade="all, delete-orphan")
    warnings: Mapped[list["Warning"]] = relationship(back_populates="member", cascade="all, delete-orphan")
    norms: Mapped[list["DailyNorm"]] = relationship(back_populates="member", cascade="all, delete-orphan")
    attendances: Mapped[list["EventAttendance"]] = relationship(back_populates="member", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class PointSetting(Base):
    """Настраиваемый вид работы и количество баллов за него
    (например: 'Патруль' -> 5 баллов). Управляется через настройки."""
    __tablename__ = "point_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), unique=True)
    points: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WeeklyReport(Base):
    """Еженедельный отчёт сотрудника."""
    __tablename__ = "weekly_reports"
    __table_args__ = (UniqueConstraint("member_id", "week_start", name="uq_member_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    week_start: Mapped[dt.date] = mapped_column(Date)  # понедельник недели, за которую отчёт
    content: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    member: Mapped[Member] = relationship(back_populates="reports")
    items: Mapped[list["ReportItem"]] = relationship(back_populates="report", cascade="all, delete-orphan")

    @property
    def total_points(self) -> int:
        return sum(i.quantity * i.points_at_submission for i in self.items)


class ReportItem(Base):
    """Конкретная выполненная работа внутри отчёта (название работы + кол-во раз)."""
    __tablename__ = "report_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("weekly_reports.id"))
    point_setting_id: Mapped[int] = mapped_column(ForeignKey("point_settings.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    # баллы за единицу на момент подачи отчёта (чтобы правки настроек в будущем
    # не меняли задним числом уже посчитанные отчёты)
    points_at_submission: Mapped[int] = mapped_column(Integer)

    report: Mapped[WeeklyReport] = relationship(back_populates="items")
    point_setting: Mapped[PointSetting] = relationship()


class Warning(Base):
    """Выговор/варн сотруднику."""
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    level: Mapped[WarningLevel] = mapped_column(Enum(WarningLevel))
    reason: Mapped[str] = mapped_column(Text)
    issued_by: Mapped[str] = mapped_column(String(128))
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    member: Mapped[Member] = relationship(back_populates="warnings")


class DailyNorm(Base):
    """Выполнение дневной нормы: 1 час в холле + 1 гос. волна."""
    __tablename__ = "daily_norms"
    __table_args__ = (UniqueConstraint("member_id", "date", name="uq_member_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    date: Mapped[dt.date] = mapped_column(Date)
    hall_hour_done: Mapped[bool] = mapped_column(Boolean, default=False)
    gov_wave_done: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(256), default="")

    member: Mapped[Member] = relationship(back_populates="norms")

    @property
    def completed(self) -> bool:
        return self.hall_hour_done and self.gov_wave_done


class Event(Base):
    """Событие/собрание отдела."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    event_datetime: Mapped[dt.datetime] = mapped_column(DateTime)
    created_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    attendances: Mapped[list["EventAttendance"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class EventAttendance(Base):
    """Отметка присутствия конкретного сотрудника на событии."""
    __tablename__ = "event_attendance"
    __table_args__ = (UniqueConstraint("event_id", "member_id", name="uq_event_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    present: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = ещё не отмечен

    event: Mapped[Event] = relationship(back_populates="attendances")
    member: Mapped[Member] = relationship(back_populates="attendances")
