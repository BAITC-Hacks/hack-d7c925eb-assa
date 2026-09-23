"""Independent audit. Writes only under audit/; production source/DB untouched.
Run from repository root: python -m audit.probe
"""
import copy
import csv
import json
import os
import shutil
import sqlite3
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import database
from backend.scripts import import_dataset as importer
from backend.app.main import app
from backend.app.recommendation import career_payload, projected_gains

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audit'
FIX = OUT / 'fixture'
FIX.mkdir(exist_ok=True)
results = {}
for name in ('skills.json', 'events.json', 'employees.json', 'activity_history.csv'):
    shutil.copyfile(ROOT / 'career_quest_dataset' / name, FIX / name)
skills = json.loads((FIX / 'skills.json').read_text(encoding='utf-8'))
employees = json.loads((FIX / 'employees.json').read_text(encoding='utf-8'))
senior = next(p for p in skills['role_profiles'] if p['role'] == 'Backend Engineer' and p['grade'] == 'Senior')
conflict = copy.deepcopy(employees['employees'][0])
conflict.update(employee_id='E9001', full_name='Audit Conflict Profile', grade='Middle',
                career_goal={'target_role': 'Backend Engineer', 'target_grade': 'Senior'},
                skills={**senior['required_skills'], 'SK_SYSTEM_DESIGN': 2, 'SK_PUBLIC_SPEAKING': 0})
