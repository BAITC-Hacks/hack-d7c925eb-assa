import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "analyze_dataset.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.summary = json.loads(
            (ROOT / "analysis" / "summary.json").read_text(encoding="utf-8")
        )

    def test_expected_dataset_shape_and_valid_links(self) -> None:
        self.assertTrue(self.summary["validation"]["passed"])
        self.assertEqual(self.summary["validation"]["issue_count"], 0)
        self.assertEqual(
            self.summary["dataset"],
            {
                "skills": 60,
                "role_profiles": 32,
                "employees": 200,
                "events": 40,
                "activity_records": 2743,
            },
        )

    def test_recommendations_follow_catalog_rules(self) -> None:
        events_doc = json.loads(
            (ROOT / "career_quest_dataset" / "events.json").read_text(encoding="utf-8")
        )
        events = {event["event_id"]: event for event in events_doc["events"]}
        with (ROOT / "analysis" / "recommendations.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))

        per_employee: dict[str, list[int]] = {}
        for row in rows:
            event = events[row["event_id"]]
            self.assertFalse(event["mandatory"])
            self.assertIn(row["target_role"], event["target_roles"])
            self.assertIn(row["target_grade"], event["target_grades"])
            per_employee.setdefault(row["employee_id"], []).append(int(row["rank"]))

        self.assertTrue(all(len(ranks) <= 5 for ranks in per_employee.values()))
        self.assertTrue(all(ranks == list(range(1, len(ranks) + 1)) for ranks in per_employee.values()))


if __name__ == "__main__":
    unittest.main()
