import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.app import database
from backend.app.auth import SESSIONS
from backend.scripts import import_dataset as importer
from backend.app.main import app

class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.db'
        self.env = patch.dict(os.environ, {'CQ_MODE': 'demo', 'CQ_ALLOW_EXTERNAL_AI': 'false'})
        self.env.start()
        self.db_patch = patch.object(database, 'DB_PATH', self.path)
        self.db_patch.start()
        with patch.object(importer, 'DB_PATH', self.path):
            importer.import_dataset()
        SESSIONS.clear()
        self.client = TestClient(app)
        login = self.client.post('/api/v1/session', json={})
        self.headers = {'Authorization': 'Bearer ' + login.json()['token']}

    def tearDown(self):
        self.client.close()
        self.db_patch.stop()
        self.env.stop()
        SESSIONS.clear()
        self.tmp.cleanup()

    def ask(self, message, **kwargs):
        return self.client.post('/api/v1/assistant', headers=self.headers, json={'message': message, **kwargs})

    def test_identity_and_scope(self):
        self.assertEqual(self.client.get('/api/v1/employees').status_code, 401)
        self.assertEqual(len(self.client.get('/api/v1/employees', headers=self.headers).json()), 1)
        self.assertEqual(self.client.get('/api/v1/employees/E0002/career', headers=self.headers).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/hr/summary', headers=self.headers).status_code, 403)
        self.assertEqual(self.ask('Покажи E0002').status_code, 403)
        self.assertEqual(self.client.post('/api/v1/session', json={}, headers={'Origin': 'https://evil.example'}).status_code, 403)

    def test_map_and_constraints(self):
        result = self.ask('Покажи карту навыков').json()
        self.assertEqual(result['artifact']['kind'], 'skill_map')
        career = result['artifact']['career']
        with database.connect() as db:
            total = db.execute('select count(*) from role_skill_requirements where role=? and grade=?', (career['target']['role'], career['target']['grade'])).fetchone()[0]
        self.assertEqual(career['progress']['total_required'], total)
        limited = self.ask('У меня 30 минут').json()
        self.assertEqual(limited['constraints']['max_minutes'], 30)
        self.assertTrue(all(r['duration_hours'] <= .5 for r in limited['artifact']['options']['recommendations']))
        self.assertEqual(self.ask('Построй маршрут').json()['constraints']['max_minutes'], 30)
        self.assertIsNone(self.ask('Построй маршрут без ограничений', reset_constraints=True).json()['constraints']['max_minutes'])

    def test_completion_idempotent_and_capped(self):
        before = self.client.get('/api/v1/employees/E0001/career', headers=self.headers).json()
        self.assertTrue(before['recommendations'])
        event = before['recommendations'][0]['event_id']
        with database.connect() as db:
            db.execute('update event_skill_gains set gain=20, max_level=3 where event_id=?', (event,))
        url = f'/api/v1/employees/E0001/events/{event}/complete'
        first = self.client.post(url, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        second = self.client.post(url, headers=self.headers).json()
        self.assertTrue(second['already_completed'])
        self.assertEqual(first.json()['career']['progress'], second['career']['progress'])
        for skill in second['career']['gaps']:
            self.assertLessEqual(skill['expected_level'], max(skill['current_level'], 3))
        self.assertEqual(self.client.post('/api/v1/employees/E0001/events/EV_001/complete', headers=self.headers).status_code in (200,409), True)

    def test_hr_scoped(self):
        login = self.client.post('/api/v1/session', json={'role':'hr'}).json()
        result = self.client.get('/api/v1/hr/summary', headers={'Authorization':'Bearer '+login['token']}).json()
        with database.connect() as db:
            expected = db.execute('select count(*) from employees where department=?',(login['department'],)).fetchone()[0]
        self.assertEqual(result['employee_count'], expected)
        self.assertLess(expected, 200)

    def test_model_tools_and_fallback(self):
        def tool(name, args, i):
            import json
            return {'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':str(i)}
        outputs = [
            {'output':[tool('get_my_context',{},1),tool('find_development_options',{'max_minutes':None,'event_format':None},2)]},
            {'output':[tool('simulate_route',{'event_ids':[]},3),tool('present_artifact',{'kind':'route'},4)]},
        ]
        with patch('backend.app.assistant.external_enabled', return_value=True), patch('backend.app.assistant.model_step',new=AsyncMock(side_effect=outputs)):
            result=self.ask('Построй маршрут').json()
        self.assertEqual(result['mode'],'agent')
        self.assertEqual(len(result['trace']),4)
        with patch('backend.app.assistant.external_enabled',return_value=True),patch('backend.app.assistant.model_step',new=AsyncMock(side_effect=TimeoutError())):
            result=self.ask('Покажи карту навыков').json()
        self.assertEqual(result['mode'],'fallback')
        self.assertEqual(result['artifact']['kind'],'skill_map')

if __name__ == '__main__':
    unittest.main()
