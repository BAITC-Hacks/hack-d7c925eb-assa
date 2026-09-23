from pathlib import Path
import subprocess
import sys
import unittest

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
subprocess.run([sys.executable, str(ROOT / "backend" / "scripts" / "import_dataset.py")], check=True)

from backend.app.main import app  # noqa: E402


class ApiTest(unittest.TestCase):
    client = TestClient(app)

    def test_health_and_employee_list(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        self.assertEqual(len(self.client.get("/api/v1/employees").json()), 200)

    def test_recommendations_respect_rules_and_explain_score(self):
        payload = self.client.get("/api/v1/employees/E0001/career").json()
        self.assertLessEqual(len(payload["recommendations"]), 3)
        for item in payload["recommendations"]:
            self.assertEqual(len(item["components"]), 5)
            self.assertEqual(item["score"], sum(item["components"].values()))

    def test_completion_changes_expected_not_confirmed_level(self):
        before = self.client.get("/api/v1/employees/E0001/career").json()
        if not before["recommendations"]:
            self.skipTest("Profile has no eligible recommendations")
        event_id = before["recommendations"][0]["event_id"]
        response = self.client.post(f"/api/v1/employees/E0001/events/{event_id}/complete")
        self.assertEqual(response.status_code, 200)
        after = response.json()["career"]
        before_levels = {item["skill_id"]: item["current_level"] for item in before["gaps"]}
        self.assertTrue(any(item["expected_level"] > before_levels.get(item["skill_id"], item["current_level"]) for item in after["gaps"]))
        self.assertTrue(all(item["current_level"] == before_levels.get(item["skill_id"], item["current_level"]) for item in after["gaps"]))


if __name__ == "__main__":
    unittest.main()
