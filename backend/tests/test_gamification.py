import sqlite3
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import test_recommendation
from backend.app import database
from backend.app.gamification import build_gamification, quest_xp, week_streaks
from backend.scripts import import_dataset as importer


class GamificationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(importer.SCHEMA)
        self.serial = 0

    def tearDown(self):
        self.db.close()

    def event(self, event_id="EV_TEST", *, hours=2, mandatory=0, kind="course", event_format="online", skills=()):
        self.db.execute("INSERT INTO events VALUES (?, ?, '', ?, ?, ?, ?)",
                        (event_id, event_id, kind, event_format, hours, mandatory))
        for skill in skills:
            self.db.execute("INSERT INTO event_skill_gains VALUES (?, ?, 1, 5)", (event_id, skill))

    def complete(self, event_id="EV_TEST", day="2026-10-01", *, employee="E1", status="completed", source="self"):
        self.serial += 1
        self.db.execute("INSERT INTO activity_records VALUES (?, ?, ?, ?, NULL, ?, 100, NULL, NULL, ?)",
                        (f"R{self.serial:05}", employee, event_id, day, status, source))

    def game(self, employee="E1", as_of="2026-10-01"):
        return build_gamification(self.db, employee, as_of)

    def test_zero_history_has_no_free_rewards_or_assessment_credit(self):
        self.db.execute("INSERT INTO employee_skills VALUES ('E1', 'BASELINE_SKILL', 5)")
        game = self.game()
        self.assertEqual((game["total_xp"], game["level"], game["completed_quests"], game["skill_count"]), (0, 1, 0, 0))
        self.assertEqual((game["level_floor_xp"], game["next_level_xp"], game["xp_to_next_level"]), (0, 300, 300))
        self.assertGreaterEqual(len(game["badges"]), 12)
        self.assertEqual(len(game["missions"]), 4)
        self.assertFalse(any(b["unlocked"] for b in game["badges"]))
        self.assertFalse(any(m["completed"] for m in game["missions"]))
        self.assertEqual(game["recent_rewards"], [])
        self.assertEqual(len(game["activity_days"]), 84)
        self.assertEqual(game["activity_days"][0]["date"], "2026-07-10")
        self.assertEqual(game["activity_days"][-1], {"date": "2026-10-01", "count": 0, "xp": 0})

    def test_reward_formula_rounds_up_and_caps(self):
        for hours, expected in ((0, 50), (0.5, 50), (1, 50), (1.01, 60), (2, 60), (12, 160), (100, 160)):
            self.assertEqual(quest_xp(hours), expected)

    def test_duplicate_ordinary_event_awards_once_on_earliest_date(self):
        self.event(skills=("S1", "S2"))
        self.complete(day="2026-09-08")
        first = self.game()
        self.complete(day="2026-09-10", source="career_quest")
        self.complete(day="2026-09-08", source="import")
        self.assertEqual(self.game(), first)
        self.assertEqual((first["completed_quests"], first["learning_hours"], first["skill_count"]), (1, 2, 2))
        self.assertEqual(first["total_xp"], 60 + 25)

    def test_recurring_event_uses_session_identity_and_labels_demo_future(self):
        self.event("EV_036", kind="meetup")
        self.complete("EV_036", "2026-09-10")
        self.complete("EV_036", "2026-09-10", source="import")
        self.complete("EV_036", "2026-09-24")
        self.complete("EV_036", "2026-10-08", source="import")
        self.assertEqual(self.game()["completed_quests"], 2)
        self.complete("EV_036", "2026-10-08", source="career_quest")
        result = self.game()
        self.assertEqual(result["completed_quests"], 3)
        demo = next(r for r in result["recent_rewards"] if r["id"] == "quest:EV_036:2026-10-08")
        self.assertEqual(demo["date"], "2026-10-01")
        self.assertIn("Демо", demo["source"])
        self.assertEqual(result["activity_days"][-1]["count"], 1)
        self.complete("EV_036", "2026-10-08", source="career_quest")
        self.assertEqual(self.game(), result)

    def test_mandatory_noncompleted_future_and_other_employee_excluded(self):
        self.event("REQUIRED", mandatory=1)
        self.event("OPTIONAL")
        self.complete("REQUIRED")
        for status in ("planned", "in_progress", "no_show", "declined", "skipped"):
            self.complete("OPTIONAL", status=status)
        self.complete("OPTIONAL", "2026-10-02")
        self.complete("OPTIONAL", "2026-10-02", source="career_quest")
        self.complete("OPTIONAL", employee="E2")
        self.assertEqual(self.game()["total_xp"], 0)
        self.assertEqual(self.game("E2")["completed_quests"], 1)

    def test_full_history_is_counted_beyond_calendar_and_last_thirty_records(self):
        for index in range(35):
            event_id = f"EV_{index}"
            self.event(event_id, hours=1, skills=(f"S{index}",))
            self.complete(event_id, (date(2025, 1, 1) + timedelta(days=index)).isoformat())
        game = self.game()
        self.assertEqual((game["completed_quests"], game["learning_hours"], game["skill_count"]), (35, 35, 35))
        self.assertFalse(any(d["count"] for d in game["activity_days"]))
        self.assertEqual(game["current_streak"], 0)
        self.assertGreaterEqual(game["best_streak"], 5)

    def test_bonuses_once_and_calendar_and_ledger_reconcile(self):
        formats = ("online", "offline", "self_paced")
        types = ("course", "workshop", "mentoring")
        for index in range(6):
            event_id = f"EVENT_{index}"
            self.event(event_id, hours=2, kind=types[index % 3], event_format=formats[index % 3], skills=(f"S{index}",))
            self.complete(event_id, (date(2026, 8, 24) + timedelta(weeks=index)).isoformat())
        game = self.game()
        bonus = sum(b["reward_xp"] for b in game["badges"] if b["unlocked"])
        bonus += sum(m["reward_xp"] for m in game["missions"] if m["completed"])
        self.assertEqual(game["total_xp"], 6 * 60 + bonus)
        self.assertEqual(sum(d["xp"] for d in game["activity_days"]), game["total_xp"])
        self.assertEqual(sum(d["count"] for d in game["activity_days"]), 6)
        self.assertEqual(len({r["id"] for r in game["recent_rewards"]}), len(game["recent_rewards"]))
        changes = self.db.total_changes
        self.assertEqual(self.game(), game)
        self.assertEqual(self.db.total_changes, changes)
        self.complete("EVENT_0", "2026-10-01")
        self.assertEqual(self.game(), game)
        later = self.game(as_of="2026-11-01")
        self.assertEqual(later["total_xp"], game["total_xp"])
        self.assertEqual(later["current_streak"], 0)
        self.assertEqual(later["badges"], game["badges"])

    def test_week_streak_handles_same_week_gaps_grace_and_year_boundary(self):
        days = {date(2025, 12, 22), date(2025, 12, 28), date(2025, 12, 29), date(2026, 1, 5)}
        self.assertEqual(week_streaks(days, date(2026, 1, 8)), (3, 3))
        self.assertEqual(week_streaks(days, date(2026, 1, 18)), (3, 3))
        self.assertEqual(week_streaks(days, date(2026, 1, 19)), (0, 3))
        self.assertEqual(week_streaks(days | {date(2026, 1, 19)}, date(2026, 1, 19)), (1, 3))
        self.assertEqual(week_streaks(set(), date(2026, 1, 19)), (0, 0))

    def test_level_boundaries_and_unbounded_levels(self):
        # Isolate base XP from achievement configuration to exercise exact boundaries.
        with patch("backend.app.gamification.BADGES", ()), patch("backend.app.gamification.MISSIONS", ()):
            for index in range(4):
                self.event(f"E{index}", hours=2)
                self.complete(f"E{index}")
            self.event("SHORT", hours=1)
            self.complete("SHORT")
            before = self.game()
            self.assertEqual((before["total_xp"], before["level"], before["xp_to_next_level"]), (290, 1, 10))
            self.db.execute("UPDATE events SET duration_hours=2 WHERE event_id='SHORT'")
            boundary = self.game()
            self.assertEqual((boundary["total_xp"], boundary["level"], boundary["level_floor_xp"]), (300, 2, 300))
            self.assertEqual(boundary["level_progress_pct"], 0)
            self.assertEqual(boundary["xp_to_next_level"], 300)
            for index in range(60):
                self.event(f"LONG_{index}", hours=2)
                self.complete(f"LONG_{index}")
            above = self.game()
            self.assertEqual((above["total_xp"], above["level"]), (3900, 14))
            self.assertEqual(len(above["milestones"]), 10)
            self.assertTrue(all(m["reached"] for m in above["milestones"]))


