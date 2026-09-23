from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any


SNAPSHOT_DATE = "2026-10-01"
RECURRING_EVENT_ID = "EV_036"


def target_for(connection: sqlite3.Connection, employee: sqlite3.Row) -> dict[str, str]:
    goal = connection.execute(
        "SELECT target_role, target_grade FROM career_goals WHERE employee_id = ?",
        (employee["employee_id"],),
    ).fetchone()
    if goal:
        return {"role": goal["target_role"], "grade": goal["target_grade"], "source": "career_goal"}
    return {"role": employee["role"], "grade": employee["grade"], "source": "current_profile"}


def projected_gains(connection: sqlite3.Connection, employee_id: str) -> dict[str, float]:
    initial = {r['skill_id']: float(r['level']) for r in connection.execute(
        'SELECT skill_id, level FROM employee_skills WHERE employee_id = ?', (employee_id,))}
    levels = dict(initial)
    rows = connection.execute(
        """
        SELECT g.skill_id, g.gain, g.max_level
        FROM activity_records a
        JOIN event_skill_gains g ON g.event_id = a.event_id
        WHERE a.employee_id = ? AND a.status = 'completed' AND a.assigned_by = 'career_quest'
        ORDER BY a.date, a.rowid, g.skill_id
        """,
        (employee_id,),
    ).fetchall()
    for row in rows:
        current = levels.get(row['skill_id'], 0)
        levels[row['skill_id']] = max(current, min(5, row['max_level'], current + row['gain']))
    return {key: value - initial.get(key, 0) for key, value in levels.items()}


def build_gaps(connection: sqlite3.Connection, employee: sqlite3.Row, target: dict[str, str]) -> list[dict[str, Any]]:
    gains = projected_gains(connection, employee["employee_id"])
    rows = connection.execute(
        """
        SELECT r.skill_id, s.name, s.type, s.category, s.description, r.required_level, r.is_critical,
               COALESCE(es.level, 0) AS current_level
        FROM role_skill_requirements r
        JOIN skills s ON s.skill_id = r.skill_id
        LEFT JOIN employee_skills es ON es.skill_id = r.skill_id AND es.employee_id = ?
        WHERE r.role = ? AND r.grade = ?
        ORDER BY r.is_critical DESC, r.required_level - COALESCE(es.level, 0) DESC, s.name
        """,
        (employee["employee_id"], target["role"], target["grade"]),
    ).fetchall()
    gaps = []
    for row in rows:
        confirmed = int(row["current_level"])
        expected = min(5.0, confirmed + gains.get(row["skill_id"], 0))
        required = int(row["required_level"])
        gaps.append(
            {
                "skill_id": row["skill_id"], "name": row["name"], "type": row["type"],
                "category": row["category"], "current_level": confirmed,
                "description": row["description"],
                "expected_level": round(expected, 1), "required_level": required,
                "gap": max(0, required - confirmed),
                "expected_gap": round(max(0, required - expected), 1),
                "critical": bool(row["is_critical"]),
            }
        )
    return gaps


def _history_affinity(connection: sqlite3.Connection, employee_id: str, event_type: str, event_format: str) -> int:
    rows = connection.execute(
        """
        SELECT e.type, e.format, a.status, a.feedback_rating
        FROM activity_records a JOIN events e ON e.event_id = a.event_id
        WHERE a.employee_id = ?
        """,
        (employee_id,),
    ).fetchall()
    completed = [row for row in rows if row["status"] == "completed"]
    if not rows:
        return 10
    type_rate = sum(row["type"] == event_type for row in completed) / max(1, sum(row["type"] == event_type for row in rows))
    format_rate = sum(row["format"] == event_format for row in completed) / max(1, sum(row["format"] == event_format for row in rows))
    ratings = [row["feedback_rating"] for row in completed if row["feedback_rating"] is not None]
    rating_factor = (sum(ratings) / len(ratings) / 5) if ratings else 0.6
    return round(min(20, 8 * type_rate + 7 * format_rate + 5 * rating_factor))


