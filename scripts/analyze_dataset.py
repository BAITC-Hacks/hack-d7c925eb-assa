#!/usr/bin/env python3
"""Reproducible analysis for the Career Quest synthetic dataset."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "career_quest_dataset"
OUTPUT_DIR = ROOT / "analysis"
SNAPSHOT_DATE = date(2026, 10, 1)
RECURRING_EVENT_ID = "EV_036"
GRADE_ORDER = {"Junior": 0, "Middle": 1, "Senior": 2, "Lead": 3}


def load_json(name: str) -> dict[str, Any]:
    with (DATA_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_activity() -> list[dict[str, str]]:
    with (DATA_DIR / "activity_history.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def percent(numerator: int | float, denominator: int | float) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def average(values: Iterable[int | float]) -> float | None:
    collected = list(values)
    return round(mean(collected), 2) if collected else None


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True)
class Gap:
    employee_id: str
    full_name: str
    current_role: str
    current_grade: str
    target_role: str
    target_grade: str
    target_source: str
    skill_id: str
    skill_name: str
    skill_type: str
    category: str
    current_level: int
    required_level: int
    gap: int
    critical: bool


def validate_data(
    skills_doc: dict[str, Any],
    employees_doc: dict[str, Any],
    events_doc: dict[str, Any],
    activity: list[dict[str, str]],
) -> dict[str, Any]:
    skills = skills_doc["skills"]
    profiles = skills_doc["role_profiles"]
    employees = employees_doc["employees"]
    events = events_doc["events"]

    skill_ids = [item["skill_id"] for item in skills]
    employee_ids = [item["employee_id"] for item in employees]
    event_ids = [item["event_id"] for item in events]
    record_ids = [item["record_id"] for item in activity]
    profile_keys = [(item["role"], item["grade"]) for item in profiles]

    issues: list[str] = []
    for label, values in (
        ("skill_id", skill_ids),
        ("employee_id", employee_ids),
        ("event_id", event_ids),
        ("record_id", record_ids),
        ("role_profile", profile_keys),
    ):
        duplicates = [key for key, count in Counter(values).items() if count > 1]
        if duplicates:
            issues.append(f"Duplicate {label}: {duplicates[:5]}")

    skill_set = set(skill_ids)
    employee_set = set(employee_ids)
    event_set = set(event_ids)
    profile_set = set(profile_keys)

    for employee in employees:
        if (employee["role"], employee["grade"]) not in profile_set:
            issues.append(f"Missing profile for {employee['employee_id']}")
        manager_id = employee.get("manager_id")
        if manager_id and manager_id not in employee_set:
            issues.append(f"Unknown manager {manager_id} for {employee['employee_id']}")
        unknown = set(employee.get("skills", {})) - skill_set
        if unknown:
            issues.append(f"Unknown employee skills for {employee['employee_id']}: {sorted(unknown)}")

    for profile in profiles:
        unknown = set(profile["required_skills"]) | set(profile["critical_skills"])
        unknown -= skill_set
        if unknown:
            issues.append(f"Unknown skills in profile {profile['role']}/{profile['grade']}")

    for event in events:
        developed = {item["skill_id"] for item in event["develops_skills"]}
        unknown = (developed | set(event["prerequisites"])) - skill_set
        if unknown:
            issues.append(f"Unknown skills in {event['event_id']}: {sorted(unknown)}")

    allowed_status = {
        "completed",
        "in_progress",
        "dropped",
        "no_show",
        "declined",
        "overdue",
    }
    for row in activity:
        if row["employee_id"] not in employee_set:
            issues.append(f"Unknown employee in {row['record_id']}")
        if row["event_id"] not in event_set:
            issues.append(f"Unknown event in {row['record_id']}")
        if row["status"] not in allowed_status:
            issues.append(f"Unknown status in {row['record_id']}: {row['status']}")
        completion = int(row["completion_pct"])
        if not 0 <= completion <= 100:
            issues.append(f"Invalid completion in {row['record_id']}")
        if row["status"] == "completed" and completion != 100:
            issues.append(f"Completed row below 100%: {row['record_id']}")

    return {
        "passed": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "unique_ids": {
            "skills": len(skill_set) == len(skill_ids),
            "employees": len(employee_set) == len(employee_ids),
            "events": len(event_set) == len(event_ids),
            "activity_records": len(set(record_ids)) == len(record_ids),
            "role_profiles": len(profile_set) == len(profile_keys),
        },
    }


def build_gaps(
    skills_doc: dict[str, Any], employees: list[dict[str, Any]]
) -> tuple[list[Gap], dict[str, dict[str, Any]]]:
    skill_by_id = {item["skill_id"]: item for item in skills_doc["skills"]}
    profile_by_key = {
        (item["role"], item["grade"]): item
        for item in skills_doc["role_profiles"]
    }
    result: list[Gap] = []
    targets: dict[str, dict[str, Any]] = {}

    for employee in employees:
        goal = employee.get("career_goal")
        if goal and (goal["target_role"], goal["target_grade"]) in profile_by_key:
            target_role = goal["target_role"]
            target_grade = goal["target_grade"]
            source = "career_goal"
        else:
            target_role = employee["role"]
            target_grade = employee["grade"]
            source = "current_profile"
        profile = profile_by_key[(target_role, target_grade)]
        targets[employee["employee_id"]] = {
            "role": target_role,
            "grade": target_grade,
            "source": source,
            "critical_skills": set(profile["critical_skills"]),
        }
        for skill_id, required in profile["required_skills"].items():
            current = int(employee.get("skills", {}).get(skill_id, 0))
            if current >= required:
                continue
            skill = skill_by_id[skill_id]
            result.append(
                Gap(
                    employee_id=employee["employee_id"],
                    full_name=employee["full_name"],
                    current_role=employee["role"],
                    current_grade=employee["grade"],
                    target_role=target_role,
                    target_grade=target_grade,
                    target_source=source,
                    skill_id=skill_id,
                    skill_name=skill["name"],
                    skill_type=skill["type"],
                    category=skill["category"],
                    current_level=current,
                    required_level=required,
                    gap=required - current,
                    critical=skill_id in profile["critical_skills"],
                )
            )
    return result, targets


def build_event_metrics(
    events: list[dict[str, Any]], activity: list[dict[str, str]]
) -> list[dict[str, Any]]:
    history: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in activity:
        history[row["event_id"]].append(row)

    rows: list[dict[str, Any]] = []
    for event in events:
        records = history[event["event_id"]]
        status_counts = Counter(row["status"] for row in records)
        completed = status_counts["completed"]
        scores = [int(row["score"]) for row in records if row["score"]]
        ratings = [int(row["feedback_rating"]) for row in records if row["feedback_rating"]]
        rows.append(
            {
                "event_id": event["event_id"],
                "title": event["title"],
                "type": event["type"],
                "format": event["format"],
                "mandatory": str(event["mandatory"]).lower(),
                "duration_hours": event["duration_hours"],
                "participants": len(records),
                "completed": completed,
                "completion_rate_pct": percent(completed, len(records)),
                "in_progress": status_counts["in_progress"],
                "dropped": status_counts["dropped"],
                "no_show": status_counts["no_show"],
                "declined": status_counts["declined"],
                "overdue": status_counts["overdue"],
                "avg_score": average(scores),
                "avg_feedback": average(ratings),
                "feedback_count": len(ratings),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["participants"]), row["event_id"]))


def build_recommendations(
    employees: list[dict[str, Any]],
    events: list[dict[str, Any]],
    activity: list[dict[str, str]],
    gaps: list[Gap],
    targets: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps_by_employee: dict[str, dict[str, Gap]] = defaultdict(dict)
    for gap in gaps:
        gaps_by_employee[gap.employee_id][gap.skill_id] = gap

    completed_by_employee: dict[str, set[str]] = defaultdict(set)
    for row in activity:
        if row["status"] == "completed":
            completed_by_employee[row["employee_id"]].add(row["event_id"])

    recommendations: list[dict[str, Any]] = []
    for employee in employees:
        employee_id = employee["employee_id"]
        target = targets[employee_id]
        employee_gaps = gaps_by_employee.get(employee_id, {})
        candidates: list[dict[str, Any]] = []

        for event in events:
            if event["mandatory"]:
                continue
            if target["role"] not in event["target_roles"]:
                continue
            if target["grade"] not in event["target_grades"]:
                continue
            if (
                event["event_id"] in completed_by_employee[employee_id]
                and event["event_id"] != RECURRING_EVENT_ID
            ):
                continue
            if any(
                int(employee.get("skills", {}).get(skill_id, 0)) < required
                for skill_id, required in event["prerequisites"].items()
            ):
                continue
            future_sessions = sorted(
                session
                for session in event["upcoming_sessions"]
                if parse_date(session) and parse_date(session) >= SNAPSHOT_DATE
            )
            if event["format"] != "self_paced" and not future_sessions:
                continue

            covered: list[tuple[Gap, float]] = []
            for developed in event["develops_skills"]:
                gap = employee_gaps.get(developed["skill_id"])
                if not gap or gap.current_level >= developed["max_level"]:
                    continue
                useful_gain = min(
                    float(developed["gain"]),
                    float(developed["max_level"] - gap.current_level),
                    float(gap.gap),
                )
                if useful_gain > 0:
                    covered.append((gap, useful_gain))
            if not covered:
                continue

            critical_count = sum(1 for gap, _ in covered if gap.critical)
            useful_gain = round(sum(gain for _, gain in covered), 2)
            duration = float(event["duration_hours"])
            efficiency = useful_gain / duration if duration else useful_gain
            score = round(critical_count * 100 + useful_gain * 10 + efficiency, 4)
            candidates.append(
                {
                    "employee_id": employee_id,
                    "full_name": employee["full_name"],
                    "target_role": target["role"],
                    "target_grade": target["grade"],
                    "event_id": event["event_id"],
                    "event_title": event["title"],
                    "event_type": event["type"],
                    "format": event["format"],
                    "duration_hours": event["duration_hours"],
                    "next_session": future_sessions[0] if future_sessions else "self_paced",
                    "skills_covered": "; ".join(gap.skill_name for gap, _ in covered),
                    "critical_skills_covered": critical_count,
                    "useful_gain": useful_gain,
                    "ranking_score": score,
                }
            )

        candidates.sort(
            key=lambda row: (
                -int(row["critical_skills_covered"]),
                -float(row["useful_gain"]),
                -float(row["ranking_score"]),
                float(row["duration_hours"]),
                row["event_id"],
            )
        )
        for rank, candidate in enumerate(candidates[:5], start=1):
            candidate["rank"] = rank
            recommendations.append(candidate)
    return recommendations


def build_summary(
    skills_doc: dict[str, Any],
    employees: list[dict[str, Any]],
    events: list[dict[str, Any]],
    activity: list[dict[str, str]],
    gaps: list[Gap],
    event_metrics: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    validation: dict[str, Any],
) -> dict[str, Any]:
    statuses = Counter(row["status"] for row in activity)
    assignment = Counter(row["assigned_by"] for row in activity)
    grades = Counter(item["grade"] for item in employees)
    roles = Counter(item["role"] for item in employees)
    formats = Counter(item["work_format"] for item in employees)
    languages = Counter(item["preferred_language"] for item in employees)
    event_types = Counter(item["type"] for item in events)
    event_formats = Counter(item["format"] for item in events)
    career_goals = sum(1 for item in employees if item.get("career_goal"))
    gap_employees = {gap.employee_id for gap in gaps}
    critical_gap_employees = {gap.employee_id for gap in gaps if gap.critical}
    recommendation_employees = {row["employee_id"] for row in recommendations}
    scores = [int(row["score"]) for row in activity if row["score"]]
    ratings = [int(row["feedback_rating"]) for row in activity if row["feedback_rating"]]
    completion_by_assignment = {}
    for source in sorted(assignment):
        source_rows = [row for row in activity if row["assigned_by"] == source]
        completed = sum(row["status"] == "completed" for row in source_rows)
        completion_by_assignment[source] = {
            "participations": len(source_rows),
            "completion_rate_pct": percent(completed, len(source_rows)),
        }

    skill_gap_counts = Counter(gap.skill_name for gap in gaps)
    category_gap_counts = Counter(gap.category for gap in gaps)
    critical_gap_counts = Counter(gap.skill_name for gap in gaps if gap.critical)
    top_events = sorted(
        event_metrics,
        key=lambda row: (-float(row["completion_rate_pct"]), -int(row["participants"])),
    )[:10]

    return {
        "snapshot_date": SNAPSHOT_DATE.isoformat(),
        "history_window": {"start": "2024-10-01", "end": "2026-09-30"},
        "validation": validation,
        "dataset": {
            "skills": len(skills_doc["skills"]),
            "role_profiles": len(skills_doc["role_profiles"]),
            "employees": len(employees),
            "events": len(events),
            "activity_records": len(activity),
        },
        "workforce": {
            "roles": dict(sorted(roles.items())),
            "grades": dict(sorted(grades.items(), key=lambda item: GRADE_ORDER[item[0]])),
            "work_formats": dict(sorted(formats.items())),
            "preferred_languages": dict(sorted(languages.items())),
            "career_goals_set": career_goals,
            "career_goals_set_pct": percent(career_goals, len(employees)),
            "median_tenure_months": median(item["tenure_months"] for item in employees),
        },
        "activity": {
            "statuses": dict(sorted(statuses.items())),
            "completion_rate_pct": percent(statuses["completed"], len(activity)),
            "assigned_by": dict(sorted(assignment.items())),
            "completion_by_assigned_by": completion_by_assignment,
            "avg_score": average(scores),
            "score_coverage_pct": percent(len(scores), len(activity)),
            "avg_feedback": average(ratings),
            "feedback_coverage_pct": percent(len(ratings), len(activity)),
        },
        "catalog": {
            "event_types": dict(sorted(event_types.items())),
            "event_formats": dict(sorted(event_formats.items())),
            "mandatory_events": sum(item["mandatory"] for item in events),
            "voluntary_events": sum(not item["mandatory"] for item in events),
        },
        "skill_gaps": {
            "total_gap_rows": len(gaps),
            "employees_with_gaps": len(gap_employees),
            "employees_with_gaps_pct": percent(len(gap_employees), len(employees)),
            "employees_with_critical_gaps": len(critical_gap_employees),
            "employees_with_critical_gaps_pct": percent(
                len(critical_gap_employees), len(employees)
            ),
            "top_skills": skill_gap_counts.most_common(10),
            "top_critical_skills": critical_gap_counts.most_common(10),
            "by_category": dict(category_gap_counts.most_common()),
        },
        "recommendations": {
            "rows": len(recommendations),
            "employees_with_recommendations": len(recommendation_employees),
            "coverage_of_employees_with_gaps_pct": percent(
                len(recommendation_employees), len(gap_employees)
            ),
        },
        "top_events_by_completion_rate": [
            {
                "event_id": row["event_id"],
                "title": row["title"],
                "participants": row["participants"],
                "completion_rate_pct": row["completion_rate_pct"],
            }
            for row in top_events
        ],
    }


def render_report(summary: dict[str, Any]) -> str:
    dataset = summary["dataset"]
    workforce = summary["workforce"]
    activity = summary["activity"]
    catalog = summary["catalog"]
    gaps = summary["skill_gaps"]
    recommendations = summary["recommendations"]
    validation = summary["validation"]

    top_gap_lines = "\n".join(
        f"| {index} | {name} | {count} |"
        for index, (name, count) in enumerate(gaps["top_skills"], start=1)
    )
    top_critical_lines = "\n".join(
        f"| {index} | {name} | {count} |"
        for index, (name, count) in enumerate(gaps["top_critical_skills"], start=1)
    )
    assignment_lines = "\n".join(
        f"| {source} | {values['participations']} | {values['completion_rate_pct']:.1f}% |"
        for source, values in activity["completion_by_assigned_by"].items()
    )
    top_event_lines = "\n".join(
        f"| {item['event_id']} | {item['title']} | {item['participants']} | "
        f"{item['completion_rate_pct']:.1f}% |"
        for item in summary["top_events_by_completion_rate"]
    )

    return f"""# Разбор датасета Career Quest

