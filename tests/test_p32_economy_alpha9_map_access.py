import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Alpha9MapAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'resources.json'), encoding='utf-8') as f:
            cls.resources = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'caravans.json'), encoding='utf-8') as f:
            cls.caravans = json.load(f)

    def test_mistwood_stream_has_gatherable_herbs(self):
        self.assertIn('草药', self.rooms['mistwood_stream'].get('forage', {}))

    def test_abandoned_mine_is_reachable_from_existing_map(self):
        self.assertEqual(self.rooms['mistwood_hut']['exits'].get('东'), 'abandoned_iron_mine')
        self.assertEqual(self.rooms['abandoned_iron_mine']['exits'].get('西'), 'mistwood_hut')
        self.assertEqual(self.rooms['abandoned_iron_mine']['zone'], 'mistwood')

    def test_mining_config_uses_real_room_id(self):
        self.assertIn('abandoned_iron_mine', self.rooms)
        self.assertIn('abandoned_iron_mine', self.resources)
        manager = EconomyManager(data_dir=os.path.join(BASE, 'data', 'economy'))
        ok, result = manager.mine('abandoned_iron_mine')
        self.assertTrue(ok)
        self.assertEqual(result[0], '铁矿石')

    def test_caravan_route_uses_actual_mine_room(self):
        self.assertTrue(any('abandoned_iron_mine' in row.get('route', []) for row in self.caravans.values()))
        self.assertNotIn('cave_entrance', self.resources)

if __name__ == '__main__':
    unittest.main()
