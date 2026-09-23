from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Depends, Request

from .database import connect
from .recommendation import SNAPSHOT_DATE, career_payload, hr_summary, recommend
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


@router.post("/employees/{employee_id}/events/{event_id}/complete")
def complete_event(employee_id: str, event_id: str, session: Session = Depends(current_session)) -> dict:
    employee_access(session, employee_id, write=True)
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if not connection.execute("SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Employee not found")
        if not connection.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        existing = connection.execute(
            "SELECT 1 FROM activity_records WHERE employee_id = ? AND event_id = ? AND status = 'completed'",
            (employee_id, event_id),
        ).fetchone()
        if not existing:
            employee = connection.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
            career = career_payload(connection, employee_id)
            eligible = recommend(connection, employee, career['target'], career['gaps'], limit=None)
            if event_id not in {r['event_id'] for r in eligible}:
                raise HTTPException(409, 'Активность больше не доступна или не соответствует требованиям')
            connection.execute(
                "INSERT INTO activity_records VALUES (?, ?, ?, ?, NULL, 'completed', 100, NULL, NULL, 'career_quest')",
                (f"CQ_{uuid.uuid4().hex[:12]}", employee_id, event_id, SNAPSHOT_DATE),
            )
        payload = career_payload(connection, employee_id)
    return {"completed": True, "already_completed": bool(existing), "career": payload}


@router.get("/hr/summary")
def summary(session: Session = Depends(current_session)) -> dict:
    require_hr(session)
    with connect() as connection:
        return hr_summary(connection, session.department)
