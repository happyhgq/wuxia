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


class Alpha88CrisisResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'region_activity.json'), encoding='utf-8') as f:
            cls.config = json.load(f)

    def player_at(self, zone='guiyun_city'):
        p = Player('局势应对测试', '散人')
        p.location = next(room_id for room_id, row in self.rooms.items() if row.get('zone') == zone)
        return p

    def crisis(self, player, event_id='guiyun_city_riot', zone='guiyun_city'):
        event = next(row for row in self.config['external_world_events']['events'] if row['id'] == event_id)
        variables = player.world_state.setdefault('variables', {})
        variables['world_crises'] = {
            event_id: {
                'id': event_id, 'title': event['title'], 'type': event['type'], 'status': 'active',
                'started_clock': 10, 'expires_clock': 60, 'effects': event['effects'],
                'announcement': event['announcement'], 'end_announcement': event['end_announcement'],
                'npc_response': event.get('npc_response', {}), 'player_action': event.get('player_action', {}),
                'escalation': event.get('escalation', {}), 'escalated': False, 'stage': '发生',
                'last_npc_response_clock': 10, 'npc_relief': 0.0, 'player_relief': 0.0,
                'player_actions': 0, 'last_player_action_clock': -999999,
            }
        }
        return variables['world_crises'][event_id]

    def test_npc_response_reduces_crisis_impact_after_configured_interval(self):
        p = self.player_at()
        crisis = self.crisis(p)
        config = json.loads(json.dumps(self.config))
        config['external_world_events'].update({'roll_interval': 1000, 'trigger_chance': 0, 'max_active': 2})
        with patch.object(region_activity, 'get_config', return_value=config):
            before = region_activity.get_region_delta(p, 'guiyun_city')['security']
            region_activity.process_external_world_crises(p, 18)
            after = region_activity.get_region_delta(p, 'guiyun_city')['security']
        self.assertEqual(crisis['npc_relief'], 0.12)
        self.assertGreater(after, before)
        self.assertTrue(any('捕快与街坊' in x for x in p.world_state['variables'].get('pending_world_crisis_announcements', [])))

    def test_player_can_assist_local_crisis_with_limited_contributions(self):
        p = self.player_at()
        crisis = self.crisis(p)
        before = region_activity.get_region_delta(p, 'guiyun_city')['security']
        ok, message, _ = region_activity.assist_world_crisis(p, 'guiyun_city')
        after = region_activity.get_region_delta(p, 'guiyun_city')['security']
        self.assertTrue(ok)
        self.assertIn('协助捕快', message)
        self.assertGreater(after, before)
        self.assertEqual(crisis['player_actions'], 1)
        ok2, message2, _ = region_activity.assist_world_crisis(p, 'guiyun_city')
        self.assertFalse(ok2)
        self.assertIn('等待', message2)

    def test_player_cannot_assist_crisis_from_unaffected_region(self):
        p = self.player_at('sunken_ruins')
        self.crisis(p)
        ok, message, _ = region_activity.assist_world_crisis(p, 'sunken_ruins')
        self.assertFalse(ok)
        self.assertIn('没有可由你直接协助', message)


    def test_unresolved_crisis_escalates_once_and_announces(self):
        p = self.player_at()
        crisis = self.crisis(p)
        crisis['started_clock'] = 10
        crisis['last_npc_response_clock'] = 100
        crisis['npc_response'] = {}
        crisis['escalation'] = {'after': 12, 'multiplier': 1.25, 'announcement': '测试局势进一步恶化。'}
        config = json.loads(json.dumps(self.config))
        config['external_world_events'].update({'roll_interval': 1000, 'trigger_chance': 0, 'max_active': 2})
        with patch.object(region_activity, 'get_config', return_value=config):
            before = region_activity.get_region_delta(p, 'guiyun_city')['security']
            region_activity.process_external_world_crises(p, 22)
            after = region_activity.get_region_delta(p, 'guiyun_city')['security']
            region_activity.process_external_world_crises(p, 23)
        self.assertTrue(crisis['escalated'])
        self.assertEqual(crisis['stage'], '局势恶化')
        self.assertLess(after, before)
        announcements = p.world_state['variables'].get('pending_world_crisis_announcements', [])
        self.assertEqual(sum('测试局势进一步恶化' in x for x in announcements), 1)

    def test_security_command_exposes_assistance_action(self):
        p = self.player_at()
        self.crisis(p)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            actions.handle_security_governance(p, ['协助'])
        self.assertIn('协助捕快', out.getvalue())

    def test_relief_is_bounded_and_state_remains_v12_compatible(self):
        p = self.player_at()
        crisis = self.crisis(p)
        crisis['npc_relief'] = 0.45
        crisis['player_relief'] = 0.55
        delta = region_activity.get_region_delta(p, 'guiyun_city')
        self.assertGreaterEqual(delta['security'], -12)
        self.assertEqual(engine.SAVE_VERSION, 12)
        json.dumps(p.world_state, ensure_ascii=False)


if __name__ == '__main__':
    unittest.main()
