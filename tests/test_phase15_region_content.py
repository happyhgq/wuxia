import json
import os
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')

def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f:
        return json.load(f)

class Phase15RegionContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rooms = load('rooms.json')
        cls.npcs = load('npcs.json')
        cls.enemies = load('enemies.json')
        cls.items = load('items.json')
        cls.factions = load('factions.json')
        cls.zones = {'mistwood', 'sunken_ruins', 'northfront_town'}

    def test_new_regions_have_interactive_content(self):
        for zone in self.zones:
            room_ids = [rid for rid, room in self.rooms.items() if room.get('zone') == zone]
            self.assertTrue(room_ids)
            self.assertTrue(any(self.rooms[rid].get('npcs') for rid in room_ids), zone)
            self.assertTrue(any(self.rooms[rid].get('enemies') for rid in room_ids), zone)

    def test_room_npc_and_enemy_references_resolve(self):
        for rid, room in self.rooms.items():
            for npc in room.get('npcs', []):
                self.assertIn(npc, self.npcs, f'{rid}: {npc}')
            for enemy in room.get('enemies', []):
                self.assertIn(enemy, self.enemies, f'{rid}: {enemy}')

    def test_all_enemy_drops_resolve_to_items(self):
        for enemy, data in self.enemies.items():
            for drop in data.get('drops', []):
                self.assertIn(drop.get('item'), self.items, f'{enemy}: {drop}')
                self.assertGreaterEqual(drop.get('chance', 0), 0)
                self.assertLessEqual(drop.get('chance', 0), 1)

    def test_new_npcs_have_valid_factions_and_autonomy(self):
        names = {'采药人阿芷','失踪猎户的同伴','守祠残僧','北境货栈掌柜','巡河老兵','货船伙计小满'}
        for name in names:
            npc = self.npcs[name]
            self.assertIn(npc.get('faction'), self.factions)
            autonomy = npc.get('autonomy_profile', {})
            self.assertIs(autonomy.get('enabled'), True)
            self.assertTrue(autonomy.get('allowed_actions'))
            self.assertTrue(autonomy.get('route'))
            self.assertTrue(all(r in self.rooms for r in autonomy['route']))

    def test_new_items_have_chinese_descriptions_and_nonnegative_prices(self):
        names = {'雾露草','凝露丸','山獐肉','猎户旧图','沉河铜钱','潮纹石片','锈蚀令牌','北境肉干','商队封蜡','精制护腕','雾行短刃','沉河铁片'}
        for name in names:
            item = self.items[name]
            self.assertTrue(item.get('desc'))
            self.assertGreaterEqual(item.get('price', 0), 0)

    def test_region_content_levels_are_reasonable(self):
        for rid, room in self.rooms.items():
            if room.get('zone') not in self.zones:
                continue
            level = room.get('recommended_level', 0)
            for enemy_name in room.get('enemies', []):
                self.assertLessEqual(self.enemies[enemy_name].get('level', 1), level + 2, rid)
                self.assertGreaterEqual(self.enemies[enemy_name].get('level', 1), max(1, level - 2), rid)

if __name__ == '__main__':
    unittest.main()