class GamificationApiTests(unittest.TestCase):
    setUp = test_recommendation.ApiTest.setUp
    tearDown = test_recommendation.ApiTest.tearDown

    def test_completion_reward_retry_reload_and_profile_isolation(self):
        path = "/api/v1/employees/E0001/career"
        before = self.client.get(path, headers=self.headers).json()
        option = before["recommendations"][0]
        self.assertEqual(option["reward_xp"], quest_xp(option["duration_hours"]))
        with database.connect() as db:
            other_before = build_gamification(db, "E0002", before["snapshot_date"])
        completion = self.client.post(f"/api/v1/employees/E0001/events/{option['event_id']}/complete", headers=self.headers,
                                      json={"participation_id": option["participation_id"]})
        self.assertEqual(completion.status_code, 200, completion.text)
        first = completion.json()
        self.assertGreaterEqual(first["reward"]["xp"], option["reward_xp"])
        self.assertEqual(first["reward"]["xp"], first["career"]["gamification"]["total_xp"] - before["gamification"]["total_xp"])
        retry = self.client.post(f"/api/v1/employees/E0001/events/{option['event_id']}/complete", headers=self.headers,
                                 json={"participation_id": option["participation_id"]}).json()
        self.assertTrue(retry["already_completed"])
        self.assertEqual(retry["reward"]["xp"], 0)
        self.assertFalse(retry["reward"]["level_up"])
        self.assertEqual(retry["reward"]["badges"], [])
        self.assertEqual(retry["career"]["gamification"], first["career"]["gamification"])
        reloaded = self.client.get(path, headers=self.headers).json()
        self.assertEqual(reloaded["gamification"], first["career"]["gamification"])
        self.assertEqual(reloaded["employee"]["grade"], before["employee"]["grade"])
        self.assertEqual([(s["skill_id"], s["current_level"]) for s in reloaded["current_skills"]],
                         [(s["skill_id"], s["current_level"]) for s in before["current_skills"]])
        with database.connect() as db:
            self.assertEqual(build_gamification(db, "E0002", before["snapshot_date"]), other_before)

    def test_recurring_demo_api_completion_is_idempotent_for_game_rewards(self):
        with database.connect() as db:
            db.execute("UPDATE role_skill_requirements SET required_level=4 WHERE skill_id='SK_PUBLIC_SPEAKING' AND role='Backend Engineer' AND grade='Middle'")
            db.execute("UPDATE employee_skills SET level=0 WHERE employee_id='E0001' AND skill_id='SK_PUBLIC_SPEAKING'")
            db.execute("DELETE FROM activity_records WHERE employee_id='E0001' AND event_id='EV_036'")
        url = "/api/v1/employees/E0001/events/EV_036/complete"
        body = {"participation_id": "EV_036:2026-10-08"}
        first = self.client.post(url, headers=self.headers, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertGreaterEqual(first.json()["reward"]["xp"], quest_xp(2))
        retry = self.client.post(url, headers=self.headers, json=body).json()
        self.assertEqual(retry["reward"]["xp"], 0)
        self.assertEqual(retry["career"]["gamification"], first.json()["career"]["gamification"])
        second = self.client.post(url, headers=self.headers, json={"participation_id": "EV_036:2026-10-22"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["career"]["gamification"]["completed_quests"],
                         first.json()["career"]["gamification"]["completed_quests"] + 1)

    def test_append_same_dataset_does_not_award_again(self):
        path = "/api/v1/employees/E0001/career"
        before = self.client.get(path, headers=self.headers).json()["gamification"]
        with patch.object(importer, "DB_PATH", self.path):
            imported = importer.append_dataset(importer.DATASET)
        self.assertEqual(imported["history_added"], 0)
        self.assertEqual(self.client.get(path, headers=self.headers).json()["gamification"], before)


if __name__ == "__main__":
    unittest.main()
