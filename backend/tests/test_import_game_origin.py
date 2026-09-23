import csv
import unittest
from pathlib import Path
from unittest.mock import patch

import test_recommendation
from backend.app import database
from backend.scripts import import_dataset as importer


class ImportGameOriginTests(unittest.TestCase):
    setUp = test_recommendation.ApiTest.setUp
    tearDown = test_recommendation.ApiTest.tearDown

    def import_rows(self, rows):
        folder = Path(self.tmp.name) / 'append'
        folder.mkdir(exist_ok=True)
        with (folder / 'activity_history.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with patch.object(importer, 'DB_PATH', self.path):
            return importer.append_dataset(folder)

    def test_reserved_origin_rejects_new_future_reward_and_rolls_back_valid_row(self):
        before = self.client.get('/api/v1/employees/E0001/career', headers=self.headers).json()['gamification']
        valid = {
            'record_id': 'IMPORT_VALID', 'employee_id': 'E0001', 'event_id': 'EV_036',
            'date': '2026-09-17', 'due_date': '', 'status': 'completed',
            'completion_pct': 100, 'score': '', 'feedback_rating': '', 'assigned_by': 'self',
        }
        spoof = {**valid, 'record_id': 'IMPORT_SPOOF', 'date': '2026-10-08', 'assigned_by': 'career_quest'}
        with self.assertRaisesRegex(ValueError, 'career_quest зарезервирован для завершений в приложении'):
            self.import_rows([valid, spoof])
        with database.connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM activity_records WHERE record_id IN ('IMPORT_VALID', 'IMPORT_SPOOF')"
            ).fetchone()[0], 0)
        after = self.client.get('/api/v1/employees/E0001/career', headers=self.headers).json()['gamification']
        self.assertEqual(after, before)

    def test_identical_application_completion_can_be_reimported_as_duplicate(self):
        path = '/api/v1/employees/E0001/career'
        option = self.client.get(path, headers=self.headers).json()['recommendations'][0]
        response = self.client.post(
            f"/api/v1/employees/E0001/events/{option['event_id']}/complete",
            headers=self.headers, json={'participation_id': option['participation_id']},
        )
        self.assertEqual(response.status_code, 200, response.text)
        before = response.json()['career']['gamification']
        with database.connect() as db:
            row = db.execute(
                "SELECT * FROM activity_records WHERE employee_id='E0001' AND event_id=? AND assigned_by='career_quest'",
                (option['event_id'],),
            ).fetchone()
        self.assertIsNotNone(row)
        counts = self.import_rows([dict(row)])
        self.assertEqual(counts, {'employees_added': 0, 'history_added': 0, 'duplicates': 1})
        self.assertEqual(self.client.get(path, headers=self.headers).json()['gamification'], before)


if __name__ == '__main__':
    unittest.main()
