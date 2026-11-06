import copy
import json
import os
import unittest
from unittest.mock import patch

import engine
import region_activity
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Alpha91CrisisActionOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'region_activity.json'), encoding='utf-8') as f:
            cls.config = json.load(f)

    def make_player(self, zone='northfront_town', event_id='north_route_robbery'):
        p = Player('危机应对测试', '散人')
        room_id = next(rid for rid, row in self.rooms.items() if row.get('zone') == zone)
        p.location = room_id
        event = copy.deepcopy(next(row for row in self.config['external_world_events']['events'] if row['id'] == event_id))
        p.world_state.setdefault('variables', {})['world_crises'] = {
            event_id: {
                'id': event_id, 'title': event['title'], 'type': event['type'], 'status': 'active',
                'started_clock': 0, 'expires_clock': 50, 'effects': copy.deepcopy(event['effects']),
                'player_action': copy.deepcopy(event.get('player_action', {})),
                'npc_relief': 0.0, 'player_relief': 0.0, 'player_actions': 0,
                'last_player_action_clock': -999999,
            }
        }
        return p, event_id

    def test_assisting_robbery_immediately_improves_local_trade_and_travel(self):
        p, event_id = self.make_player()
        before = copy.deepcopy(region_activity._ensure_row(p, 'northfront_town'))
        ok, message, _ = region_activity.assist_world_crisis(p, 'northfront_town')
        after = region_activity._ensure_row(p, 'northfront_town')
        self.assertTrue(ok)
        self.assertEqual(after['security'] - before['security'], 1)
        self.assertEqual(after['commerce'] - before['commerce'], 2)
        self.assertEqual(after['travel'] - before['travel'], 2)
        self.assertIn('商路+2', message)
        self.assertIn('通行+2', message)
        self.assertEqual(p.world_state['variables']['world_crises'][event_id]['player_actions'], 1)

    def test_riot_assistance_uses_its_own_configured_effects(self):
        p, _ = self.make_player('guiyun_city', 'guiyun_city_riot')
        before = copy.deepcopy(region_activity._ensure_row(p, 'guiyun_city'))
        ok, message, _ = region_activity.assist_world_crisis(p, 'guiyun_city')
        after = region_activity._ensure_row(p, 'guiyun_city')
        self.assertTrue(ok)
        self.assertEqual(after['security'] - before['security'], 2)
        self.assertEqual(after['commerce'] - before['commerce'], 1)
        self.assertIn('治安+2', message)

    def test_unconfigured_action_keeps_existing_relief_behavior_without_local_delta(self):
        p, _ = self.make_player()
        crisis = p.world_state['variables']['world_crises']['north_route_robbery']
        crisis['player_action'].pop('immediate_effects', None)
        before = copy.deepcopy(region_activity._ensure_row(p, 'northfront_town'))
        with patch.object(region_activity, 'get_config', return_value=self.config):
            ok, _, _ = region_activity.assist_world_crisis(p, 'northfront_town')
        after = region_activity._ensure_row(p, 'northfront_town')
        self.assertTrue(ok)
        for key in ('security', 'commerce', 'travel'):
            self.assertEqual(after[key], before[key])
        self.assertGreater(crisis['player_relief'], 0)

    def test_effects_are_bounded_and_save_format_remains_v12(self):
        p, _ = self.make_player()
        crisis = p.world_state['variables']['world_crises']['north_route_robbery']
        crisis['player_action']['immediate_effects']['northfront_town'] = {
            'security': 999, 'commerce': -999, 'travel': 1
        }
        ok, _, _ = region_activity.assist_world_crisis(p, 'northfront_town')
        row = region_activity._ensure_row(p, 'northfront_town')
        self.assertTrue(ok)
        self.assertEqual(row['security'], 3)
        self.assertEqual(row['commerce'], -3)
        self.assertEqual(row['travel'], 1)
        json.dumps(p.world_state, ensure_ascii=False)
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == '__main__':
    unittest.main()
