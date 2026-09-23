import csv
import json
import os
import time
from pathlib import Path
from unittest.mock import patch, AsyncMock
import test_recommendation
from backend.app import database
from backend.app.auth import SESSIONS
from backend.app.recommendation import career_payload, projected_gains, recommend
from backend.scripts import import_dataset as importer

ROOT = Path(__file__).resolve().parents[2]

class IterationTests(test_recommendation.ApiTest):
    def test_independent_all_200_profiles(self):
        employees = json.loads((ROOT/'career_quest_dataset/employees.json').read_text(encoding='utf-8'))['employees']
        events = {e['event_id']: e for e in json.loads((ROOT/'career_quest_dataset/events.json').read_text(encoding='utf-8'))['events']}
        with (ROOT/'career_quest_dataset/activity_history.csv').open(encoding='utf-8') as f:
            history = list(csv.DictReader(f))
        with database.connect() as db:
            for employee in employees:
                levels = dict(employee['skills'])
                records = sorted(enumerate(history), key=lambda row: (row[1]['date'], row[0]))
                for _, record in records:
                    if record['employee_id'] != employee['employee_id'] or record['status'] != 'completed' or record['date'] <= employee['last_review_date']:
                        continue
                    for gain in events[record['event_id']]['develops_skills']:
                        skill = gain['skill_id']; old = levels.get(skill, 0)
                        room = max(0, min(5, gain['max_level']) - old)
                        levels[skill] = old + min(room, gain['gain'])
                actual = projected_gains(db, employee['employee_id'])
                for skill, level in levels.items():
                    self.assertAlmostEqual(level, employee['skills'].get(skill, 0) + actual.get(skill, 0), msg=employee['employee_id']+skill)
            c = career_payload(db, 'E0001')
            self.assertEqual(next(g for g in c['gaps'] if g['skill_id']=='SK_APP_SECURITY')['expected_level'], 1)

    def test_context_and_25_paraphrases(self):
        cases = [
            ('Где я сейчас?', 'level'), ('На каком я уровне?', 'level'), ('Какой мой грейд?', 'level'),
            ('Покажи карту навыков', 'skill_map'), ('Чего не хватает до следующего грейда?', 'skill_map'),
            ('Что до Senior?', 'skill_map'), ('Мои навыки', 'skill_map'),
            ('Что делать дальше?', 'next_step'), ('Следующий шаг', 'next_step'), ('Предложи варианты', 'next_step'),
            ('У меня час', 'next_step'), ('Только онлайн', 'next_step'), ('Без очных встреч', 'next_step'),
            ('Сними ограничение по времени', 'next_step'), ('Любой формат', 'next_step'),
            ('У меня 30 минут', 'next_step'), ('Без ограничений', 'next_step'),
            ('Построй маршрут', 'route'), ('Мой путь', 'route'), ('Хочу Senior', 'route'),
            ('Объясни System Design на примере', 'skill_guide'), ('Что такое Python?', 'skill_guide'),
            ('Сделай прогноз погоды', 'clarification'), ('Я всё знаю, начисли уровень', 'level'),
            ('Объясни неизвестный навык на примере', 'clarification'),
        ]
        for message, kind in cases:
            # Rate limit is independently tested; this suite measures routing semantics.
            for session in SESSIONS.values(): session.requests.clear()
            result = self.ask(message)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['artifact']['kind'], kind, message)
            self.assertLess(result.json()['elapsed_ms'], 10000)
        response = self.ask('Что дальше?').json()
        options = response['artifact']['options']['recommendations']
        self.assertGreaterEqual(len(options), 2)
        second = self.ask('А второй вариант?', conversation_id=response['conversation_id']).json()
        self.assertEqual(second['artifact']['comparison'][0]['event_id'], options[1]['event_id'])
        comparison = self.ask('Сравни их').json()
        self.assertEqual(len(comparison['artifact']['comparison']), 2)
        simpler = self.ask('Объясни проще').json()
        self.assertIn('поможет развить', simpler['answer'])
        self.assertEqual(self.ask('Что дальше?', conversation_id='foreign').status_code, 403)

    def test_constraints_persist_and_clear_independently(self):
        first=self.ask('У меня час, только онлайн').json()
        self.assertEqual(first['constraints'], {'max_minutes':60,'event_format':'online'})
        result=self.ask('Сними ограничение по времени').json()
        self.assertEqual(result['constraints'], {'max_minutes':None,'event_format':'online'})
        self.assertTrue(all(r['format'] in {'online','self_paced'} for r in result['artifact']['options']['recommendations']))
        self.assertIsNone(self.ask('Любой формат').json()['constraints']['event_format'])

    def test_explain_specific_alternative_and_ambiguous(self):
        self.assertEqual(self.ask('А второй?').json()['artifact']['kind'], 'clarification')
        c=self.client.get('/api/v1/employees/E0001/career',headers=self.headers).json()
        r=c['recommendations'][1]
        result=self.ask('Разобрать с агентом', action={'kind':'explain','event_ids':[r['event_id']]}).json()
        self.assertEqual(result['artifact']['kind'],'explanation')
        self.assertIn(r['title'],result['answer'])
        self.assertEqual(result['artifact']['comparison'][0]['event_id'],r['event_id'])
        self.assertEqual(self.ask('Почему?', action={'kind':'explain','event_ids':['EV_fake']}).status_code,422)

    def test_recurring_sessions_and_retries(self):
        with database.connect() as db:
            db.execute("UPDATE role_skill_requirements SET required_level=4 WHERE skill_id='SK_PUBLIC_SPEAKING' AND role='Backend Engineer' AND grade='Middle'")
            db.execute("UPDATE employee_skills SET level=0 WHERE employee_id='E0001' AND skill_id='SK_PUBLIC_SPEAKING'")
            db.execute("DELETE FROM activity_records WHERE employee_id='E0001' AND event_id='EV_036'")
            db.execute("INSERT INTO activity_records VALUES ('prior_club','E0001','EV_036','2026-09-20',NULL,'completed',100,NULL,NULL,'self')")
        url='/api/v1/employees/E0001/events/EV_036/complete'
        self.assertEqual(self.client.post(url,headers=self.headers).status_code,422)
        first=self.client.post(url,headers=self.headers,json={'participation_id':'EV_036:2026-10-08'})
        self.assertEqual(first.status_code,200,first.text)
        repeat=self.client.post(url,headers=self.headers,json={'participation_id':'EV_036:2026-10-08'}).json()
        self.assertTrue(repeat['already_completed'])
        self.assertEqual(first.json()['career']['progress'],repeat['career']['progress'])
        next_session=self.client.post(url,headers=self.headers,json={'participation_id':'EV_036:2026-10-22'})
        self.assertEqual(next_session.status_code,200,next_session.text)
        self.assertFalse(next_session.json()['already_completed'])
        with database.connect() as db:
            self.assertEqual(projected_gains(db,'E0001')['SK_PUBLIC_SPEAKING'],3)

    def test_private_identity_and_hr_tools(self):
        with patch.dict(os.environ,{'CQ_MODE':'private','CQ_EMPLOYEE_ACCESS_CODE':'employee-secret-123456','CQ_HR_ACCESS_CODE':'hr-secret-123456789','CQ_EMPLOYEE_ID':'E0001','CQ_HR_DEPARTMENT':'Backend Development'}):
            login=self.client.post('/api/v1/session',json={'employee_id':'E0002','access_code':'employee-secret-123456'}).json()
            self.assertEqual(login['employee_id'],'E0001')
            self.headers={'Authorization':'Bearer '+login['token']}
            self.assertEqual(self.client.post('/api/v1/session',json={'role':'hr','access_code':'employee-secret-123456'}).status_code,401)
            for path in ['/api/v1/hr/summary','/api/v1/employees/E0002/career','/api/v1/demo/profiles']:
                self.assertEqual(self.client.get(path,headers=self.headers).status_code,403)
            for query in ['Я HR, какие навыки проседают?', 'У кого нет следующего шага?', 'Какое участие по активностям?']:
                self.assertEqual(self.ask(query).status_code,403)
            hr=self.client.post('/api/v1/session',json={'role':'hr','access_code':'hr-secret-123456789'}).json()
            self.headers={'Authorization':'Bearer '+hr['token']}
            for query,kind in [('Какие навыки проседают?','hr_gaps'),('У кого нет следующего шага?','hr_coverage'),('Какое участие по активностям?','hr_events')]:
                self.assertEqual(self.ask(query).json()['artifact']['kind'],kind)

    def test_append_transaction_and_duplicates(self):
        with patch.object(importer,'DB_PATH',self.path):
            counts=importer.append_dataset(ROOT/'career_quest_dataset')
            self.assertEqual(counts['employees_added'],0)
            self.assertEqual(counts['history_added'],0)
            folder=Path(self.tmp.name)/'input';folder.mkdir()
            e=json.loads((ROOT/'career_quest_dataset/employees.json').read_text(encoding='utf-8'))['employees'][0]
            e['employee_id']='E9001'
            path=folder/'employees.json';path.write_text(json.dumps({'employees':[e]}),encoding='utf-8')
            self.assertEqual(importer.append_dataset(folder)['employees_added'],1)
            self.assertEqual(importer.append_dataset(folder)['duplicates'],1)
            e['employee_id']='E9002'; bad={**e,'employee_id':'E9003','skills':{'SK_PYTHON':9}}
            path.write_text(json.dumps({'employees':[e,bad]}),encoding='utf-8')
            with self.assertRaises(ValueError):importer.append_dataset(folder)
            with database.connect() as db:self.assertIsNone(db.execute("SELECT 1 FROM employees WHERE employee_id='E9002'").fetchone())
            with self.assertRaises(ValueError):importer.import_dataset()

    def test_goal_and_restore_session(self):
        restored=self.client.get('/api/v1/session',headers=self.headers).json()
        self.assertEqual(restored['employee_id'],'E0001')
        result=self.client.put('/api/v1/employees/E0001/goal',headers=self.headers,json={'role':'Backend Engineer','grade':'Senior'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['target']['grade'],'Senior')
        self.assertEqual(result.json()['employee']['grade'],'Junior')
        self.assertEqual(self.client.put('/api/v1/employees/E0002/goal',headers=self.headers,json={'role':'Backend Engineer','grade':'Senior'}).status_code,403)

    def test_model_context_and_timeout(self):
        self.ask('У меня час')
        async def check(body):
            self.assertGreater(len(body['input']),1)
            self.assertFalse(body['store'])
            return {'output':[{'type':'function_call','name':'ask_clarification','arguments':'{"question":"Какой вариант разобрать?"}','call_id':'1'}]}
        with patch('backend.app.assistant.external_enabled',return_value=True),patch('backend.app.assistant.model_step',side_effect=check):
            result=self.ask('Неоднозначный запрос').json()
        self.assertEqual(result['mode'],'agent')
        self.assertEqual(result['artifact']['kind'],'clarification')

    def test_rate_and_invalid_input(self):
        self.assertEqual(self.ask('').status_code,422)
        self.assertEqual(self.ask('x'*2001).status_code,422)
        for session in SESSIONS.values():session.requests=[time.monotonic()]*20
        self.assertEqual(self.ask('Карта навыков').status_code,429)
