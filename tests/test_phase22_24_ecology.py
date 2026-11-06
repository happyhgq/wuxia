import json
import os
import unittest
import engine
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')

def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)

class Phase22To24EcologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load('world_events.json')
        cls.rooms = load('rooms.json')
        cls.items = load('items.json')
        cls.npcs = load('npcs.json')
        cls.regions = load('world_regions.json')

    def _player_in_region(self, region, flag):
        p = Player('生态联动验收', '散人')
        room = next((rid for rid, info in self.rooms.items() if info.get('zone') == region), None)
        self.assertIsNotNone(room, region)
        p.location = room
        p.set_flag(flag, True)
        return p

    def test_four_branch_events_are_region_bound_and_reference_valid(self):
        expected = {
            'sunken_official_escort': ('guiyun_city', 'sunken_ruins:evidence_to_officials'),
            'sunken_blackmarket_deal': ('sunken_ruins', 'sunken_ruins:evidence_to_black_market'),
            'northfront_merchant_recovery': ('northfront_town', 'northfront:merchant_route_chosen'),
            'northfront_smuggler_backlash': ('northfront_town', 'northfront:smuggler_deal_made'),
        }
        for event_id, (region, flag) in expected.items():
            info = self.events[event_id]
            self.assertEqual(info['region'], region)
            self.assertIn(flag, info['requires']['flags'])
            self.assertTrue(info.get('once'))
            for npc_info in info.get('effects', {}).get('npc_information', []):
                self.assertIn(npc_info['npc'], self.npcs)
            self.assertIn(info['rewards']['item'], self.items)

    def test_branch_events_apply_world_effects_and_reward_once(self):
        cases = [
            ('sunken_official_escort', 'guiyun_city', 'sunken_ruins:evidence_to_officials', 'world:guiyun:old_case_witness_safe'),
            ('sunken_blackmarket_deal', 'sunken_ruins', 'sunken_ruins:evidence_to_black_market', 'world:sunken:blackmarket_network_open'),
            ('northfront_merchant_recovery', 'northfront_town', 'northfront:merchant_route_chosen', 'world:northfront:merchant_route_reopened'),
            ('northfront_smuggler_backlash', 'northfront_town', 'northfront:smuggler_deal_made', 'world:northfront:smuggler_backlash_seen'),
        ]
        for event_id, region, required_flag, result_flag in cases:
            with self.subTest(event_id=event_id):
                p = self._player_in_region(region, required_flag)
                before_gold = p.gold
                ok, message, info = p.trigger_world_event(event_id)
                self.assertTrue(ok, message)
                self.assertTrue(p.get_flag(result_flag))
                self.assertGreaterEqual(p.gold, before_gold)
                ok_again, _, _ = p.trigger_world_event(event_id)
                self.assertFalse(ok_again)
                self.assertEqual(p.get_world_event_state(event_id).get('count'), 1)

    def test_old_v12_world_state_can_use_new_events_without_schema_change(self):
        p = Player('旧档生态验收', '散人')
        p.world_state.setdefault('variables', {}).pop('world_events', None)
        self.assertEqual(engine.SAVE_VERSION, 12)
        self.assertFalse(p.can_trigger_world_event('sunken_official_escort'))
        p.set_flag('sunken_ruins:evidence_to_officials', True)
        p.location = next(rid for rid, info in self.rooms.items() if info.get('zone') == 'guiyun_city')
        self.assertTrue(p.can_trigger_world_event('sunken_official_escort'))

if __name__ == '__main__':
    unittest.main()