def recommend(connection: sqlite3.Connection, employee: sqlite3.Row, target: dict[str, str], gaps: list[dict[str, Any]], *, limit: int | None = 3, max_minutes: int | None = None, event_format: str | None = None, exclusions: Counter | None = None) -> list[dict[str, Any]]:
    def reject(reason: str) -> None:
        if exclusions is not None:
            exclusions[reason] += 1
    actionable = {gap["skill_id"]: gap for gap in gaps if gap["expected_gap"] > 0}
    completed = {
        row[0] for row in connection.execute(
            "SELECT event_id FROM activity_records WHERE employee_id = ? AND status = 'completed'",
            (employee["employee_id"],),
        )
    }
    employee_skills = {
        row["skill_id"]: int(row["level"]) for row in connection.execute(
            "SELECT skill_id, level FROM employee_skills WHERE employee_id = ?", (employee["employee_id"],)
        )
    }
    candidates = connection.execute(
        """
        SELECT DISTINCT e.* FROM events e
        JOIN event_targets t ON t.event_id = e.event_id
        WHERE e.mandatory = 0 AND t.role = ? AND t.grade = ?
        """,
        (target["role"], target["grade"]),
    ).fetchall()
    result = []
    total_gap = sum(gap["expected_gap"] for gap in actionable.values()) or 1
    for event in candidates:
        if max_minutes is not None and event['duration_hours'] * 60 > max_minutes:
            reject('Не укладывается в доступное время')
            continue
        if event_format and event['format'] != event_format:
            reject('Не подходит выбранный формат')
            continue
        if event["event_id"] in completed and event["event_id"] != RECURRING_EVENT_ID:
            reject('Активность уже завершена')
            continue
        prerequisites = connection.execute(
            "SELECT skill_id, required_level FROM event_prerequisites WHERE event_id = ?", (event["event_id"],)
        ).fetchall()
        if any(employee_skills.get(row["skill_id"], 0) < row["required_level"] for row in prerequisites):
            reject('Не выполнены предварительные требования')
            continue
        sessions = [
            row[0] for row in connection.execute(
                "SELECT session_date FROM event_sessions WHERE event_id = ? AND session_date >= ? ORDER BY session_date",
                (event["event_id"], SNAPSHOT_DATE),
            )
        ]
        if event["format"] != "self_paced" and not sessions:
            reject('Нет доступной сессии')
            continue
        covered = []
        useful_gain = 0.0
        for gain in connection.execute(
            "SELECT g.skill_id, g.gain, g.max_level, s.name FROM event_skill_gains g JOIN skills s ON s.skill_id = g.skill_id WHERE g.event_id = ?",
            (event["event_id"],),
        ):
            gap = actionable.get(gain["skill_id"])
            if not gap or gap["expected_level"] >= gain["max_level"]:
                continue
            useful = min(float(gain["gain"]), float(gain["max_level"]) - gap["expected_level"], gap["expected_gap"])
            if useful > 0:
                useful_gain += useful
                covered.append({"skill_id": gain["skill_id"], "name": gain["name"], "gain": round(useful, 1), "critical": gap["critical"]})
        if not covered:
            reject('Не сокращает оставшийся разрыв с учётом предела навыка')
            continue

        critical = sum(item["critical"] for item in covered)
        priority = min(30, 18 + critical * 8 + max(0, len(covered) - 1) * 2)
        reduction = round(min(25, 25 * useful_gain / total_gap))
        history = _history_affinity(connection, employee["employee_id"], event["type"], event["format"])
        duration = float(event["duration_hours"])
        realism = max(5, round(15 - max(0, duration - 4) * 0.5))
        time_efficiency = max(2, round(10 / max(1, duration / max(useful_gain, 0.5))))
        components = {
            "goal_priority": int(priority), "gap_reduction": int(reduction),
            "history_fit": int(history), "realism": int(realism),
            "time_efficiency": int(min(10, time_efficiency)),
        }
        score = sum(components.values())
        names = ", ".join(item["name"] for item in covered)
        evidence = [
            f"Цель: {target['role']} · {target['grade']}.",
            'Навыки: ' + '; '.join(f"{c['name']} {actionable[c['skill_id']]['expected_level']:g}/{actionable[c['skill_id']]['required_level']}" + (' — критический' if c['critical'] else '') for c in covered) + '.',
            f"Соответствие истории: {history}/20; учитываются завершения и пропуски этого типа и формата, а также отзывы.",
            f"Ожидаемое сокращение дефицита: {useful_gain:g}. Длительность: {duration:g} ч.",
        ]
        explanation = ' '.join(evidence)
        result.append(
            {
                "event_id": event["event_id"], "title": event["title"], "description": event["description"],
                "type": event["type"], "format": event["format"], "duration_hours": duration,
                "next_session": sessions[0] if sessions else None, "score": score,
                "score_label": "Recommendation Score", "components": components,
                "covered_skills": covered, "explanation": explanation, "factors": evidence,
            }
        )
    if not candidates:
        reject('В каталоге нет добровольных событий для этой роли и грейда')
    ordered = sorted(result, key=lambda item: (-item["score"], item["duration_hours"], item["event_id"]))
    return ordered if limit is None else ordered[:limit]


