from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "career_quest_dataset"
DB_PATH = ROOT / "backend" / "data" / "career_quest.db"


SCHEMA = """
PRAGMA foreign_keys = OFF;
DROP TABLE IF EXISTS activity_records;
DROP TABLE IF EXISTS event_sessions;
DROP TABLE IF EXISTS event_prerequisites;
DROP TABLE IF EXISTS event_skill_gains;
DROP TABLE IF EXISTS event_targets;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS role_skill_requirements;
DROP TABLE IF EXISTS employee_skills;
DROP TABLE IF EXISTS career_goals;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS skills;

CREATE TABLE employees (
  employee_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, department TEXT NOT NULL,
  role TEXT NOT NULL, grade TEXT NOT NULL, manager_id TEXT, tenure_months INTEGER,
  work_format TEXT, preferred_language TEXT, last_review_date TEXT
);
CREATE TABLE career_goals (
  employee_id TEXT PRIMARY KEY, target_role TEXT NOT NULL, target_grade TEXT NOT NULL,
  FOREIGN KEY(employee_id) REFERENCES employees(employee_id)
);
CREATE TABLE skills (
  skill_id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
  category TEXT NOT NULL, description TEXT NOT NULL
);
CREATE TABLE employee_skills (
  employee_id TEXT NOT NULL, skill_id TEXT NOT NULL, level INTEGER NOT NULL,
  PRIMARY KEY(employee_id, skill_id)
);
CREATE TABLE role_skill_requirements (
  role TEXT NOT NULL, grade TEXT NOT NULL, skill_id TEXT NOT NULL,
  required_level INTEGER NOT NULL, is_critical INTEGER NOT NULL,
  PRIMARY KEY(role, grade, skill_id)
);
CREATE TABLE events (
  event_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
  type TEXT NOT NULL, format TEXT NOT NULL, duration_hours REAL NOT NULL,
  mandatory INTEGER NOT NULL
);
CREATE TABLE event_targets (
  event_id TEXT NOT NULL, role TEXT NOT NULL, grade TEXT NOT NULL,
  PRIMARY KEY(event_id, role, grade)
);
CREATE TABLE event_skill_gains (
  event_id TEXT NOT NULL, skill_id TEXT NOT NULL, gain REAL NOT NULL,
  max_level INTEGER NOT NULL, PRIMARY KEY(event_id, skill_id)
);
CREATE TABLE event_prerequisites (
  event_id TEXT NOT NULL, skill_id TEXT NOT NULL, required_level INTEGER NOT NULL,
  PRIMARY KEY(event_id, skill_id)
);
CREATE TABLE event_sessions (
  event_id TEXT NOT NULL, session_date TEXT NOT NULL,
  PRIMARY KEY(event_id, session_date)
);
CREATE TABLE activity_records (
  record_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, event_id TEXT NOT NULL,
  date TEXT NOT NULL, due_date TEXT, status TEXT NOT NULL,
  completion_pct INTEGER NOT NULL, score INTEGER, feedback_rating INTEGER,
  assigned_by TEXT NOT NULL
);
CREATE INDEX idx_activity_employee ON activity_records(employee_id, status);
CREATE INDEX idx_requirements_target ON role_skill_requirements(role, grade);
PRAGMA foreign_keys = ON;
"""


def load_json(name: str) -> dict:
    return json.loads((DATASET / name).read_text(encoding="utf-8"))


def optional_int(value: str) -> int | None:
    return int(value) if value else None