Дата среза: **{summary['snapshot_date']}**. История: **{summary['history_window']['start']} — {summary['history_window']['end']}**.

## Краткий итог

- Набор содержит {dataset['employees']} сотрудников, {dataset['skills']} навыков,
  {dataset['role_profiles']} профиля «роль × грейд», {dataset['events']} мероприятий
  и {dataset['activity_records']:,} записей участия.
- Карьерная цель задана у {workforce['career_goals_set']} сотрудников
  ({workforce['career_goals_set_pct']:.1f}%).
- Завершено {activity['statuses'].get('completed', 0):,} участий.
  Общая доля завершения — {activity['completion_rate_pct']:.1f}%.
- У {gaps['employees_with_gaps']} сотрудников ({gaps['employees_with_gaps_pct']:.1f}%)
  есть хотя бы один дефицит относительно карьерной цели либо текущего профиля.
- У {gaps['employees_with_critical_gaps']} сотрудников
  ({gaps['employees_with_critical_gaps_pct']:.1f}%) есть дефицит критического навыка.
- Подобрано {recommendations['rows']} рекомендаций для
  {recommendations['employees_with_recommendations']} сотрудников. Это
  {recommendations['coverage_of_employees_with_gaps_pct']:.1f}% сотрудников с дефицитами.

