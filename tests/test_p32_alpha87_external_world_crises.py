import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import actions
import engine
import region_activity
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Alpha87ExternalWorldCrisisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'region_activity.json'), encoding='utf-8') as f:
            cls.config = json.load(f)

    def player_at(self, zone='northfront_town'):
        player = Player('外部局势测试', '散人')
        player.location = next(room_id for room_id, row in self.rooms.items() if row.get('zone') == zone)
        return player

    def test_world_crisis_changes_region_and_emits_public_announcement(self):
        player = self.player_at('northfront_town')
        player.set_var('quest_clock', 18)
        variables = player.world_state.setdefault('variables', {})
        config = json.loads(json.dumps(self.config))
        config['external_world_events']['trigger_chance'] = 1.0
        config['external_world_events']['events'] = [
            {
                'id': 'test_external_war', 'type': '战争', 'title': '北境战事测试',
                'cooldown': 50, 'duration': 30,
                'announcement': '北境测试战事爆发。', 'end_announcement': '北境测试战事平息。',
                'effects': {'northfront_town': {'security': -18, 'commerce': -12, 'travel': -15}}
            }
        ]
        with patch.object(region_activity, 'get_config', return_value=config):
            changed = region_activity.process_external_world_crises(player, 18)
            self.assertTrue(any(row.get('status') == 'active' for row in changed))
            delta = region_activity.get_region_delta(player, 'northfront_town')
            self.assertEqual(delta['security'], -18)
            self.assertEqual(delta['commerce'], -12)
            self.assertEqual(delta['travel'], -15)
        news = variables.get('pending_world_crisis_announcements', [])
        self.assertTrue(any('北境测试战事爆发' in line for line in news))

    def test_crisis_expiry_fades_effect_and_emits_resolution_announcement(self):
        player = self.player_at('northfront_town')
        variables = player.world_state.setdefault('variables', {})
        player.set_var('quest_clock', 9)
        variables = player.world_state.setdefault('variables', {})
        variables['world_crises'] = {
            'test_external_war': {
                'id': 'test_external_war', 'title': '北境战事测试', 'status': 'active',
                'started_clock': 1, 'expires_clock': 10,
                'effects': {'northfront_town': {'security': -18, 'commerce': -12, 'travel': -15}},
                'end_announcement': '北境测试战事平息。'
            }
        }
        with patch.object(region_activity, 'get_config', return_value={
            'external_world_events': {'roll_interval': 1000, 'trigger_chance': 0, 'recovery_fade': 12, 'max_active': 2, 'events': []}
        }):
            before = region_activity.get_region_delta(player, 'northfront_town')
            self.assertEqual(before['security'], -18)
            region_activity.process_external_world_crises(player, 10)
            player.set_var('quest_clock', 16)
            after = region_activity.get_region_delta(player, 'northfront_town')
            self.assertGreater(after['security'], before['security'])
            self.assertLess(after['security'], 0)
        self.assertTrue(any('北境测试战事平息' in line for line in variables.get('pending_world_crisis_announcements', [])))

    def test_region_screen_explains_external_crisis(self):
        player = self.player_at('northfront_town')
        variables = player.world_state.setdefault('variables', {})
        variables['world_crises'] = {
            'test_external_war': {
                'id': 'test_external_war', 'title': '北境战事测试', 'status': 'active',
                'started_clock': 1, 'expires_clock': 50,
                'effects': {'northfront_town': {'security': -18}},
                'announcement': '边境战事影响商路。'
            }
        }
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            actions.handle_region_ecology(player, [])
        self.assertIn('外部局势：北境战事测试', out.getvalue())
        self.assertIn('边境战事影响商路', out.getvalue())

    def test_old_v12_save_gets_crisis_state_lazily(self):
        player = self.player_at('main')
        player.world_state.setdefault('variables', {}).pop('world_crises', None)
        with patch.object(region_activity, 'get_config', return_value={
            'external_world_events': {'roll_interval': 1000, 'trigger_chance': 0, 'events': []}
        }):
            region_activity.process_external_world_crises(player, 1)
        self.assertIn('world_crises', player.world_state['variables'])
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == '__main__':
    unittest.main()