def career_payload(connection: sqlite3.Connection, employee_id: str) -> dict[str, Any] | None:
    employee = connection.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,)).fetchone()
    if not employee:
        return None
    target = target_for(connection, employee)
    gaps = build_gaps(connection, employee, target)
    recommendations = recommend(connection, employee, target, gaps)
    progress = {
        "total_required": len(gaps),
        "confirmed_ready": sum(gap["gap"] == 0 for gap in gaps),
        "expected_ready": sum(gap["expected_gap"] == 0 for gap in gaps),
        "remaining_gap": round(sum(gap["gap"] for gap in gaps), 1),
        "expected_remaining_gap": round(sum(gap["expected_gap"] for gap in gaps), 1),
    }
    return {
        "employee": dict(employee), "target": target, "gaps": gaps,
        "recommendations": recommendations, "progress": progress,
        "snapshot_date": SNAPSHOT_DATE,
        "history": [dict(row) for row in connection.execute(
            '''SELECT a.record_id, a.event_id, e.title, a.date, a.status, a.completion_pct,
                      a.assigned_by FROM activity_records a JOIN events e ON e.event_id=a.event_id
               WHERE a.employee_id=? ORDER BY a.date DESC, a.rowid DESC LIMIT 30''', (employee_id,))],
        "achievements": {"quests_completed": connection.execute(
            "SELECT COUNT(*) FROM activity_records WHERE employee_id=? AND assigned_by='career_quest' AND status='completed'", (employee_id,)).fetchone()[0]},
    }


def hr_summary(connection: sqlite3.Connection, department: str) -> dict[str, Any]:
    gaps_counter: Counter[str] = Counter()
    without = []
    employees = connection.execute('SELECT * FROM employees WHERE department=? ORDER BY full_name', (department,)).fetchall()
    for employee in employees:
        target = target_for(connection, employee)
        gaps = build_gaps(connection, employee, target)
        for gap in gaps:
            if gap["expected_gap"] > 0:
                gaps_counter[gap["name"]] += 1
        exclusions: Counter = Counter()
        if any(g['expected_gap'] > 0 for g in gaps) and not recommend(connection, employee, target, gaps, exclusions=exclusions):
            without.append({"employee_id": employee["employee_id"], "full_name": employee["full_name"], "target_role": target["role"], 'reasons': [{'reason': name, 'events': count} for name, count in exclusions.most_common()]})
    statuses = {row['status']: row['count'] for row in connection.execute('''SELECT a.status, COUNT(*) AS count
        FROM activity_records a JOIN employees e ON e.employee_id=a.employee_id
        WHERE e.department=? GROUP BY a.status''', (department,))}
    total = sum(statuses.values())
    completed = statuses.get("completed", 0)
    return {
        'department': department, 'employee_count': len(employees),
        "top_gaps": [{"name": name, "employees": count} for name, count in gaps_counter.most_common(5)],
        "employees_without_recommendations": without,
        "participation": {"total_records": total, "completed": completed, "completion_rate": round(completed / total * 100, 1) if total else 0, "statuses": statuses},
        'events': [dict(row) for row in connection.execute('''SELECT ev.event_id, ev.title, COUNT(*) AS participants,
            SUM(CASE WHEN a.status='completed' THEN 1 ELSE 0 END) AS completed
            FROM activity_records a JOIN employees e ON e.employee_id=a.employee_id
            JOIN events ev ON ev.event_id=a.event_id WHERE e.department=?
            GROUP BY ev.event_id ORDER BY participants DESC''', (department,))],
    }
