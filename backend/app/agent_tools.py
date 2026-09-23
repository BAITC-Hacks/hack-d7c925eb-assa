"""Read-only tools. Identity is injected by the server, never accepted from the model."""
from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .auth import Session, require_hr
from .database import connect
from .recommendation import career_payload, recommend, hr_summary


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Find(Empty):
    max_minutes: int | None = Field(ge=1, le=10000)
    event_format: Literal['self_paced', 'online', 'offline', 'hybrid'] | None


class Simulate(Empty):
    event_ids: list[str] = Field(max_length=3)


class Present(Empty):
    kind: Literal['level', 'skill_map', 'route', 'next_step', 'hr_gaps', 'hr_coverage', 'hr_events', 'skill_guide', 'comparison', 'explanation', 'clarification']


class Events(Empty):
    event_ids: list[str] = Field(min_length=1, max_length=2)


class Clarify(Empty):
    question: str = Field(min_length=1, max_length=300)


class Guide(Empty):
    skill_id: str = Field(pattern=r'^SK_[A-Z0-9_]+$', max_length=80)


SCHEMAS = {
    'get_my_context': (Empty, 'Get own career goal, skill requirements and summarized participation. No employee ID argument.'),
    'find_development_options': (Find, 'Rank eligible activities. Pass null to clear a time/format constraint. Never invent events.'),
    'simulate_route': (Simulate, 'Preview up to three recommended activities without writing progress. Requires find_development_options first.'),
    'get_skill_guide': (Guide, 'Read a skill definition and a clearly labelled educational exercise. Requires get_my_context first.'),
    'present_artifact': (Present, 'Finish by publishing a validated visual result and its grounded explanation. Requires the relevant preceding tools.'),
    'get_team_gaps': (Empty, 'HR only: deficits of the authorized department.'),
    'get_coverage_gaps': (Empty, 'HR only: why development recommendations are unavailable in the authorized department.'),
    'get_team_participation': (Empty, 'HR only: participation counts by activity in the authorized department.'),
    'explain_options': (Events, 'Explain or compare one or two real catalog activities using current eligibility, score and history. IDs must come from context or search.'),
    'ask_clarification': (Clarify, 'Ask one short clarification when the task or selected activity is ambiguous. No factual claims.'),
}


def definitions(role: str) -> list[dict]:
    names = ['get_my_context', 'find_development_options', 'simulate_route', 'get_skill_guide', 'present_artifact', 'explain_options', 'ask_clarification']
    if role == 'hr':
        names += ['get_team_gaps', 'get_coverage_gaps', 'get_team_participation']
    result = []
    for name in names:
        schema, description = SCHEMAS[name]
        parameters = schema.model_json_schema()
        parameters.pop('title', None)
        result.append({'type': 'function', 'name': name, 'description': description, 'parameters': parameters, 'strict': True})
    return result


