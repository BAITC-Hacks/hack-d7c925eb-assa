from __future__ import annotations

import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ConfigDict

from .config import demo_mode
from .database import connect


@dataclass
class Session:
    employee_id: str
    role: str
    department: str
    expires: float
    max_minutes: int | None = None
    event_format: str | None = None
    requests: list[float] = field(default_factory=list)
    busy: bool = False
    conversation_id: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    turns: list[dict] = field(default_factory=list)
    selected_events: list[str] = field(default_factory=list)
    last_kind: str | None = None


SESSIONS: dict[str, Session] = {}
bearer = HTTPBearer(auto_error=False)


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['employee', 'hr'] = 'employee'
    employee_id: str = Field(default='E0001', pattern=r'^E\d{4,8}$')
    access_code: str = Field(default='', max_length=256)


def require_local(request: Request) -> None:
    if not demo_mode() or not request.client or request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        raise HTTPException(403, 'Деморежим доступен только на локальном компьютере')
    if request.url.hostname not in {'localhost', '127.0.0.1', '::1', 'testserver'}:
        raise HTTPException(403, 'Недопустимый адрес демосервера')
    origin = request.headers.get('origin')
    if origin and (urlparse(origin).hostname not in {'localhost', '127.0.0.1', '::1'} or urlparse(origin).scheme not in {'http', 'https'}):
        raise HTTPException(403, 'Недопустимый источник запроса')


def create_session(data: Login, request: Request) -> dict:
    if demo_mode():
        require_local(request)
        employee_id = data.employee_id
    else:
        expected = os.getenv('CQ_HR_ACCESS_CODE' if data.role == 'hr' else 'CQ_EMPLOYEE_ACCESS_CODE', '')
        if len(expected) < 16 or not hmac.compare_digest(data.access_code, expected):
            raise HTTPException(401, 'Неверный код доступа')
        employee_id = os.getenv('CQ_EMPLOYEE_ID', 'E0001')
    with connect() as db:
        employee = db.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
    if not employee:
        raise HTTPException(404, 'Профиль не найден')
    department = employee['department'] if demo_mode() else os.getenv('CQ_HR_DEPARTMENT', employee['department'])
    now = time.time()
    for token, session in list(SESSIONS.items()):
        if session.expires < now:
            SESSIONS.pop(token, None)
    if len(SESSIONS) >= 256:
        raise HTTPException(429, 'Слишком много активных сессий')
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = Session(employee_id, data.role, department, now + 8 * 3600)
    return {'token': token, 'employee_id': employee_id, 'role': data.role, 'department': department, 'demo': demo_mode()}


def current_session(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Session:
    session = SESSIONS.get(credentials.credentials) if credentials else None
    if not session or session.expires < time.time():
        raise HTTPException(401, 'Сессия истекла. Войдите снова.')
    if demo_mode():
        require_local(request)
    return session


def employee_access(session: Session, employee_id: str, *, write: bool = False) -> None:
    if employee_id == session.employee_id:
        return
    if session.role == 'hr' and not write:
        with connect() as db:
            row = db.execute('SELECT department FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
        if row and row['department'] == session.department:
            return
    raise HTTPException(403, 'Нет доступа к этому профилю')


def require_hr(session: Session) -> None:
    if session.role != 'hr':
        raise HTTPException(403, 'Раздел доступен только HR')
