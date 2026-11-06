import json
import os
import unittest

from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha68FiniteForageTests(unittest.TestCase):
    def test_every_searchable_forage_item_has_a_matching_finite_resource(self):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'resources.json'), encoding='utf-8') as f:
            resources = json.load(f)
        for room_id, room in rooms.items():
            for item in (room.get('forage') or {}):
                self.assertIn(room_id, resources, f'{room_id} has unbounded forage item {item}')
                cfg = resources[room_id]
                self.assertEqual(cfg.get('action'), 'gather', f'{room_id}:{item} must use gather')
                self.assertEqual(cfg.get('item'), item, f'{room_id} forage item does not match resource')
                self.assertGreater(int(cfg.get('capacity', 0)), 0)
                self.assertGreater(int(cfg.get('regen_interval', 0)), 0)
                self.assertGreater(int(cfg.get('regen_amount', 0)), 0)

    def test_wild_fields_only_searches_herbs_not_pork(self):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            rooms = json.load(f)
        self.assertEqual(set(rooms['wild_fields']['forage']), {'草药'})
        with open(os.path.join(BASE, 'data', 'enemies.json'), encoding='utf-8') as f:
            enemies = json.load(f)
        boar = enemies.get('野猪', {})
        drops = boar.get('drops', [])
        self.assertTrue(any(row.get('item') == '野猪肉' for row in drops))

    def test_wild_fields_stock_recovers_six_ticks_by_two_but_never_over_capacity(self):
        manager = EconomyManager({'tick': 0, 'resources': {'wild_fields': {'remaining': 0, 'last_tick': 0}}})
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.update(6)
        self.assertEqual(manager.state.resources['wild_fields']['remaining'], 2)
        manager.state.resources['wild_fields']['remaining'] = 11
        manager.state.resources['wild_fields']['last_tick'] = manager.state.tick
        manager.update(6)
        self.assertEqual(manager.state.resources['wild_fields']['remaining'], 12)
        manager.update(60)
        self.assertEqual(manager.state.resources['wild_fields']['remaining'], 12)

    def test_wild_fields_can_be_depleted_then_recovers(self):
        manager = EconomyManager({'resources': {'wild_fields': {'remaining': 1, 'last_tick': 0}}})
        ok, result = manager.gather('wild_fields', 1)
        self.assertTrue(ok)
        self.assertEqual(result, ('草药', 1))
        self.assertFalse(manager.gather('wild_fields', 1)[0])
        manager.update(6)
        self.assertEqual(manager.state.resources['wild_fields']['remaining'], 2)


if __name__ == '__main__':
    unittest.main()
