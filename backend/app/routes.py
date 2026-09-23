from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from .database import connect
from .recommendation import SNAPSHOT_DATE, RECURRING_EVENT_ID, career_payload, hr_summary, recommend
from .auth import Session, Login, create_session, current_session, employee_access, require_hr, require_local, SESSIONS
from .config import demo_mode, external_enabled
from .assistant import AssistantRequest, run_assistant


router = APIRouter(prefix="/api/v1")


@router.get('/config')
def public_config(request: Request) -> dict:
    if demo_mode():
        require_local(request)
    return {'demo': demo_mode(), 'ai_enabled': external_enabled(), 'snapshot_date': SNAPSHOT_DATE}


@router.get('/demo/profiles')
def demo_profiles(request: Request) -> list[dict]:
    require_local(request)
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT employee_id, full_name, department, role, grade FROM employees ORDER BY full_name')]


@router.post('/session')
def login(data: Login, request: Request) -> dict:
    return create_session(data, request)


@router.delete('/session')
def logout(request: Request, session: Session = Depends(current_session)) -> dict:
    token = request.headers.get('authorization', '').removeprefix('Bearer ')
    SESSIONS.pop(token, None)
    return {'logged_out': True}


@router.get('/session')
def restore_session(session: Session = Depends(current_session)) -> dict:
    return {'employee_id': session.employee_id, 'role': session.role, 'department': session.department, 'demo': demo_mode()}


class Goal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: str = Field(max_length=100)
    grade: str = Field(max_length=50)


@router.get('/goals')
def goals(session: Session = Depends(current_session)) -> list[dict]:
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT DISTINCT role, grade FROM role_skill_requirements ORDER BY role, grade')]


@router.put('/employees/{employee_id}/goal')
def set_goal(employee_id: str, data: Goal, session: Session = Depends(current_session)) -> dict:
    employee_access(session, employee_id, write=True)
    with connect() as db:
        if not db.execute('SELECT 1 FROM role_skill_requirements WHERE role=? AND grade=?', (data.role, data.grade)).fetchone():
            raise HTTPException(422, 'Для этой цели нет требований')
        db.execute('INSERT INTO career_goals VALUES (?, ?, ?) ON CONFLICT(employee_id) DO UPDATE SET target_role=excluded.target_role, target_grade=excluded.target_grade', (employee_id, data.role, data.grade))
        return career_payload(db, employee_id)


@router.post('/assistant')
async def assistant(data: AssistantRequest, session: Session = Depends(current_session)) -> dict:
    return await run_assistant(data, session)


@router.get("/health")
def health() -> dict[str, str]:
    with connect() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok", "database": "connected"}


@router.get("/employees")
def employees(session: Session = Depends(current_session)) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT employee_id, full_name, department, role, grade FROM employees WHERE employee_id=? OR (?='hr' AND department=?) ORDER BY full_name",
            (session.employee_id, session.role, session.department),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/employees/{employee_id}/career")
def career(employee_id: str, session: Session = Depends(current_session)) -> dict:
    employee_access(session, employee_id)
    with connect() as connection:
        payload = career_payload(connection, employee_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Employee not found")
    return payload


class Completion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    participation_id: str | None = Field(default=None, max_length=100)


@router.post("/employees/{employee_id}/events/{event_id}/complete")
def complete_event(employee_id: str, event_id: str, data: Completion = Completion(), session: Session = Depends(current_session)) -> dict:
    employee_access(session, employee_id, write=True)
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if not connection.execute("SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Employee not found")
        if not connection.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        date = SNAPSHOT_DATE
        if event_id == RECURRING_EVENT_ID:
            if not data.participation_id or not data.participation_id.startswith(event_id + ':'):
                raise HTTPException(422, 'Выберите конкретную сессию клуба')
            date = data.participation_id.split(':', 1)[1]
            if not connection.execute('SELECT 1 FROM event_sessions WHERE event_id=? AND session_date=? AND session_date>=?', (event_id, date, SNAPSHOT_DATE)).fetchone():
                raise HTTPException(409, 'Сессия отсутствует или недоступна')
        existing = connection.execute(
            "SELECT 1 FROM activity_records WHERE employee_id = ? AND event_id = ? AND status = 'completed' AND (? != ? OR date=?)",
            (employee_id, event_id, event_id, RECURRING_EVENT_ID, date),
        ).fetchone()
        if not existing:
            employee = connection.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
            career = career_payload(connection, employee_id)
            eligible = recommend(connection, employee, career['target'], career['gaps'], limit=None)
            if event_id not in {r['event_id'] for r in eligible}:
                raise HTTPException(409, 'Активность больше не доступна или не соответствует требованиям')
            selected = next(r for r in eligible if r['event_id'] == event_id)
            if event_id == RECURRING_EVENT_ID and selected['participation_id'] != data.participation_id:
                raise HTTPException(409, 'Обновите карточку: доступна другая сессия')
            connection.execute(
                "INSERT INTO activity_records VALUES (?, ?, ?, ?, NULL, 'completed', 100, NULL, NULL, 'career_quest')",
                (f"CQ_{uuid.uuid4().hex[:12]}", employee_id, event_id, date),
            )
        payload = career_payload(connection, employee_id)
        game = payload['gamification']
        previous = career['gamification'] if not existing else game
        reward = {
            'xp': max(0, game['total_xp'] - previous['total_xp']),
            'level_up': game['level'] > previous['level'],
            'level_title': game['level_title'],
            'badges': [badge['title'] for badge in game['badges'] if badge['unlocked']
                       and not any(old['id'] == badge['id'] and old['unlocked'] for old in previous['badges'])],
        }
    return {"completed": True, "already_completed": bool(existing), "career": payload, "reward": reward}


@router.get("/hr/summary")
def summary(session: Session = Depends(current_session)) -> dict:
    require_hr(session)
    with connect() as connection:
        return hr_summary(connection, session.department)