class AgentTools:
    def __init__(self, session: Session):
        self.session = session
        with connect() as db:
            self.career = career_payload(db, session.employee_id)
        if not self.career:
            raise ValueError('Профиль отсутствует')
        self.context_read = False
        self.options: dict | None = None
        self.simulation: list[dict] | None = None
        self.team: dict | None = None
        self.guide: dict | None = None
        self.artifact: dict | None = None
        self.answer = ''
        self.sources: list[dict] = []
        self.comparison: list[dict] | None = None

    def execute(self, name: str, arguments: dict) -> dict:
        if name in {'get_team_gaps', 'get_coverage_gaps', 'get_team_participation'}:
            require_hr(self.session)
        if name not in {d['name'] for d in definitions(self.session.role)}:
            raise ValueError('Инструмент недоступен для этой роли')
        data = SCHEMAS[name][0].model_validate(arguments)
        return getattr(self, name)(**data.model_dump())

    def get_my_context(self) -> dict:
        self.context_read = True
        c = self.career
        # No name, department, manager ID or raw participation is sent to the provider.
        return {'role': c['employee']['role'], 'grade': c['employee']['grade'], 'target': c['target'],
                'skills': c['gaps'], 'progress': c['progress'],
                'history_statuses': dict(Counter(h['status'] for h in c['history'])),
                'history_window': 'Последние 30 записей; ranking использует всю историю',
                'constraints': {'max_minutes': self.session.max_minutes, 'event_format': self.session.event_format}}

    def ask_clarification(self, question: str) -> dict:
        # Clarification is visibly separate from a verified factual answer.
        self.artifact = {'kind': 'clarification'}
        self.answer = question
        return {'clarification': True}

    def explain_options(self, event_ids: list[str]) -> dict:
        if len(set(event_ids)) != len(event_ids):
            raise ValueError('Выберите разные активности')
        self.context_read = True
        self.comparison = []
        with connect() as db:
            employee = db.execute('SELECT * FROM employees WHERE employee_id=?', (self.session.employee_id,)).fetchone()
            allowed = recommend(db, employee, self.career['target'], self.career['gaps'], limit=None,
                                max_minutes=self.session.max_minutes, event_format=self.session.event_format)
            for event_id in event_ids:
                event = db.execute('SELECT event_id, title FROM events WHERE event_id=?', (event_id,)).fetchone()
                if event is None:
                    raise ValueError('Нет такой активности')
                item = next((r for r in allowed if r['event_id'] == event_id), None)
                if item:
                    self.comparison.append({**item, 'eligible': True})
                else:
                    reasons = []
                    if not db.execute('SELECT 1 FROM event_targets WHERE event_id=? AND role=? AND grade=?', (event_id, employee['role'], employee['grade'])).fetchone():
                        reasons.append('Не предназначена для подтверждённых роли и грейда')
                    raw = db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
                    if self.session.max_minutes and raw['duration_hours'] * 60 > self.session.max_minutes:
                        reasons.append('Не укладывается в ограничение времени')
                    if self.session.event_format and raw['format'] not in ({'online', 'self_paced'} if self.session.event_format == 'online' else {self.session.event_format}):
                        reasons.append('Не подходит выбранный формат')
                    if raw['mandatory']:
                        reasons.append('Обязательное событие не входит в добровольный маршрут')
                    if event_id != 'EV_036' and db.execute("SELECT 1 FROM activity_records WHERE employee_id=? AND event_id=? AND status='completed'", (self.session.employee_id, event_id)).fetchone():
                        reasons.append('Уже завершена')
                    if db.execute('''SELECT 1 FROM event_prerequisites p LEFT JOIN employee_skills s
                        ON s.skill_id=p.skill_id AND s.employee_id=? WHERE p.event_id=? AND COALESCE(s.level,0)<p.required_level''', (self.session.employee_id, event_id)).fetchone():
                        reasons.append('Требуется подтверждение предварительных навыков')
                    if not reasons:
                        reasons.append('Не сокращает оставшийся разрыв либо нет доступной сессии')
                    self.comparison.append({**dict(event), 'eligible': False, 'explanation': '. '.join(reasons) + '.'})
        return {'items': self.comparison}

    def find_development_options(self, max_minutes: int | None, event_format: str | None) -> dict:
        self.session.max_minutes, self.session.event_format = max_minutes, event_format
        reasons: Counter = Counter()
        with connect() as db:
            employee = db.execute('SELECT * FROM employees WHERE employee_id=?', (self.session.employee_id,)).fetchone()
            items = recommend(db, employee, self.career['target'], self.career['gaps'],
                              max_minutes=max_minutes, event_format=event_format, exclusions=reasons)
        self.options = {'recommendations': items, 'max_minutes': max_minutes, 'event_format': event_format,
                        'exclusions': [{'reason': k, 'events': v} for k, v in reasons.most_common()]}
        self.simulation = None
        self.artifact = None
        return self.options

    def simulate_route(self, event_ids: list[str]) -> dict:
        if self.options is None:
            raise ValueError('Сначала получите допустимые активности')
        allowed = {e['event_id']: e for e in self.options['recommendations']}
        if len(event_ids) != len(set(event_ids)) or any(e not in allowed for e in event_ids):
            raise ValueError('Можно моделировать только уникальные допустимые активности')
        levels = {s['skill_id']: s['expected_level'] for s in self.career['gaps'] if s['expected_level'] is not None}
        steps = []
        with connect() as db:
            for event_id in event_ids:
                changes = []
                for gain in db.execute('SELECT * FROM event_skill_gains WHERE event_id=?', (event_id,)):
                    if gain['skill_id'] not in levels:
                        continue
                    old = levels[gain['skill_id']]
                    new = max(old, min(5, gain['max_level'], old + gain['gain']))
                    levels[gain['skill_id']] = new
                    if new > old:
                        changes.append({'skill_id': gain['skill_id'], 'before': old, 'after': new})
                steps.append({'event_id': event_id, 'title': allowed[event_id]['title'], 'changes': changes})
        self.simulation = steps
        return {'steps': steps, 'remaining': [{'skill_id': g['skill_id'], 'name': g['name'],
                'expected': levels.get(g['skill_id']), 'required': g['required_level']}
                for g in self.career['gaps'] if g['skill_id'] not in levels or levels[g['skill_id']] < g['required_level']],
                'note': 'Прогноз, не подтверждённая оценка. Грейд не меняется.'}

    def get_skill_guide(self, skill_id: str) -> dict:
        if not self.context_read:
            raise ValueError('Сначала получите контекст')
        skill = next((s for s in self.career['gaps'] if s['skill_id'] == skill_id), None)
        if skill is None:
            raise ValueError('Навык отсутствует среди требований текущей цели')
        exercises = {
            'SK_SYSTEM_DESIGN': 'Спроектируйте сервис коротких ссылок: API, хранение, кэш и поведение при отказе. Объясните один компромисс между простотой и масштабированием.',
            'SK_PUBLIC_SPEAKING': 'Подготовьте трёхминутное объяснение своего проекта: проблема, решение, результат. Запишите выступление и проверьте, понятна ли главная мысль.',
            'SK_PYTHON': 'Возьмите небольшой обработчик данных, добавьте обработку неверного ввода и напишите тест на граничный случай. Объясните выбор структуры данных.',
        }
        example = exercises.get(skill_id, f"Выберите небольшую рабочую задачу, где нужен навык «{skill['name']}». Опишите решение и попросите коллегу дать обратную связь по одному конкретному критерию.")
        self.guide = {'skill': skill, 'example': example, 'label': 'Учебный пример, не корпоративный курс; выполнение не начисляет уровень'}
        return self.guide

    def get_team_gaps(self) -> dict:
        require_hr(self.session)
        with connect() as db:
            self.team = hr_summary(db, self.session.department)
        return {'top_gaps': self.team['top_gaps'], 'employee_count': self.team['employee_count'],
                'participation': self.team['participation']}

    def get_coverage_gaps(self) -> dict:
        self.get_team_gaps()
        # The model sees aggregated reasons only; identities remain inside the app.
        reasons = Counter(r['reason'] for p in self.team['employees_without_recommendations'] for r in p['reasons'])
        return {'without_recommendations': len(self.team['employees_without_recommendations']), 'reasons': dict(reasons)}

    def get_team_participation(self) -> dict:
        self.get_team_gaps()
        return {'events': self.team['events'], 'participation': self.team['participation']}

    def present_artifact(self, kind: str) -> dict:
        if kind.startswith('hr_'):
            require_hr(self.session)
            if self.team is None:
                raise ValueError('Сначала получите сводку команды')
            self.artifact = {'kind': kind, 'hr': self.team}
            count = len(self.team['employees_without_recommendations'])
            top = self.team['top_gaps']
            self.answer = (f"В разрешённом отделе {self.team['employee_count']} сотрудников. "
                + (f"Чаще всего не хватает навыка {top[0]['name']}: {top[0]['employees']} сотрудников. " if top else 'Дефициты не найдены. ')
                + f"Без подходящего следующего шага: {count}. Причины показаны на карточках. Проверьте пробелы каталога и предварительные требования; участие не является оценкой результативности человека.")
            self.sources = [{'id': 'team', 'label': 'Дефициты отдела', 'view': 'hr_gaps'}, {'id': 'coverage', 'label': 'Покрытие рекомендациями', 'view': 'hr_coverage'}]
            if kind == 'hr_events':
                p = self.team['participation']
                self.answer = f"В отделе {p['total_records']} записей участия, завершено {p['completed']} ({p['completion_rate']}%). Повторные участия учитываются отдельно. Это не оценка результативности сотрудников."
                self.sources = [{'id': 'participation', 'label': 'Участие по активностям', 'view': 'hr_events'}]
        else:
            if not self.context_read:
                raise ValueError('Сначала получите контекст')
            if kind in {'route', 'next_step'} and (self.options is None or self.simulation is None):
                raise ValueError('Сначала подберите активности и проверьте маршрут')
            if kind == 'skill_guide' and self.guide is None:
                raise ValueError('Сначала получите определение навыка')
            c = self.career
            self.artifact = {'kind': kind, 'career': c, 'options': self.options, 'simulation': self.simulation, 'guide': self.guide}
            if kind in {'explanation', 'comparison'}:
                if not self.comparison:
                    raise ValueError('Сначала выберите активности для объяснения')
                self.artifact['comparison'] = self.comparison
            self.sources = [{'id': 'profile', 'label': 'Профиль и оценка навыков', 'view': 'level'},
                            {'id': 'requirements', 'label': 'Требования к цели', 'view': 'skill_map'}]
            self.answer = f"Сейчас: {c['employee']['role']} · {c['employee']['grade']}. "
            self.answer += f"Цель: {c['target']['role']} · {c['target']['grade']}. " if c['target']['source'] == 'career_goal' else 'Цель пока не задана: показываю требования текущей роли. '
            p = c['progress']
            self.answer += f"Подтверждено {p['confirmed_ready']} из {p['total_required']} требований. "
            if p['unknown_required']:
                self.answer += f"Нет оценки для {p['unknown_required']} требований; сначала нужна оценка этих навыков. "
            if kind in {'route', 'next_step'}:
                recs = self.options['recommendations']
                if recs:
                    self.answer += f"Следующий шаг — {recs[0]['title']}. {recs[0]['explanation']}"
                    self.sources += [{'id': recs[0]['event_id'], 'label': recs[0]['title'], 'view': 'next_step'},
                                     {'id': 'history', 'label': 'История участия', 'view': 'history'}]
                else:
                    self.answer += 'Подходящих активностей при этих условиях нет. '
                    self.answer += ' '.join(r['reason'] + '.' for r in self.options['exclusions'])
                    self.answer += ' Можно изменить время или формат. Короткий учебный пример не заменяет завершение активности.'
            if kind == 'skill_guide':
                self.answer = f"{self.guide['skill']['name']}: {self.guide['skill']['description']}\n\nУчебный пример: {self.guide['example']}\n\n{self.guide['label']}"
                self.sources = [{'id': self.guide['skill']['skill_id'], 'label': self.guide['skill']['name'], 'view': 'skill_map'}]
            if kind in {'explanation', 'comparison'}:
                self.answer = '\n\n'.join(f"{r['title']}: {r['explanation']}" for r in self.comparison)
                if len(self.comparison) == 2:
                    eligible = [r for r in self.comparison if r['eligible']]
                    if eligible:
                        best = max(eligible, key=lambda r: r['score'])
                        self.answer += f"\n\nПри текущих условиях предпочтительнее {best['title']}: оценка соответствия {best['score']}/100. Это не вероятность повышения."
                self.sources += [{'id': r['event_id'], 'label': r['title'], 'view': 'next_step'} for r in self.comparison]
        # Do not return raw employee/team data to the model on this final tool.
        return {'published': kind, 'source_ids': [s['id'] for s in self.sources]}