def import_dataset(*, reset: bool = False) -> dict[str, int]:
    if DB_PATH.exists() and not reset:
        raise ValueError('База уже существует. Для добавления используйте --append; для разрушительного сброса --reset.')
    skills_doc = load_json("skills.json")
    employees_doc = load_json("employees.json")
    events_doc = load_json("events.json")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT INTO skills VALUES (:skill_id, :name, :type, :category, :description)",
            skills_doc["skills"],
        )
        requirement_rows = []
        for profile in skills_doc["role_profiles"]:
            critical = set(profile["critical_skills"])
            requirement_rows.extend(
                (profile["role"], profile["grade"], skill_id, level, int(skill_id in critical))
                for skill_id, level in profile["required_skills"].items()
            )
        connection.executemany(
            "INSERT INTO role_skill_requirements VALUES (?, ?, ?, ?, ?)", requirement_rows
        )

        skill_rows = []
        goal_rows = []
        for employee in employees_doc["employees"]:
            connection.execute(
                "INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    employee["employee_id"], employee["full_name"], employee["department"],
                    employee["role"], employee["grade"], employee.get("manager_id"),
                    employee["tenure_months"], employee["work_format"],
                    employee["preferred_language"], employee["last_review_date"],
                ),
            )
            skill_rows.extend(
                (employee["employee_id"], skill_id, level)
                for skill_id, level in employee.get("skills", {}).items()
            )
            goal = employee.get("career_goal")
            if goal:
                goal_rows.append((employee["employee_id"], goal["target_role"], goal["target_grade"]))
        connection.executemany("INSERT INTO employee_skills VALUES (?, ?, ?)", skill_rows)
        connection.executemany("INSERT INTO career_goals VALUES (?, ?, ?)", goal_rows)

        target_rows, gain_rows, prerequisite_rows, session_rows = [], [], [], []
        for event in events_doc["events"]:
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event["event_id"], event["title"], event["description"], event["type"],
                    event["format"], event["duration_hours"], int(event["mandatory"]),
                ),
            )
            target_rows.extend(
                (event["event_id"], role, grade)
                for role in event["target_roles"] for grade in event["target_grades"]
            )
            gain_rows.extend(
                (event["event_id"], item["skill_id"], item["gain"], item["max_level"])
                for item in event["develops_skills"]
            )
            prerequisite_rows.extend(
                (event["event_id"], skill_id, level)
                for skill_id, level in event["prerequisites"].items()
            )
            session_rows.extend((event["event_id"], date) for date in event["upcoming_sessions"])
        connection.executemany("INSERT INTO event_targets VALUES (?, ?, ?)", target_rows)
        connection.executemany("INSERT INTO event_skill_gains VALUES (?, ?, ?, ?)", gain_rows)
        connection.executemany("INSERT INTO event_prerequisites VALUES (?, ?, ?)", prerequisite_rows)
        connection.executemany("INSERT INTO event_sessions VALUES (?, ?)", session_rows)

        with (DATASET / "activity_history.csv").open(encoding="utf-8", newline="") as handle:
            activity = list(csv.DictReader(handle))
        connection.executemany(
            "INSERT INTO activity_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    row["record_id"], row["employee_id"], row["event_id"], row["date"],
                    row["due_date"] or None, row["status"], int(row["completion_pct"]),
                    optional_int(row["score"]), optional_int(row["feedback_rating"]), row["assigned_by"],
                )
                for row in activity
            ],
        )

    connection.close()
    return {
        "skills": len(skills_doc["skills"]),
        "employees": len(employees_doc["employees"]),
        "events": len(events_doc["events"]),
        "activity_records": len(activity),
    }


