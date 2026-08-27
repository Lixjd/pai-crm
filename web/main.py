"""Веб-панель отдела PAI: REST API + отдача статичного дашборда.
Запуск: python -m web.main (из корня проекта)
"""
from __future__ import annotations

import datetime as dt
import itsdangerous
import os
from pathlib import Path
import datetime as dt
import itsdangerous
from pathlib import Path
from typing import Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import crud
from core.config import WEB_ADMIN_PASSWORD, WEB_SECRET_KEY
from core.database import get_session, init_db
from core.models import Position, WarningLevel

app = FastAPI(title="PAI CRM API")
signer = itsdangerous.TimestampSigner(WEB_SECRET_KEY)
STATIC_DIR = Path(__file__).parent / "static"

SESSION_MAX_AGE = 60 * 60 * 12  # 12 часов


# ---------- Авторизация (простая, по одному общему паролю) ----------

class LoginBody(BaseModel):
    password: str


def require_auth(pai_session: Optional[str] = Cookie(default=None)):
    if not pai_session:
        raise HTTPException(status_code=401, detail="Не авторизован")
    try:
        signer.unsign(pai_session, max_age=SESSION_MAX_AGE)
    except itsdangerous.BadSignature:
        raise HTTPException(status_code=401, detail="Сессия истекла, войдите заново")
    return True


@app.post("/api/login")
async def login(body: LoginBody, response: Response):
    if body.password != WEB_ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Неверный пароль")
    token = signer.sign(b"ok").decode()
    response.set_cookie("pai_session", token, httponly=True, max_age=SESSION_MAX_AGE, samesite="lax")
    return {"ok": True}


@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("pai_session")
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    await init_db()


# ---------- Сериализация ----------

def member_to_dict(m) -> dict:
    return {
        "id": m.id,
        "first_name": m.first_name,
        "last_name": m.last_name,
        "full_name": m.full_name,
        "static_id": m.static_id,
        "position": m.position.value,
        "position_key": m.position.name,
        "discord_id": m.discord_id,
        "active": m.active,
    }


def setting_to_dict(s) -> dict:
    return {"id": s.id, "title": s.title, "points": s.points, "active": s.active}


def report_to_dict(r) -> dict:
    return {
        "id": r.id,
        "member_id": r.member_id,
        "member_name": r.member.full_name if r.member else None,
        "week_start": r.week_start.isoformat(),
        "content": r.content,
        "submitted_at": r.submitted_at.isoformat(),
        "total_points": r.total_points,
        "items": [
            {
                "title": i.point_setting.title if i.point_setting else "?",
                "quantity": i.quantity,
                "points_at_submission": i.points_at_submission,
            }
            for i in r.items
        ],
    }


def warning_to_dict(w) -> dict:
    return {
        "id": w.id,
        "member_id": w.member_id,
        "member_name": w.member.full_name if w.member else None,
        "level": w.level.value,
        "reason": w.reason,
        "issued_by": w.issued_by,
        "issued_at": w.issued_at.isoformat(),
    }


def event_to_dict(e, with_attendance: bool = False) -> dict:
    data = {
        "id": e.id,
        "title": e.title,
        "description": e.description,
        "event_datetime": e.event_datetime.isoformat(),
        "created_by": e.created_by,
    }
    if with_attendance:
        data["attendance"] = [
            {
                "member_id": a.member_id,
                "member_name": a.member.full_name if a.member else None,
                "present": a.present,
            }
            for a in e.attendances
        ]
    return data


# ---------- Справочники ----------

@app.get("/api/positions", dependencies=[Depends(require_auth)])
async def positions():
    return [{"key": p.name, "label": p.value} for p in Position]


@app.get("/api/warning-levels", dependencies=[Depends(require_auth)])
async def warning_levels():
    return [{"key": w.name, "label": w.value} for w in WarningLevel]


# ---------- Состав ----------

class MemberBody(BaseModel):
    first_name: str
    last_name: str
    static_id: str
    position: str
    discord_id: Optional[int] = None


