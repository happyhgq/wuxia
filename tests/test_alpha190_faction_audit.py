# -*- coding: utf-8 -*-
"""Alpha190: model the existing Black Wind Stronghold separately from the black market."""
import json
import os
import unittest

import engine
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Alpha190FactionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'factions.json'), encoding='utf-8') as f:
            cls.factions = json.load(f)
        with open(os.path.join(BASE, 'data', 'sects.json'), encoding='utf-8') as f:
            cls.sects = json.load(f)
        with open(os.path.join(BASE, 'data', 'world_regions.json'), encoding='utf-8') as f:
            cls.regions = json.load(f)
        with open(os.path.join(BASE, 'data', 'quests.json'), encoding='utf-8') as f:
            cls.quests = json.load(f)
        with open(os.path.join(BASE, 'data', 'world_events.json'), encoding='utf-8') as f:
            cls.events = json.load(f)

    def test_existing_bandit_organization_is_a_faction(self):
        self.assertIn('黑风寨', self.factions)
        self.assertIn('bandit_zone', self.regions)
        self.assertIn('清剿黑风山', self.quests)
        self.assertIn('main_bandit_warning', self.events)

    def test_black_wind_stronghold_and_black_market_are_distinct(self):
        self.assertNotEqual(self.factions['黑风寨']['title'], self.factions['黑市']['title'])
        self.assertEqual(self.factions['黑风寨']['relations']['黑市'], 0)
        self.assertEqual(self.factions['黑市']['relations']['黑风寨'], 0)
        self.assertNotIn('黑风寨', self.sects)

    def test_new_static_relations_are_symmetric(self):
        for other, value in self.factions['黑风寨']['relations'].items():
            self.assertIn('黑风寨', self.factions[other]['relations'])
            self.assertEqual(self.factions[other]['relations']['黑风寨'], value)

    def test_player_reads_static_relations_in_both_directions(self):
        p = Player('Alpha190势力核查', '散人')
        expected = {'青石村': -65, '官府': -75, '商会': -35, '黑市': 0, '江湖': -10, '沈府': 0}
        for faction, relation in expected.items():
            self.assertEqual(p.get_faction_relation('黑风寨', faction), relation)
            self.assertEqual(p.get_faction_relation(faction, '黑风寨'), relation)

    def test_faction_summary_includes_existing_bandit_organization(self):
        p = Player('Alpha190势力面板', '散人')
        summary = {row['title']: row for row in p.get_faction_summary()}
        self.assertIn('黑风寨山寨势力', summary)
        relations = {row['faction']: row['relation'] for row in summary['黑风寨山寨势力']['relations']}
        self.assertEqual(relations['官府'], -75)
        self.assertEqual(relations['黑市'], 0)

    def test_save_version_remains_v12(self):
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == '__main__':
    unittest.main()
