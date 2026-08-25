"""Общая бизнес-логика: и Discord-бот, и веб-панель дергают эти функции,
чтобы правила (например, подсчёт баллов или порядок варнов) не расходились
в двух реализациях.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.models import (
    DailyNorm,
    Event,
    EventAttendance,
    Member,
    PointSetting,
    Position,
    ReportItem,
    Warning,
    WarningLevel,
    WeeklyReport,
)


# ---------- Состав (Roster) ----------

async def list_members(session: AsyncSession, active_only: bool = True) -> list[Member]:
    q = select(Member)
    if active_only:
        q = q.where(Member.active.is_(True))
    q = q.order_by(Member.position, Member.last_name)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_member(session: AsyncSession, member_id: int) -> Member | None:
    return await session.get(Member, member_id)


async def get_member_by_static(session: AsyncSession, static_id: str) -> Member | None:
    result = await session.execute(select(Member).where(Member.static_id == static_id))
    return result.scalar_one_or_none()


async def get_member_by_discord_id(session: AsyncSession, discord_id: int) -> Member | None:
    result = await session.execute(select(Member).where(Member.discord_id == discord_id))
    return result.scalar_one_or_none()


async def add_member(
    session: AsyncSession,
    first_name: str,
    last_name: str,
    static_id: str,
    position: Position,
    discord_id: int | None = None,
) -> Member:
    member = Member(
        first_name=first_name,
        last_name=last_name,
        static_id=static_id,
        position=position,
        discord_id=discord_id,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member


async def update_member(session: AsyncSession, member_id: int, **fields) -> Member | None:
    member = await session.get(Member, member_id)
    if member is None:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(member, key):
            setattr(member, key, value)
    await session.commit()
    await session.refresh(member)
    return member


async def remove_member(session: AsyncSession, member_id: int, hard: bool = False) -> bool:
    member = await session.get(Member, member_id)
    if member is None:
        return False
    if hard:
        await session.delete(member)
    else:
        member.active = False
    await session.commit()
    return True


# ---------- Настройки баллов ----------

async def list_point_settings(session: AsyncSession, active_only: bool = True) -> list[PointSetting]:
    q = select(PointSetting)
    if active_only:
        q = q.where(PointSetting.active.is_(True))
    result = await session.execute(q.order_by(PointSetting.title))
    return list(result.scalars().all())


async def add_point_setting(session: AsyncSession, title: str, points: int) -> PointSetting:
    setting = PointSetting(title=title, points=points)
    session.add(setting)
    await session.commit()
    await session.refresh(setting)
    return setting


async def update_point_setting(session: AsyncSession, setting_id: int, **fields) -> PointSetting | None:
    setting = await session.get(PointSetting, setting_id)
    if setting is None:
        return None
    for key, value in fields.items():
        if value is not None and hasattr(setting, key):
            setattr(setting, key, value)
    await session.commit()
    await session.refresh(setting)
    return setting


async def remove_point_setting(session: AsyncSession, setting_id: int) -> bool:
    setting = await session.get(PointSetting, setting_id)
    if setting is None:
        return False
    setting.active = False
    await session.commit()
    return True


# ---------- Еженедельные отчёты ----------

def week_start_for(date: dt.date) -> dt.date:
    """Возвращает понедельник недели, к которой относится дата."""
    return date - dt.timedelta(days=date.weekday())


async def submit_weekly_report(
    session: AsyncSession,
    member_id: int,
    items: list[tuple[int, int]],  # (point_setting_id, quantity)
    content: str = "",
    week_start: dt.date | None = None,
) -> WeeklyReport:
    week_start = week_start or week_start_for(dt.date.today())

    existing = await session.execute(
        select(WeeklyReport).where(
            WeeklyReport.member_id == member_id, WeeklyReport.week_start == week_start
        )
    )
    report = existing.scalar_one_or_none()
    if report is not None:
        await session.execute(delete(ReportItem).where(ReportItem.report_id == report.id))
        report.content = content
        report.submitted_at = dt.datetime.utcnow()
    else:
        report = WeeklyReport(member_id=member_id, week_start=week_start, content=content)
        session.add(report)
        await session.flush()

    for point_setting_id, quantity in items:
        setting = await session.get(PointSetting, point_setting_id)
        if setting is None:
            continue
        session.add(
            ReportItem(
                report_id=report.id,
                point_setting_id=point_setting_id,
                quantity=quantity,
                points_at_submission=setting.points,
            )
        )

    await session.commit()
    result = await session.execute(
        select(WeeklyReport)
        .options(selectinload(WeeklyReport.items).selectinload(ReportItem.point_setting))
        .where(WeeklyReport.id == report.id)
    )
    return result.scalar_one()


async def list_reports_for_week(session: AsyncSession, week_start: dt.date) -> list[WeeklyReport]:
    result = await session.execute(
        select(WeeklyReport)
        .options(
            selectinload(WeeklyReport.items).selectinload(ReportItem.point_setting),
            selectinload(WeeklyReport.member),
        )
        .where(WeeklyReport.week_start == week_start)
    )
    return list(result.scalars().all())


async def weekly_summary(session: AsyncSession, week_start: dt.date) -> list[dict]:
    """Сводка активности за неделю: кто сдал отчёт, кто нет, сколько баллов."""
    members = await list_members(session)
    reports = await list_reports_for_week(session, week_start)
    reports_by_member = {r.member_id: r for r in reports}

    summary = []
    for m in members:
        r = reports_by_member.get(m.id)
        summary.append(
            {
                "member_id": m.id,
                "member_name": m.full_name,
                "static_id": m.static_id,
                "position": m.position.value,
                "submitted": r is not None,
                "points": r.total_points if r else 0,
                "submitted_at": r.submitted_at.isoformat() if r else None,
            }
        )
    return summary


# ---------- Выговоры ----------

async def issue_warning(
    session: AsyncSession, member_id: int, level: WarningLevel, reason: str, issued_by: str
) -> Warning:
    warning = Warning(member_id=member_id, level=level, reason=reason, issued_by=issued_by)
    session.add(warning)
    await session.commit()
    await session.refresh(warning)
    return warning


async def list_warnings(session: AsyncSession, member_id: int | None = None) -> list[Warning]:
    q = select(Warning).options(selectinload(Warning.member)).order_by(Warning.issued_at.desc())
    if member_id is not None:
        q = q.where(Warning.member_id == member_id)
    result = await session.execute(q)
    return list(result.scalars().all())


async def remove_warning(session: AsyncSession, warning_id: int) -> bool:
    warning = await session.get(Warning, warning_id)
    if warning is None:
        return False
    await session.delete(warning)
    await session.commit()
    return True


# ---------- Дневная норма ----------

async def set_daily_norm(
    session: AsyncSession,
    member_id: int,
    date: dt.date,
    hall_hour_done: bool | None = None,
    gov_wave_done: bool | None = None,
    note: str | None = None,
) -> DailyNorm:
    result = await session.execute(
        select(DailyNorm).where(DailyNorm.member_id == member_id, DailyNorm.date == date)
    )
    norm = result.scalar_one_or_none()
    if norm is None:
        norm = DailyNorm(member_id=member_id, date=date)
        session.add(norm)
    if hall_hour_done is not None:
        norm.hall_hour_done = hall_hour_done
    if gov_wave_done is not None:
        norm.gov_wave_done = gov_wave_done
    if note is not None:
        norm.note = note
    await session.commit()
    await session.refresh(norm)
    return norm


async def norms_table(session: AsyncSession, start: dt.date, end: dt.date) -> dict:
    """Возвращает таблицу норм: {member: {date: DailyNorm}} за диапазон дат."""
    members = await list_members(session)
    result = await session.execute(
        select(DailyNorm).where(DailyNorm.date >= start, DailyNorm.date <= end)
    )
    norms = list(result.scalars().all())
    by_member: dict[int, dict[str, DailyNorm]] = {}
    for n in norms:
        by_member.setdefault(n.member_id, {})[n.date.isoformat()] = n

    table = []
    day = start
    days = []
    while day <= end:
        days.append(day.isoformat())
        day += dt.timedelta(days=1)

    for m in members:
        row = {"member_id": m.id, "member_name": m.full_name, "static_id": m.static_id, "days": {}}
        for d in days:
            n = by_member.get(m.id, {}).get(d)
            row["days"][d] = {
                "hall_hour_done": n.hall_hour_done if n else False,
                "gov_wave_done": n.gov_wave_done if n else False,
                "completed": n.completed if n else False,
            }
        table.append(row)

    return {"days": days, "rows": table}


# ---------- События / собрания ----------

async def create_event(
    session: AsyncSession,
    title: str,
    event_datetime: dt.datetime,
    description: str = "",
    created_by: str = "",
    invite_all_active: bool = True,
) -> Event:
    event = Event(title=title, description=description, event_datetime=event_datetime, created_by=created_by)
    session.add(event)
    await session.flush()

    if invite_all_active:
        members = await list_members(session)
        for m in members:
            session.add(EventAttendance(event_id=event.id, member_id=m.id, present=None))

    await session.commit()
    await session.refresh(event)
    return event


async def list_events(session: AsyncSession, upcoming_only: bool = False) -> list[Event]:
    q = select(Event).order_by(Event.event_datetime.desc())
    if upcoming_only:
        q = q.where(Event.event_datetime >= dt.datetime.utcnow())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_event(session: AsyncSession, event_id: int) -> Event | None:
    result = await session.execute(
        select(Event)
        .options(selectinload(Event.attendances).selectinload(EventAttendance.member))
        .where(Event.id == event_id)
    )
    return result.scalar_one_or_none()


async def mark_attendance(session: AsyncSession, event_id: int, member_id: int, present: bool) -> EventAttendance:
    result = await session.execute(
        select(EventAttendance).where(
            EventAttendance.event_id == event_id, EventAttendance.member_id == member_id
        )
    )
    att = result.scalar_one_or_none()
    if att is None:
        att = EventAttendance(event_id=event_id, member_id=member_id, present=present)
        session.add(att)
    else:
        att.present = present
    await session.commit()
    await session.refresh(att)
    return att
