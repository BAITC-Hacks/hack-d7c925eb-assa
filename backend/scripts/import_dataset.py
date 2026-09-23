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


def import_dataset() -> dict[str, int]:
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

    return {
        "skills": len(skills_doc["skills"]),
        "employees": len(employees_doc["employees"]),
        "events": len(events_doc["events"]),
        "activity_records": len(activity),
    }


if __name__ == "__main__":
    counts = import_dataset()
    print(f"Created {DB_PATH}")
    print("Imported " + ", ".join(f"{key}={value}" for key, value in counts.items()))