## Качество данных

Автоматическая проверка связей и ограничений: **{'пройдена' if validation['passed'] else 'есть замечания'}**.
Найдено проблем: **{validation['issue_count']}**. Проверены уникальность идентификаторов,
ссылки между файлами, допустимые статусы, диапазон прогресса и согласованность
статуса `completed` со значением 100%.

## Состав сотрудников

- По грейдам: {', '.join(f'{key} — {value}' for key, value in workforce['grades'].items())}.
- Формат работы: {', '.join(f'{key} — {value}' for key, value in workforce['work_formats'].items())}.
- Предпочтительный язык: {', '.join(f'{key} — {value}' for key, value in workforce['preferred_languages'].items())}.
- Медианный стаж: {workforce['median_tenure_months']} месяцев.

## Активность и завершение

| Инициатор | Участий | Завершено, % |
|---|---:|---:|
{assignment_lines}

Средняя итоговая оценка среди заполненных значений — **{activity['avg_score']}**,
покрытие оценками — **{activity['score_coverage_pct']:.1f}%**. Средний отзыв —
**{activity['avg_feedback']} из 5**, покрытие отзывами —
**{activity['feedback_coverage_pct']:.1f}%**. Пропуски не трактуются как нули.

Каталог включает {catalog['mandatory_events']} обязательных и
{catalog['voluntary_events']} добровольных мероприятий. В персональные
рекомендации включаются только добровольные мероприятия.