class MemberUpdateBody(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    static_id: Optional[str] = None
    position: Optional[str] = None
    discord_id: Optional[int] = None


@app.get("/api/members", dependencies=[Depends(require_auth)])
async def api_list_members(active_only: bool = True):
    async with get_session() as session:
        members = await crud.list_members(session, active_only=active_only)
        return [member_to_dict(m) for m in members]


@app.post("/api/members", dependencies=[Depends(require_auth)])
async def api_add_member(body: MemberBody):
    async with get_session() as session:
        existing = await crud.get_member_by_static(session, body.static_id)
        if existing:
            raise HTTPException(status_code=400, detail="Сотрудник с таким static ID уже есть")
        try:
            position = Position[body.position]
        except KeyError:
            raise HTTPException(status_code=400, detail="Неизвестная должность")
        member = await crud.add_member(
            session, body.first_name, body.last_name, body.static_id, position, body.discord_id
        )
        return member_to_dict(member)


@app.put("/api/members/{member_id}", dependencies=[Depends(require_auth)])
async def api_update_member(member_id: int, body: MemberUpdateBody):
    position = Position[body.position] if body.position else None
    async with get_session() as session:
        member = await crud.update_member(
            session,
            member_id,
            first_name=body.first_name,
            last_name=body.last_name,
            static_id=body.static_id,
            position=position,
            discord_id=body.discord_id,
        )
        if member is None:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        return member_to_dict(member)


@app.delete("/api/members/{member_id}", dependencies=[Depends(require_auth)])
async def api_remove_member(member_id: int, hard: bool = False):
    async with get_session() as session:
        ok = await crud.remove_member(session, member_id, hard=hard)
        if not ok:
            raise HTTPException(status_code=404, detail="Сотрудник не найден")
        return {"ok": True}


# ---------- Настройки баллов ----------

class PointSettingBody(BaseModel):
    title: str
    points: int


class PointSettingUpdateBody(BaseModel):
    title: Optional[str] = None
    points: Optional[int] = None


@app.get("/api/point-settings", dependencies=[Depends(require_auth)])
async def api_list_point_settings(active_only: bool = True):
    async with get_session() as session:
        settings = await crud.list_point_settings(session, active_only=active_only)
        return [setting_to_dict(s) for s in settings]


@app.post("/api/point-settings", dependencies=[Depends(require_auth)])
async def api_add_point_setting(body: PointSettingBody):
    async with get_session() as session:
        setting = await crud.add_point_setting(session, body.title, body.points)
        return setting_to_dict(setting)


@app.put("/api/point-settings/{setting_id}", dependencies=[Depends(require_auth)])
async def api_update_point_setting(setting_id: int, body: PointSettingUpdateBody):
    async with get_session() as session:
        setting = await crud.update_point_setting(session, setting_id, title=body.title, points=body.points)
        if setting is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        return setting_to_dict(setting)


@app.delete("/api/point-settings/{setting_id}", dependencies=[Depends(require_auth)])
async def api_remove_point_setting(setting_id: int):
    async with get_session() as session:
        ok = await crud.remove_point_setting(session, setting_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Не найдено")
        return {"ok": True}


# ---------- Еженедельные отчёты ----------

class ReportItemBody(BaseModel):
    point_setting_id: int
    quantity: int = 1


class ReportBody(BaseModel):
    member_id: int
    content: str = ""
    week_start: Optional[dt.date] = None
    items: list[ReportItemBody] = []


@app.get("/api/reports", dependencies=[Depends(require_auth)])
async def api_list_reports(week_start: dt.date):
    async with get_session() as session:
        reports = await crud.list_reports_for_week(session, week_start)
        return [report_to_dict(r) for r in reports]


@app.post("/api/reports", dependencies=[Depends(require_auth)])
async def api_submit_report(body: ReportBody):
    async with get_session() as session:
        report = await crud.submit_weekly_report(
            session,
            body.member_id,
            [(i.point_setting_id, i.quantity) for i in body.items],
            content=body.content,
            week_start=body.week_start,
        )
        return report_to_dict(report)


@app.get("/api/reports/summary", dependencies=[Depends(require_auth)])
async def api_report_summary(week_start: dt.date):
    async with get_session() as session:
        return await crud.weekly_summary(session, week_start)


# ---------- Выговоры ----------

class WarningBody(BaseModel):
    member_id: int
    level: str
    reason: str
    issued_by: str = "Веб-панель"


@app.get("/api/warnings", dependencies=[Depends(require_auth)])
async def api_list_warnings(member_id: Optional[int] = None):
    async with get_session() as session:
        warnings = await crud.list_warnings(session, member_id)
        return [warning_to_dict(w) for w in warnings]


@app.post("/api/warnings", dependencies=[Depends(require_auth)])
async def api_issue_warning(body: WarningBody):
    try:
        level = WarningLevel[body.level]
    except KeyError:
        raise HTTPException(status_code=400, detail="Неизвестный уровень выговора")
    async with get_session() as session:
        warning = await crud.issue_warning(session, body.member_id, level, body.reason, body.issued_by)
        warnings = await crud.list_warnings(session, body.member_id)
        return {**warning_to_dict(warning), "member_total_warnings": len(warnings)}


@app.delete("/api/warnings/{warning_id}", dependencies=[Depends(require_auth)])
async def api_remove_warning(warning_id: int):
    async with get_session() as session:
        ok = await crud.remove_warning(session, warning_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Не найдено")
        return {"ok": True}


# ---------- Дневная норма ----------

class NormBody(BaseModel):
    member_id: int
    date: dt.date
    hall_hour_done: Optional[bool] = None
    gov_wave_done: Optional[bool] = None
    note: Optional[str] = None


@app.get("/api/norms", dependencies=[Depends(require_auth)])
async def api_norms_table(start: dt.date, end: dt.date):
    async with get_session() as session:
        return await crud.norms_table(session, start, end)


@app.post("/api/norms", dependencies=[Depends(require_auth)])
async def api_set_norm(body: NormBody):
    async with get_session() as session:
        norm = await crud.set_daily_norm(
            session, body.member_id, body.date, body.hall_hour_done, body.gov_wave_done, body.note
        )
        return {
            "member_id": norm.member_id,
            "date": norm.date.isoformat(),
            "hall_hour_done": norm.hall_hour_done,
            "gov_wave_done": norm.gov_wave_done,
            "completed": norm.completed,
            "note": norm.note,
        }


# ---------- События ----------

class EventBody(BaseModel):
    title: str
    description: str = ""
    event_datetime: dt.datetime
    created_by: str = "Веб-панель"
    invite_all_active: bool = True


class AttendanceBody(BaseModel):
    member_id: int
    present: bool


@app.get("/api/events", dependencies=[Depends(require_auth)])
async def api_list_events(upcoming_only: bool = False):
    async with get_session() as session:
        events = await crud.list_events(session, upcoming_only=upcoming_only)
        return [event_to_dict(e) for e in events]


@app.post("/api/events", dependencies=[Depends(require_auth)])
async def api_create_event(body: EventBody):
    async with get_session() as session:
        event = await crud.create_event(
            session, body.title, body.event_datetime, body.description, body.created_by, body.invite_all_active
        )
        full = await crud.get_event(session, event.id)
        return event_to_dict(full, with_attendance=True)


@app.get("/api/events/{event_id}", dependencies=[Depends(require_auth)])
async def api_get_event(event_id: int):
    async with get_session() as session:
        event = await crud.get_event(session, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Событие не найдено")
        return event_to_dict(event, with_attendance=True)


@app.post("/api/events/{event_id}/attendance", dependencies=[Depends(require_auth)])
async def api_mark_attendance(event_id: int, body: AttendanceBody):
    async with get_session() as session:
        await crud.mark_attendance(session, event_id, body.member_id, body.present)
        event = await crud.get_event(session, event_id)
        return event_to_dict(event, with_attendance=True)


# ---------- Статика (дашборд) ----------

app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return FileResponse(str(STATIC_DIR / "index.html"))
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn

    from core.config import WEB_HOST, WEB_PORT

    # reload=True удобен только при локальной разработке. На хостинге (Railway и т.п.)
    # он следит за изменениями файлов и может уйти в цикл перезапуска, когда
    # рядом создаётся/меняется файл базы данных pai_crm.db — поэтому включаем его
    # только если явно попросили через переменную окружения DEV_RELOAD=1.
    dev_reload = os.getenv("DEV_RELOAD", "0") == "1"
    uvicorn.run("web.main:app", host=WEB_HOST, port=WEB_PORT, reload=dev_reload)
