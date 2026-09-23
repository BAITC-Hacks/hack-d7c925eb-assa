from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from .database import connect
from .recommendation import SNAPSHOT_DATE, career_payload, hr_summary


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    with connect() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok", "database": "connected"}


@router.get("/employees")
def employees() -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT employee_id, full_name, department, role, grade FROM employees ORDER BY full_name"
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/employees/{employee_id}/career")
def career(employee_id: str) -> dict:
    with connect() as connection:
        payload = career_payload(connection, employee_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Employee not found")
    return payload


@router.post("/employees/{employee_id}/events/{event_id}/complete")
def complete_event(employee_id: str, event_id: str) -> dict:
    with connect() as connection:
        if not connection.execute("SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Employee not found")
        if not connection.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Event not found")
        existing = connection.execute(
            "SELECT 1 FROM activity_records WHERE employee_id = ? AND event_id = ? AND status = 'completed'",
            (employee_id, event_id),
        ).fetchone()
        if not existing:
            connection.execute(
                "INSERT INTO activity_records VALUES (?, ?, ?, ?, NULL, 'completed', 100, NULL, NULL, 'career_quest')",
                (f"CQ_{uuid.uuid4().hex[:12]}", employee_id, event_id, SNAPSHOT_DATE),
            )
        payload = career_payload(connection, employee_id)
    return {"completed": True, "already_completed": bool(existing), "career": payload}


@router.get("/hr/summary")
def summary() -> dict:
    with connect() as connection:
        return hr_summary(connection)
