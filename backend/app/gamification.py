"""Personal game progress derived from participation, never a skill assessment.

The ledger is rebuilt from all eligible history on every read. Stable event and
achievement identities make imports, retries and page reloads idempotent without
an additional mutable balance or database migration.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import Any


LEVEL_XP = 300
RECURRING_EVENT_ID = "EV_036"

# id, title, description, icon, metric, target, bonus XP
BADGES = (
    ("first_quest", "Первый шаг", "Завершить первую добровольную активность.", "flag", "quests", 1, 25),
    ("three_quests", "Вошёл во вкус", "Завершить 3 добровольные активности.", "route", "quests", 3, 40),
    ("ten_quests", "Коллекционер опыта", "Завершить 10 добровольных активностей.", "award", "quests", 10, 100),
    ("five_hours", "Время для себя", "Накопить 5 часов завершённого обучения.", "clock", "hours", 5, 40),
    ("twenty_hours", "Глубокое погружение", "Накопить 20 часов завершённого обучения.", "gem", "hours", 20, 80),
    ("three_skills", "Новые горизонты", "Пройти активности для 3 разных навыков.", "compass", "skills", 3, 40),
    ("six_skills", "Широкий кругозор", "Пройти активности для 6 разных навыков.", "spark", "skills", 6, 70),
    ("two_formats", "Гибкий подход", "Попробовать 2 разных формата обучения.", "map", "formats", 2, 40),
    ("three_self_paced", "В своём темпе", "Завершить 3 самостоятельные активности.", "skills", "self_paced", 3, 50),
    ("two_workshops", "От теории к делу", "Завершить 2 практикума.", "chart", "workshops", 2, 50),
    ("first_mentoring", "Сила диалога", "Завершить встречу с наставником.", "people", "mentoring", 1, 40),
    ("two_weeks", "Поймал ритм", "Учиться 2 календарные недели подряд.", "leaf", "best_streak", 2, 60),
    ("four_weeks", "Привычка расти", "Учиться 4 календарные недели подряд.", "up", "best_streak", 4, 120),
    ("three_types", "Исследователь методов", "Пройти активности 3 разных типов: например курс, практикум и встречу.", "compass", "types", 3, 70),
    ("three_clubs", "Голос сообщества", "Завершить 3 разные сессии клуба выступлений.", "people", "clubs", 3, 70),
)

# Missions are lifetime goals: no resets, loss of rewards or daily login pressure.
MISSIONS = (
    ("quest_route", "Маршрут из пяти шагов", "Завершить 5 добровольных активностей за всё время.", "quests", 5, 100),
    ("learning_marathon", "Марафон знаний", "Накопить 12 часов завершённого обучения за всё время.", "hours", 12, 100),
    ("skill_constellation", "Созвездие навыков", "Пройти активности для 8 разных навыков за всё время.", "skills", 8, 140),
    ("steady_pace", "Устойчивый темп", "Хотя бы один раз учиться 6 календарных недель подряд.", "best_streak", 6, 180),
)


def quest_xp(duration_hours: float) -> int:
    """A visible, capped reward for an eligible completion (50..160 XP)."""
    return 40 + 10 * min(12, max(1, math.ceil(duration_hours)))


def level_title(level: int) -> str:
    for ceiling, title in ((2, "Искатель"), (4, "Исследователь"), (6, "Практик"),
                           (9, "Мастер маршрута"), (14, "Наставник")):
        if level <= ceiling:
            return title
    return "Легенда развития"


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_streaks(days: set[date], as_of: date) -> tuple[int, int]:
    """Consecutive ISO weeks; the current week may still be in progress."""
    weeks = sorted({_week(day) for day in days if day <= as_of})
    current = best = run = 0
    previous = None
    for week in weeks:
        run = run + 1 if previous is not None and week - previous == timedelta(weeks=1) else 1
        best = max(best, run)
        previous = week
    if weeks and _week(as_of) - weeks[-1] <= timedelta(weeks=1):
        current = run
    return current, best


def build_gamification(connection: sqlite3.Connection, employee_id: str, as_of: str) -> dict[str, Any]:
    reference = date.fromisoformat(as_of)
    rows = connection.execute(
        """SELECT a.record_id, a.event_id, a.date, a.assigned_by,
                  e.title, e.duration_hours, e.type, e.format
           FROM activity_records a JOIN events e ON e.event_id = a.event_id
           WHERE a.employee_id = ? AND a.status = 'completed' AND e.mandatory = 0
           ORDER BY a.date, a.record_id""", (employee_id,),
    ).fetchall()
    eligible = []
    for row in rows:
        actual_date = date.fromisoformat(row["date"])
        # The demo completion endpoint deliberately allows scheduled club sessions.
        # Their real session identity is retained, but their game reward belongs to
        # the snapshot day. Future imported history must not create rewards.
        demo_future = (actual_date > reference and row["event_id"] == RECURRING_EVENT_ID
                       and row["assigned_by"] == "career_quest")
        if actual_date > reference and not demo_future:
            continue
        identity = (f"{row['event_id']}:{row['date']}"
                    if row["event_id"] == RECURRING_EVENT_ID else row["event_id"])
        eligible.append({**dict(row), "id": identity, "effective_date": min(actual_date, reference),
                         "demo_future": demo_future})
    eligible.sort(key=lambda row: (row["effective_date"], row["date"], row["record_id"]))

    event_skills: dict[str, set[str]] = defaultdict(set)
    for row in connection.execute("SELECT event_id, skill_id FROM event_skill_gains WHERE gain > 0"):
        event_skills[row["event_id"]].add(row["skill_id"])
    seen: set[str] = set()
    skills: set[str] = set()
    formats: set[str] = set()
    types: set[str] = set()
    days: set[date] = set()
    metrics: dict[str, float] = {key: 0 for key in (
        "quests", "hours", "skills", "formats", "types", "self_paced", "workshops", "mentoring", "clubs", "best_streak")}
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "xp": 0})
    rewards = []
    earned: set[str] = set()
    total_xp = 0

    def reward(identity: str, title: str, day: str, xp: int, source: str) -> None:
        nonlocal total_xp
        total_xp += xp
        daily[day]["xp"] += xp
        rewards.append({"id": identity, "title": title, "date": day, "xp": xp, "source": source})

    for row in eligible:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        day = row["effective_date"].isoformat()
        skills.update(event_skills[row["event_id"]])
        formats.add(row["format"])
        types.add(row["type"])
        days.add(row["effective_date"])
        metrics["quests"] += 1
        metrics["hours"] += float(row["duration_hours"])
        metrics["skills"], metrics["formats"], metrics["types"] = len(skills), len(formats), len(types)
        metrics["self_paced"] += row["format"] == "self_paced"
        metrics["workshops"] += row["type"] == "workshop"
        metrics["mentoring"] += row["type"] == "mentoring"
        metrics["clubs"] += row["event_id"] == RECURRING_EVENT_ID
        _, metrics["best_streak"] = week_streaks(days, reference)
        daily[day]["count"] += 1
        source = ("Демо: завершение будущей сессии" if row["demo_future"] else
                  "Career Quest" if row["assigned_by"] == "career_quest" else "История участия")
        reward(f"quest:{row['id']}", row["title"], day, quest_xp(row["duration_hours"]), source)
        for badge_id, title, _, _, metric, target, xp in BADGES:
            identity = f"badge:{badge_id}"
            if identity not in earned and metrics[metric] >= target:
                earned.add(identity)
                reward(identity, title, day, xp, "Значок · демо" if row["demo_future"] else "Значок")
        for mission_id, title, _, metric, target, xp in MISSIONS:
            identity = f"mission:{mission_id}"
            if identity not in earned and metrics[metric] >= target:
                earned.add(identity)
                reward(identity, title, day, xp, "Миссия · демо" if row["demo_future"] else "Миссия")

    level = total_xp // LEVEL_XP + 1
    floor_xp = (level - 1) * LEVEL_XP
    current_streak, best_streak = week_streaks(days, reference)
    badges = [{"id": badge_id, "title": title, "description": description, "icon": icon,
               "progress": round(min(metrics[metric], target), 2), "target": target,
               "unlocked": f"badge:{badge_id}" in earned, "reward_xp": xp}
              for badge_id, title, description, icon, metric, target, xp in BADGES]
    missions = [{"id": mission_id, "title": title, "description": description,
                 "progress": round(min(metrics[metric], target), 2), "target": target,
                 "completed": f"mission:{mission_id}" in earned, "reward_xp": xp}
                for mission_id, title, description, metric, target, xp in MISSIONS]
    activity_days = []
    for offset in range(83, -1, -1):
        day = (reference - timedelta(days=offset)).isoformat()
        activity_days.append({"date": day, **daily[day]})
    return {
        "total_xp": total_xp, "level": level, "level_title": level_title(level),
        "level_floor_xp": floor_xp, "next_level_xp": level * LEVEL_XP,
        "level_progress_pct": round((total_xp - floor_xp) / LEVEL_XP * 100, 1),
        "xp_to_next_level": level * LEVEL_XP - total_xp,
        "completed_quests": int(metrics["quests"]), "learning_hours": round(metrics["hours"], 2),
        "skill_count": len(skills), "current_streak": current_streak, "best_streak": best_streak,
        "as_of": as_of, "badges": badges, "missions": missions,
        "milestones": [{"level": milestone, "title": level_title(milestone),
                        "xp": (milestone - 1) * LEVEL_XP, "reached": milestone <= level}
                       for milestone in range(1, 11)],
        "activity_days": activity_days, "recent_rewards": list(reversed(rewards[-12:])),
    }
