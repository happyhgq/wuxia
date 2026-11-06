import copy
import json
import os
import unittest
from unittest.mock import patch

import engine
import region_activity
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Alpha89CrisisOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'region_activity.json'), encoding='utf-8') as f:
            cls.config = json.load(f)

    def player_at(self, zone='northfront_town'):
        p = Player('局势结果测试', '散人')
        p.location = next(rid for rid, row in self.rooms.items() if row.get('zone') == zone)
        return p

    def seed_crisis(self, p, event_id='northfront_war_outbreak', relief=0.0, escalated=False, expires=10):
        event = next(e for e in self.config['external_world_events']['events'] if e['id'] == event_id)
        crisis = {
            'id': event_id, 'title': event['title'], 'type': event['type'], 'status': 'active',
            'started_clock': 0, 'expires_clock': expires, 'effects': copy.deepcopy(event['effects']),
            'announcement': event['announcement'], 'end_announcement': event['end_announcement'],
            'npc_response': {}, 'player_action': copy.deepcopy(event.get('player_action', {})),
            'escalation': copy.deepcopy(event.get('escalation', {})), 'escalated': escalated,
            'stage': '局势恶化' if escalated else '发生', 'last_npc_response_clock': 0,
            'npc_relief': relief, 'player_relief': 0.0, 'player_actions': 0,
            'last_player_action_clock': -999999,
        }
        p.world_state.setdefault('variables', {})['world_crises'] = {event_id: crisis}
        return crisis

    def test_escalation_spreads_crisis_to_configured_region(self):
        p = self.player_at()
        crisis = self.seed_crisis(p, expires=60)
        config = copy.deepcopy(self.config)
        config['external_world_events'].update({'roll_interval': 9999, 'trigger_chance': 0, 'max_active': 2})
        with patch.object(region_activity, 'get_config', return_value=config):
            rows = region_activity.process_external_world_crises(p, 30)
        self.assertTrue(crisis['escalated'])
        self.assertIn('bandit_zone', crisis['effects'])
        self.assertEqual(crisis['effects']['bandit_zone']['travel'], -5)
        self.assertTrue(any(r.get('status') == 'escalated' for r in rows))

    def test_escalation_does_not_mutate_global_event_configuration(self):
        original = copy.deepcopy(self.config['external_world_events']['events'])
        p = self.player_at()
        config = copy.deepcopy(self.config)
        event = next(e for e in config['external_world_events']['events'] if e['id'] == 'northfront_war_outbreak')
        crisis = self.seed_crisis(p)
        # Simulate the normal production event-creation path: event data is copied into saved state.
        crisis['effects'] = copy.deepcopy(event['effects'])
        config['external_world_events'].update({'roll_interval': 9999, 'trigger_chance': 0, 'max_active': 2})
        with patch.object(region_activity, 'get_config', return_value=config):
            region_activity.process_external_world_crises(p, 30)
        self.assertEqual(config['external_world_events']['events'], original)

    def test_helped_crisis_ends_with_controlled_outcome_and_short_recovery(self):
        p = self.player_at()
        crisis = self.seed_crisis(p, relief=0.4)
        config = copy.deepcopy(self.config)
        config['external_world_events'].update({'roll_interval': 9999, 'trigger_chance': 0, 'max_active': 2, 'recovery_fade': 12})
        with patch.object(region_activity, 'get_config', return_value=config):
            rows = region_activity.process_external_world_crises(p, 10)
        self.assertEqual(crisis['outcome'], '得到控制')
        self.assertEqual(crisis['stage'], '局势受控')
        self.assertEqual(crisis['recovery_end_clock'], 16)
        self.assertEqual(rows[0]['outcome'], '得到控制')

    def test_escalated_unresolved_crisis_leaves_longer_lingering_effect(self):
        p = self.player_at()
        crisis = self.seed_crisis(p, escalated=True)
        config = copy.deepcopy(self.config)
        config['external_world_events'].update({'roll_interval': 9999, 'trigger_chance': 0, 'max_active': 2, 'recovery_fade': 12})
        with patch.object(region_activity, 'get_config', return_value=config):
            region_activity.process_external_world_crises(p, 10)
        self.assertEqual(crisis['outcome'], '留下余波')
        self.assertEqual(crisis['stage'], '余波未平')
        self.assertEqual(crisis['recovery_end_clock'], 34)

    def test_crisis_state_remains_json_serializable_and_v12_unchanged(self):
        p = self.player_at()
        self.seed_crisis(p)
        region_activity.process_external_world_crises(p, 5)
        json.dumps(p.world_state, ensure_ascii=False)
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == '__main__':
    unittest.main()