## Наиболее частые дефициты навыков

| № | Навык | Сотрудников с дефицитом |
|---:|---|---:|
{top_gap_lines}

### Критические дефициты

| № | Навык | Сотрудников с дефицитом |
|---:|---|---:|
{top_critical_lines}

## Мероприятия с высокой долей завершения

Рейтинг ниже сначала сортирует по доле завершения, затем по числу участников.
Для небольших выборок показатель следует интерпретировать осторожно.

| ID | Мероприятие | Участников | Завершено, % |
|---|---|---:|---:|
{top_event_lines}

## Методика рекомендаций

Целевой профиль берётся из `career_goal`. Если цель отсутствует или не найдена
в каталоге профилей, используется текущая роль и грейд. Отсутствующий у
сотрудника навык считается уровнем 0.

Событие допускается в рекомендации, если оно добровольное, соответствует
целевой роли и грейду, доступно после даты среза, удовлетворяет предварительным
требованиям и реально сокращает хотя бы один дефицит. Уже завершённые события
не повторяются, кроме регулярного клуба `EV_036`.

Сортировка учитывает в следующем порядке:

1. количество закрываемых критических навыков;
2. полезный прирост по дефицитам с учётом `gain` и `max_level`;
3. полезный прирост на час;
4. меньшую длительность и стабильный порядок по ID.