additional = copy.deepcopy(conflict)
additional.update(employee_id='E9002', full_name='Audit Additional Profile', career_goal=None)
employees['employees'].extend([conflict, additional])
(FIX / 'employees.json').write_text(json.dumps(employees, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'additional_profiles.json').write_text(json.dumps({'employees':[conflict, additional]}, ensure_ascii=False, indent=2), encoding='utf-8')
with (FIX / 'activity_history.csv').open('a', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    for i, date in enumerate(('2026-08-01', '2026-08-15', '2026-09-01')):
        writer.writerow([f'AUDIT_{i}', 'E9001', 'EV_036', date, '', 'no_show', 0, '', '', 'self'])

# Live service: read-only career/HR requests, temporary authentication sessions.
def live(path, data=None, token=None):
    headers = {'Content-Type':'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request('http://127.0.0.1:8000/api/v1'+path,
        data=None if data is None else json.dumps(data).encode(), headers=headers)
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=12) as response:
        body = json.load(response)
    return body, round((time.perf_counter()-start)*1000, 2)

try:
    config, _ = live('/config')
    login, _ = live('/session', {'employee_id':'E0001'})
    timings = []
    for _ in range(10):
        c, ms = live('/employees/E0001/career', token=login['token'])
        timings.append(ms)
    results['live'] = {'config':config, 'career':c, 'career_ms':timings}
    replies = []
    for message in ['Построй маршрут', 'У меня 30 минут', 'Построй маршрут без ограничений']:
        reply, ms = live('/assistant', {'message':message}, login['token'])
        replies.append({'message':message, 'ms':ms, 'reply':reply})
    results['live']['assistant'] = replies
    hrlogin, _ = live('/session', {'role':'hr'})
    hr, ms = live('/hr/summary', token=hrlogin['token'])
    with sqlite3.connect(ROOT/'backend/data/career_quest.db') as db:
        emp = db.execute('select count(*) from employees where department=?', (hrlogin['department'],)).fetchone()[0]
        counts = db.execute("select count(*),sum(a.status='completed') from activity_records a join employees e on e.employee_id=a.employee_id where e.department=?", (hrlogin['department'],)).fetchone()
    results['live_hr'] = {'summary':hr, 'ms':ms, 'independent_sql':{'employees':emp,'participation_total':counts[0],'completed':counts[1]}}
except Exception as exc:
    results['live_error'] = str(exc)

dbpath = OUT / 'isolated.db'
with patch.object(importer, 'DATASET', FIX), patch.object(importer, 'DB_PATH', dbpath):
    results['import'] = importer.import_dataset()

with patch.object(database, 'DB_PATH', dbpath), patch.dict(os.environ, {'CQ_MODE':'demo','CQ_ALLOW_EXTERNAL_AI':'false'}), TestClient(app) as client:
    def login(eid='E0001', role='employee'):
        r = client.post('/api/v1/session', json={'employee_id':eid, 'role':role})
        return {'Authorization': 'Bearer '+r.json()['token']}
    def getcareer(eid, headers):
        return client.get(f'/api/v1/employees/{eid}/career', headers=headers).json()
    def ask(message, headers):
        r = client.post('/api/v1/assistant', headers=headers, json={'message':message})
        return {'status':r.status_code, 'body':r.json()}
    h = login()
    before = getcareer('E0001', h)
    event = before['recommendations'][0]['event_id']
    path = f'/api/v1/employees/E0001/events/{event}/complete'
    first = client.post(path, headers=h)
    second = client.post(path, headers=h)
    reread = getcareer('E0001', login())
    results['normal'] = {'before':before, 'event':event, 'first':first.json(),
        'second_already_completed':second.json()['already_completed'],
        'new_session_same_progress':reread['progress']==first.json()['career']['progress'],
        'new_session_same_history':reread['history']==first.json()['career']['history']}
    results['explain_button'] = ask('Объясни следующий шаг и построй маршрут', h)
    results['format_filter'] = ask('Построй маршрут только онлайн', h)
    results['errors'] = {
        'unauthenticated': client.get('/api/v1/employees').status_code,
        'hr_as_employee': client.get('/api/v1/hr/summary', headers=h).status_code,
        'other_career': client.get('/api/v1/employees/E0002/career', headers=h).status_code,
        'other_completion': client.post('/api/v1/employees/E0002/events/EV_036/complete', headers=h).status_code,
        'other_chat': ask('Покажи E0002',h)['status'],
        'hr_chat': ask('Какие навыки проседают в команде?',h),
        'empty_chat': client.post('/api/v1/assistant', headers=h, json={'message':''}).status_code,
        'bad_minutes': ask('У меня 0 минут',h)['status'],
        'missing_event':client.post('/api/v1/employees/E0001/events/EV_999/complete',headers=h).status_code,
        'bad_profile':client.post('/api/v1/session',json={'employee_id':'INVALID'}).status_code,
        'foreign_origin':client.post('/api/v1/session',json={},headers={'Origin':'https://evil.example'}).status_code,
    }
    hr = login(role='hr')
    start = time.perf_counter()
    team = client.get('/api/v1/hr/summary', headers=hr).json()
    results['hr'] = {'summary':team, 'ms':round((time.perf_counter()-start)*1000,2),
                     'without_step_chat':ask('У кого нет следующего шага?',hr),
                     'participation_chat':ask('Покажи участие по активностям',hr)}
    results['demo_access'] = {'hr_session_without_code':client.get('/api/v1/hr/summary',headers=hr).status_code,
        'other_employee_new_session':client.get('/api/v1/employees/E0002/career',headers=login('E0002')).status_code}
    hc = login('E9001')
    conflict_before = getcareer('E9001',hc)
    results['conflict'] = {'fixture_note':'Constructed surrogate; original TZ profile not supplied',
                           'career':conflict_before, 'answer':ask('Построй маршрут',hc)}
    clubpath='/api/v1/employees/E9001/events/EV_036/complete'
    club1=client.post(clubpath,headers=hc).json()
    club2=client.post(clubpath,headers=hc).json()
    results['recurring']={'first':club1,'second':club2}
    results['additional_no_goal']=getcareer('E9002',login('E9002'))
    with database.connect() as db:
        # Dataset rule: completed after last review has not yet been reflected.
        affected=[]
        for emp in db.execute("select * from employees where employee_id not like 'E9%'").fetchall():
            levels={r['skill_id']:float(r['level']) for r in db.execute('select * from employee_skills where employee_id=?',(emp['employee_id'],))}
            initial=dict(levels)
            rows=db.execute("""select a.record_id,a.date,a.event_id,g.skill_id,g.gain,g.max_level from activity_records a
                join event_skill_gains g on g.event_id=a.event_id
                where a.employee_id=? and a.status='completed' and a.date>? and a.assigned_by!='career_quest'
                order by a.date,a.rowid,g.skill_id""",(emp['employee_id'],emp['last_review_date'])).fetchall()
            for r in rows:
                old=levels.get(r['skill_id'],0)
                levels[r['skill_id']]=max(old,min(5,r['max_level'],old+r['gain']))
            changes={k:{'before':initial.get(k,0),'expected_by_dataset':v} for k,v in levels.items() if v>initial.get(k,0)}
            if changes: affected.append({'employee_id':emp['employee_id'],'last_review_date':emp['last_review_date'],'changes':changes,'records':[dict(r) for r in rows]})
        results['post_review_history']={'affected_count':len(affected),'examples':affected[:4]}
        # Validate reported gains/components independently for every initial profile.
        failures=[]; count=0; target_grade_mismatches=[]
        for emp in db.execute('select * from employees').fetchall():
            c=career_payload(db,emp['employee_id'])
            gapmap={g['skill_id']:g for g in c['gaps']}
            for rec in c['recommendations']:
                count+=1
                assert rec['score']==sum(rec['components'].values())
                for gain in rec['covered_skills']:
                    rule=db.execute('select * from event_skill_gains where event_id=? and skill_id=?',(rec['event_id'],gain['skill_id'])).fetchone()
                    g=gapmap[gain['skill_id']]
                    expected=min(rule['gain'],max(0,rule['max_level']-g['expected_level']),g['expected_gap'])
                    if abs(expected-gain['gain'])>.001: failures.append([emp['employee_id'],rec['event_id'],gain,expected])
                if not db.execute('select 1 from event_targets where event_id=? and role=? and grade=?',(rec['event_id'],emp['role'],emp['grade'])).fetchone():
                    target_grade_mismatches.append({'employee_id':emp['employee_id'],'current_grade':emp['grade'],'target':c['target'],'event_id':rec['event_id']})
        results['gain_check']={'recommendations_checked':count,'failures':failures,'eligibility_current_profile_mismatches':target_grade_mismatches[:10], 'mismatch_count':len(target_grade_mismatches)}
        # Confirm level must never be reduced by a low activity cap, in an isolated DB.
        db.execute("update employee_skills set level=4 where employee_id='E9002' and skill_id='SK_SYSTEM_DESIGN'")
        db.execute("insert into activity_records values ('AUDIT_CAP','E9002','EV_005','2026-10-01',null,'completed',100,null,null,'career_quest')")
        results['cap_above_current']={'gain':projected_gains(db,'E9002')['SK_SYSTEM_DESIGN'],'expected_gain':0}
        results['all_skills_vs_map']={'stored_E0001':db.execute("select count(*) from employee_skills where employee_id='E0001'").fetchone()[0], 'displayed_E0001':len(before['gaps'])}
    # Protected mode uses fixed server identity, denies bad/absent role credentials.
    with patch.dict(os.environ,{'CQ_MODE':'private','CQ_EMPLOYEE_ACCESS_CODE':'audit-employee-123456789','CQ_HR_ACCESS_CODE':'audit-hr-123456789','CQ_EMPLOYEE_ID':'E0001'}):
        results['private_access']={
            'no_code_hr':client.post('/api/v1/session',json={'role':'hr'}).status_code,
            'employee_code_hr':client.post('/api/v1/session',json={'role':'hr','access_code':'audit-employee-123456789'}).status_code,
            'spoof_id':{k:v for k,v in client.post('/api/v1/session',json={'role':'employee','employee_id':'E0002','access_code':'audit-employee-123456789'}).json().items() if k!='token'}}

(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUT/'results.json'),'import':results['import'],'gain_check':results['gain_check'],'post_review_affected':results['post_review_history']['affected_count'],'errors':results['errors'],'private_access':results['private_access']},ensure_ascii=False,indent=2))
