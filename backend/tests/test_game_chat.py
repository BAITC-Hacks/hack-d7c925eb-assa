import json
import unittest
from unittest.mock import AsyncMock, patch

import test_recommendation
from backend.app.agent_tools import AgentTools, definitions
from backend.app.assistant import infer_local
from backend.app.auth import SESSIONS


class GameChatTests(unittest.TestCase):
    setUp = test_recommendation.ApiTest.setUp
    tearDown = test_recommendation.ApiTest.tearDown
    ask = test_recommendation.ApiTest.ask

    def test_local_rewards_are_grounded_and_skip_ranking_tools(self):
        for message in ['Мои достижения', 'Покажи награды', 'Сколько у меня XP?', 'Мои квесты', 'Мой игровой уровень']:
            with self.subTest(message=message):
                response = self.ask(message)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['artifact']['kind'], 'rewards')
                self.assertEqual([step['tool'] for step in result['trace']], ['get_my_context', 'present_artifact'])
                game = result['artifact']['career']['gamification']
                self.assertIn(f"Игровой уровень {game['level']} — {game['level_title']}", result['answer'])
                self.assertIn(f"{game['total_xp']} XP", result['answer'])
                self.assertIn(f"Открыто значков: {sum(b['unlocked'] for b in game['badges'])}", result['answer'])
                self.assertIn(f"Текущая серия обучения: {game['current_streak']} нед.", result['answer'])
                self.assertIn('не грейд', result['answer'])
                self.assertEqual(result['sources'][0]['view'], 'rewards')

    def test_reward_words_do_not_override_skill_or_grade_requests(self):
        for message, expected in [
            ('Мои навыки', 'skill_map'),
            ('Покажи навыки и XP', 'skill_map'),
            ('Какой мой грейд?', 'level'),
            ('На каком я уровне?', 'level'),
            ('Какой мой грейд и награды?', 'level'),
            ('Покажи достижения команды', 'hr_gaps'),
        ]:
            with self.subTest(message=message):
                self.assertEqual(infer_local(message), expected)

    def test_rewards_require_context_and_do_not_expand_provider_data(self):
        tools = AgentTools(next(iter(SESSIONS.values())))
        with self.assertRaises(ValueError):
            tools.execute('present_artifact', {'kind': 'rewards'})
        context = tools.execute('get_my_context', {})
        self.assertNotIn('gamification', context)
        self.assertNotIn('employee', context)
        published = tools.execute('present_artifact', {'kind': 'rewards'})
        self.assertEqual(published, {'published': 'rewards', 'source_ids': ['rewards', 'history']})
        self.assertNotIn('career', published)
        present = next(tool for tool in definitions('employee') if tool['name'] == 'present_artifact')
        self.assertIn('rewards', present['parameters']['properties']['kind']['enum'])

    def test_quest_actions_preserve_recommendation_workflows(self):
        recommendations = self.ask('Что дальше?').json()['artifact']['options']['recommendations']
        self.assertGreaterEqual(len(recommendations), 2)
        for message, kind, expected_tools in [
            ('Почему этот квест?', 'explanation', ['get_my_context', 'explain_options', 'present_artifact']),
            ('Сравни квесты', 'comparison', ['get_my_context', 'explain_options', 'present_artifact']),
            ('Следующий квест', 'next_step', ['get_my_context', 'find_development_options', 'simulate_route', 'present_artifact']),
            ('Построй маршрут квестов', 'route', ['get_my_context', 'find_development_options', 'simulate_route', 'present_artifact']),
            ('Покажи мои квесты', 'rewards', ['get_my_context', 'present_artifact']),
            ('Сколько квестов завершено?', 'rewards', ['get_my_context', 'present_artifact']),
        ]:
            with self.subTest(message=message):
                response = self.ask(message)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['artifact']['kind'], kind)
                self.assertEqual([step['tool'] for step in result['trace']], expected_tools)
                if kind == 'comparison':
                    self.assertEqual(len(result['artifact']['comparison']), 2)
                if kind in {'route', 'next_step'}:
                    self.assertTrue(result['artifact']['options']['recommendations'])

    def test_rewards_respect_profile_access(self):
        self.assertEqual(self.ask('Покажи награды E0002').status_code, 403)
        self.assertEqual(self.ask('Покажи награды команды').status_code, 403)
        self.assertEqual(self.ask('Покажи награды E0001').status_code, 200)

    def test_external_agent_can_publish_rewards_and_fallback(self):
        calls = [{'type': 'function_call', 'name': name, 'arguments': json.dumps(arguments), 'call_id': str(i)}
                 for i, (name, arguments) in enumerate([
                     ('get_my_context', {}), ('present_artifact', {'kind': 'rewards'})
                 ])]
        with patch('backend.app.assistant.external_enabled', return_value=True), patch(
            'backend.app.assistant.model_step', new=AsyncMock(return_value={'output': calls})
        ):
            result = self.ask('Сколько у меня XP?').json()
        self.assertEqual(result['mode'], 'agent')
        self.assertEqual(result['artifact']['kind'], 'rewards')
        with patch('backend.app.assistant.external_enabled', return_value=True), patch(
            'backend.app.assistant.model_step', new=AsyncMock(side_effect=TimeoutError())
        ):
            result = self.ask('Мои квесты').json()
        self.assertEqual(result['mode'], 'fallback')
        self.assertEqual(result['artifact']['kind'], 'rewards')


if __name__ == '__main__':
    unittest.main()
