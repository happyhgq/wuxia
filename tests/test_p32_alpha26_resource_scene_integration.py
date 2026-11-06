import json
import os
import unittest
from collections import deque

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Alpha26ResourceSceneIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'resources.json'), encoding='utf-8') as f:
            cls.resources = json.load(f)

    def test_every_room_is_reachable_from_the_starting_village(self):
        seen = {'village_gate'}
        queue = deque(seen)
        while queue:
            current = queue.popleft()
            targets = list(self.rooms[current].get('exits', {}).values())
            targets.extend(entry.get('target') for entry in self.rooms[current].get('hidden_exits', {}).values() if isinstance(entry, dict))
            for target in targets:
                self.assertIn(target, self.rooms, (current, target))
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        self.assertEqual(seen, set(self.rooms), f'unreachable rooms: {sorted(set(self.rooms) - seen)}')

    def test_every_economy_resource_has_a_room_and_a_matching_interaction_hint(self):
        for room_id, cfg in self.resources.items():
            with self.subTest(room=room_id):
                self.assertIn(room_id, self.rooms)
                desc = self.rooms[room_id].get('desc', '')
                action = cfg.get('action', 'mine')
                self.assertIn('伐木' if action == 'chop' else ('搜索' if action == 'gather' else '采矿'), desc)
                self.assertGreaterEqual(int(cfg.get('capacity', 0)), 1)
                self.assertGreaterEqual(int(cfg.get('yield_max', 0)), 1)
                self.assertGreaterEqual(int(cfg.get('regen_interval', 0)), 1)
                self.assertGreaterEqual(int(cfg.get('regen_amount', 0)), 1)

    def test_scene_stock_display_reflects_live_state_and_caps_corrupt_values(self):
        from actions import _resource_stock_line
        resources = {'test_mine': {'item': '铁矿石', 'capacity': 24, 'yield_max': 3}}
        self.assertIn('24/24', _resource_stock_line('test_mine', {}, resources))
        self.assertIn('7/24', _resource_stock_line('test_mine', {'resources': {'test_mine': {'remaining': 7}}}, resources))
        depleted = _resource_stock_line('test_mine', {'resources': {'test_mine': {'remaining': 0}}}, resources)
        self.assertIn('0/24', depleted)
        self.assertIn('等待自然恢复', depleted)
        self.assertIn('24/24', _resource_stock_line('test_mine', {'resources': {'test_mine': {'remaining': 999}}}, resources))

    def test_chopping_scene_uses_the_real_chop_command(self):
        from actions import _resource_stock_line
        resources = {'test_forest': {'item': '木材', 'action': 'chop', 'capacity': 18}}
        text = _resource_stock_line('test_forest', {}, resources)
        self.assertIn('伐木', text)
        self.assertNotIn('采矿', text)

    def test_non_resource_rooms_do_not_show_fake_resource_stock(self):
        from actions import _resource_stock_line
        self.assertEqual('', _resource_stock_line('village_square', {}, self.resources))


if __name__ == '__main__':
    unittest.main()
