import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))

class Alpha39WoodcraftLoopTests(unittest.TestCase):
    def test_carpenter_is_referenced_by_real_room_and_existing_item(self):
        with open(os.path.join(BASE, 'data', 'npcs.json'), encoding='utf-8') as f:
            npcs = json.load(f)
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'items.json'), encoding='utf-8') as f:
            items = json.load(f)
        self.assertIn('木匠老许', npcs)
        self.assertIn('木匠老许', rooms['village_square']['npcs'])
        self.assertIn('木剑', items)
        self.assertIn('木剑', npcs['木匠老许']['shop'])

    def test_real_wood_stock_is_purchased_then_consumed_to_make_wood_sword(self):
        manager = EconomyManager({
            'npc_inventory': {'樵夫老周': {'木材': 9}},
            'npc_gold': {'樵夫老周': 20, '木匠老许': 100},
        })
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.resources = {}
        # 木匠采购间隔 12 个工时；工时左闭右开后需要跨过交班时辰凑满整轮。
        manager.update(24)
        state = manager.export_state()
        carpenter = state['npc_inventory']['木匠老许']
        lumberjack = state['npc_inventory']['樵夫老周']
        self.assertGreaterEqual(carpenter.get('木剑', 0), 1)
        self.assertLess(lumberjack['木材'], 9)
        self.assertGreater(state['npc_gold']['樵夫老周'], 20)
        self.assertLess(state['npc_gold']['木匠老许'], 100)
        self.assertGreater(state['market']['木剑']['supply'], 20)

    def test_carpenter_never_makes_product_without_real_wood(self):
        manager = EconomyManager({'npc_inventory': {'木匠老许': {'木材': 0, '木剑': 0}}})
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.resources = {}
        manager.update(12)
        self.assertEqual(manager.state.npc_inventory['木匠老许'].get('木剑', 0), 0)

    def test_carpenter_output_respects_capacity_over_long_run(self):
        manager = EconomyManager({
            'npc_inventory': {'樵夫老周': {'木材': 999}, '木匠老许': {'木剑': 7}},
            'npc_gold': {'樵夫老周': 100, '木匠老许': 1000},
        })
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.resources = {}
        manager.update(100)
        self.assertLessEqual(manager.state.npc_inventory['木匠老许'].get('木剑', 0), 8)
        self.assertGreaterEqual(manager.state.npc_inventory['木匠老许'].get('木材', 0), 0)
        self.assertLessEqual(manager.state.npc_inventory['樵夫老周'].get('木材', 0), 9999)

if __name__ == '__main__':
    unittest.main()