def append_dataset(folder: Path) -> dict[str, int]:
    """Add profiles and history atomically. Existing profiles and progress are immutable here."""
    from datetime import date
    from contextlib import closing
    if not DB_PATH.is_file():
        raise ValueError('Сначала создайте базовый каталог обычным импортом')
    employees_path = folder / 'employees.json'
    history_path = folder / 'activity_history.csv'
    employees = json.loads(employees_path.read_text(encoding='utf-8-sig'))['employees'] if employees_path.exists() else []
    with history_path.open(encoding='utf-8-sig', newline='') if history_path.exists() else __import__('io').StringIO('') as f:
        history = list(csv.DictReader(f))
    if not employees_path.exists() and not history_path.exists():
        raise ValueError('Нужен employees.json или activity_history.csv')
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(isinstance(employees, list) and all(isinstance(e, dict) for e in employees), 'employees должен быть массивом объектов')
    errors = []
    counts = {'employees_added': 0, 'history_added': 0, 'duplicates': 0}
    with closing(sqlite3.connect(DB_PATH)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        skills = {r[0] for r in db.execute('SELECT skill_id FROM skills')}
        events = {r[0] for r in db.execute('SELECT event_id FROM events')}
        profiles = set(db.execute('SELECT DISTINCT role, grade FROM role_skill_requirements'))
        ids = {r[0] for r in db.execute('SELECT employee_id FROM employees')}
        for index, e in enumerate(employees):
            try:
                import re
                require(re.fullmatch(r'E\d{4,8}', e['employee_id']), 'неверный employee_id')
                require(all(isinstance(e[k], str) and e[k].strip() for k in ('full_name', 'department', 'role', 'grade', 'work_format', 'preferred_language')), 'пустое поле профиля')
                date.fromisoformat(e['last_review_date'])
                require((e['role'], e['grade']) in profiles, 'неизвестная роль/грейд')
                require(type(e['tenure_months']) is int and e['tenure_months'] >= 0, 'неверный стаж')
                require(isinstance(e.get('skills', {}), dict), 'skills должен быть объектом')
                require(e.get('manager_id') is None or isinstance(e['manager_id'], str), 'неверный manager_id')
                for skill, level in e.get('skills', {}).items():
                    require(skill in skills and type(level) is int and 0 <= level <= 5, 'неверный навык/уровень')
                goal = e.get('career_goal')
                if goal:
                    require((goal['target_role'], goal['target_grade']) in profiles, 'неизвестная цель')
                values = (e['employee_id'], e['full_name'], e['department'], e['role'], e['grade'], e.get('manager_id'), e['tenure_months'], e['work_format'], e['preferred_language'], e['last_review_date'])
                old = db.execute('SELECT * FROM employees WHERE employee_id=?', (e['employee_id'],)).fetchone()
                if old:
                    # A repeated import must not reset a goal selected in the application.
                    require(old == values and dict(db.execute('SELECT skill_id, level FROM employee_skills WHERE employee_id=?', (e['employee_id'],))) == e.get('skills', {}), 'профиль с таким ID уже существует с другими данными')
                    counts['duplicates'] += 1
                    continue
                db.execute('INSERT INTO employees VALUES (?,?,?,?,?,?,?,?,?,?)', values)
                db.executemany('INSERT INTO employee_skills VALUES (?,?,?)', [(e['employee_id'], k, v) for k,v in e.get('skills', {}).items()])
                if goal:
                    db.execute('INSERT INTO career_goals VALUES (?,?,?)', (e['employee_id'], goal['target_role'], goal['target_grade']))
                ids.add(e['employee_id'])
                counts['employees_added'] += 1
            except (AssertionError, KeyError, ValueError, TypeError, sqlite3.IntegrityError) as exc:
                errors.append(f'employees[{index}]: {exc}')
        for index, e in enumerate(employees):
            if isinstance(e.get('manager_id'), str) and e['manager_id'] and e['manager_id'] not in ids:
                errors.append(f'employees[{index}]: неизвестный manager_id')
        for index, r in enumerate(history):
            try:
                require(r['record_id'] and len(r['record_id']) <= 100, 'неверный record_id')
                require(r['employee_id'] in ids and r['event_id'] in events, 'неизвестный профиль или событие')
                date.fromisoformat(r['date'])
                if r['due_date']:
                    date.fromisoformat(r['due_date'])
                require(r['status'] in {'completed', 'in_progress', 'skipped', 'declined', 'registered', 'no_show', 'assigned', 'not_started', 'overdue', 'dropped'}, 'неверный статус')
                pct, score, rating = int(r['completion_pct']), optional_int(r['score']), optional_int(r['feedback_rating'])
                require(0 <= pct <= 100 and (score is None or 0 <= score <= 100) and (rating is None or 1 <= rating <= 5), 'неверный диапазон')
                require(r['status'] != 'completed' or pct == 100, 'завершение должно быть 100%')
                values = (r['record_id'], r['employee_id'], r['event_id'], r['date'], r['due_date'] or None, r['status'], pct, score, rating, r['assigned_by'])
                old = db.execute('SELECT * FROM activity_records WHERE record_id=?', (r['record_id'],)).fetchone()
                if old:
                    require(old == values, 'record_id уже занят другой записью')
                    counts['duplicates'] += 1
                else:
                    require(r['assigned_by'] != 'career_quest', 'assigned_by=career_quest зарезервирован для завершений в приложении')
                    db.execute('INSERT INTO activity_records VALUES (?,?,?,?,?,?,?,?,?,?)', values)
                    counts['history_added'] += 1
            except (AssertionError, KeyError, ValueError, TypeError, sqlite3.IntegrityError) as exc:
                errors.append(f'activity_history[{index + 2}]: {exc}')
        if errors:
            raise ValueError('Импорт отменён; база не изменена:\n' + '\n'.join(errors))
    return counts


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Создание или безопасное добавление данных Career Quest')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--append', type=Path, help='Папка с employees.json и/или activity_history.csv')
    group.add_argument('--reset', action='store_true', help='Удалить существующие данные и прогресс')
    args = parser.parse_args()
    try:
        counts = append_dataset(args.append) if args.append else import_dataset(reset=args.reset)
        print(json.dumps(counts, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