Результат — не решение о повышении. Он показывает, какие доступные мероприятия
лучше всего сокращают формально заданные дефициты. Для кадрового решения нужны
оценка руководителя, результаты работы и повторная оценка навыков.

## Ограничения

- Данные синтетические и описывают только одну дату среза.
- Уровни навыков отражают последнюю оценку; завершённые после неё мероприятия
  ещё не обязательно учтены в профиле.
- Доля завершения считается по записям участия, а не по уникальным сотрудникам.
- Рекомендательная модель не предсказывает результат обучения и не использует
  чувствительные персональные признаки.
- Пустые оценки и отзывы исключаются из средних и отдельно отражаются через
  показатели покрытия.

## Файлы результата

- `summary.json` — все основные показатели и результаты проверок;
- `event_metrics.csv` — показатели для каждого мероприятия;
- `employee_skill_gaps.csv` — по одной строке на дефицит навыка;
- `recommendations.csv` — до пяти рекомендаций на сотрудника.
"""


def main() -> None:
    skills_doc = load_json("skills.json")
    employees_doc = load_json("employees.json")
    events_doc = load_json("events.json")
    activity = load_activity()
    employees = employees_doc["employees"]
    events = events_doc["events"]

    OUTPUT_DIR.mkdir(exist_ok=True)
    validation = validate_data(skills_doc, employees_doc, events_doc, activity)
    gaps, targets = build_gaps(skills_doc, employees)
    event_metrics = build_event_metrics(events, activity)
    recommendations = build_recommendations(
        employees, events, activity, gaps, targets
    )
    summary = build_summary(
        skills_doc,
        employees,
        events,
        activity,
        gaps,
        event_metrics,
        recommendations,
        validation,
    )

    (OUTPUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(
        OUTPUT_DIR / "employee_skill_gaps.csv",
        [field for field in Gap.__dataclass_fields__],
        (gap.__dict__ for gap in gaps),
    )
    write_csv(
        OUTPUT_DIR / "event_metrics.csv",
        list(event_metrics[0]),
        event_metrics,
    )
    recommendation_fields = [
        "employee_id",
        "full_name",
        "target_role",
        "target_grade",
        "rank",
        "event_id",
        "event_title",
        "event_type",
        "format",
        "duration_hours",
        "next_session",
        "skills_covered",
        "critical_skills_covered",
        "useful_gain",
        "ranking_score",
    ]
    write_csv(
        OUTPUT_DIR / "recommendations.csv",
        recommendation_fields,
        ({field: row[field] for field in recommendation_fields} for row in recommendations),
    )
    (OUTPUT_DIR / "REPORT.md").write_text(render_report(summary), encoding="utf-8")

    print(
        json.dumps(
            {
                "validation_passed": validation["passed"],
                "validation_issues": validation["issue_count"],
                "gap_rows": len(gaps),
                "recommendation_rows": len(recommendations),
                "output_dir": str(OUTPUT_DIR),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
