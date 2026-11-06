import json
import os
import unittest

import engine
import region_activity
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Alpha90CrisisGameplayLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'region_activity.json'), encoding='utf-8') as f:
            cls.config = json.load(f)

    def make_player(self):
        p = Player('清剿联动测试', '散人')
        room_id = next(rid for rid, row in self.rooms.items() if row.get('zone') == 'northfront_town')
        p.location = room_id
        p.world_state.setdefault('variables', {})['world_crises'] = {
            'north_route_robbery': {
                'id': 'north_route_robbery', 'title': '北境商路遭劫', 'status': 'active',
                'started_clock': 0, 'expires_clock': 50,
                'effects': {'northfront_town': {'security': -10, 'commerce': -16, 'travel': -14}},
                'player_action': next(e['player_action'] for e in self.config['external_world_events']['events'] if e['id'] == 'north_route_robbery'),
                'npc_relief': 0.0, 'player_relief': 0.0, 'player_actions': 0,
            }
        }
        return p, room_id

    def test_criminal_defeat_relieves_local_robbery_crisis_with_limits(self):
        p, room_id = self.make_player()
        crisis = p.world_state['variables']['world_crises']['north_route_robbery']
        before = region_activity.get_region_delta(p, 'northfront_town')['commerce']
        result = region_activity.record_criminal_defeat(p, room_id, '劫镖山贼', engine.ENEMIES.get('劫镖山贼'))
        after = region_activity.get_region_delta(p, 'northfront_town')['commerce']
        self.assertTrue(result['applied'])
        self.assertEqual(crisis['criminal_defeat_actions'], 1)
        self.assertGreater(crisis['player_relief'], 0)
        self.assertGreater(after, before)
        self.assertTrue(any('清剿战果' in x for x in p.world_state['variables'].get('pending_world_crisis_announcements', [])))

    def test_non_criminal_or_unconfigured_crisis_does_not_get_auto_credit(self):
        p, room_id = self.make_player()
        crisis = p.world_state['variables']['world_crises']['north_route_robbery']
        crisis['player_action']['on_criminal_defeat']['enabled'] = False
        region_activity.record_criminal_defeat(p, room_id, '劫镖山贼', engine.ENEMIES.get('劫镖山贼'))
        self.assertNotIn('criminal_defeat_actions', crisis)
        self.assertEqual(crisis['player_relief'], 0.0)

    def test_v12_save_version_unchanged(self):
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == '__main__':
    unittest.main()
