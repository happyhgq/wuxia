import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))

class Alpha43MinerSupplyChainTests(unittest.TestCase):
    def test_miner_is_in_mine_room_and_has_real_resource_route(self):
        with open(os.path.join(BASE, 'data', 'npcs.json'), encoding='utf-8') as f:
            npcs = json.load(f)
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'gatherers.json'), encoding='utf-8') as f:
            gatherers = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'recipes.json'), encoding='utf-8') as f:
            recipes = json.load(f)
        self.assertIn('矿工顾三', npcs)
        self.assertIn('矿工顾三', rooms['abandoned_iron_mine']['npcs'])
        self.assertEqual(gatherers['矿工顾三']['resource_room_id'], 'deep_iron_gallery')
        self.assertIn('矿工顾三', recipes['百炼铁铺铁匠']['supplier_routes'][0]['suppliers'])

    def test_miner_uses_shared_mine_stock_and_smith_buys_real_ore(self):
        manager = EconomyManager({'npc_inventory': {'矿工顾三': {'铁矿石': 0}, '百炼铁铺铁匠': {'铁矿石': 0}}, 'npc_gold': {'矿工顾三': 0, '百炼铁铺铁匠': 100}})
        manager.update(35)
        state = manager.export_state()
        miner = state['npc_inventory']['矿工顾三']
        smith = state['npc_inventory']['百炼铁铺铁匠']
        self.assertGreaterEqual(miner.get('铁矿石', 0), 0)
        self.assertLessEqual(miner.get('铁矿石', 0), 10)
        self.assertGreater(state['npc_gold']['矿工顾三'], 0)
        self.assertGreaterEqual(smith.get('铁矿石', 0), 1)
        self.assertLessEqual(smith.get('铁剑', 0), 8)
        self.assertLessEqual(state['resources']['abandoned_iron_mine']['remaining'], 24)

    def test_miner_stock_and_smith_output_remain_bounded_on_long_run(self):
        manager = EconomyManager({'npc_inventory': {'矿工顾三': {'铁矿石': 9999}, '百炼铁铺铁匠': {'铁矿石': 9999, '铁剑': 9999}}, 'npc_gold': {'矿工顾三': 100, '百炼铁铺铁匠': 1000}})
        manager.update(120)
        state = manager.export_state()
        self.assertLessEqual(state['npc_inventory']['矿工顾三']['铁矿石'], 10)
        self.assertLessEqual(state['npc_inventory']['百炼铁铺铁匠']['铁剑'], 8)
        self.assertGreaterEqual(state['npc_gold']['矿工顾三'], 0)

if __name__ == '__main__':
    unittest.main()
