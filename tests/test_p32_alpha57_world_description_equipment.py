"""Alpha57：场景、物品、武学与人物描写及 NPC 装备数据校验。"""
import contextlib
import io
import json
import os
import unittest
from actions import look
from player import Player

BASE = os.path.dirname(os.path.dirname(__file__))


def read(name):
    with open(os.path.join(BASE, 'data', name), encoding='utf-8') as f:
        return json.load(f)


class Alpha57DescriptionEquipmentTests(unittest.TestCase):
    def test_npc_equipment_references_real_equipable_items(self):
        npcs, items = read('npcs.json'), read('items.json')
        equipped = 0
        for npc, data in npcs.items():
            loadout = data.get('equipment', {})
            self.assertIsInstance(loadout, dict, npc)
            for slot, item in loadout.items():
                self.assertIn(item, items, f'{npc} equipment missing item {item}')
                self.assertEqual(items[item].get('slot'), slot, f'{npc} slot mismatch for {item}')
                equipped += 1
        self.assertGreaterEqual(equipped, 10)

    def test_inspecting_npc_shows_worn_gear(self):
        p = Player('测试侠客')
        # 选 13:00（tick 7）避开守卫巡逻日程，使其回到村口。
        p.set_var('quest_clock', 7)
        p.location = 'village_gate'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            look(p, ['守卫'])
        self.assertIn('装备着：', out.getvalue())
        self.assertIn('红缨枪(hong ying qiang)', out.getvalue())

    def test_items_and_skills_have_practical_descriptions(self):
        items, skills = read('items.json'), read('skills.json')
        self.assertTrue(all(str(v.get('desc', '')).strip() for v in items.values()))
        self.assertTrue(all(str(v.get('use_hint', '')).strip() for v in items.values()))
        all_skills = [row for rows in skills.values() for row in rows]
        self.assertTrue(all(str(s.get('desc', '')).strip() for s in all_skills))
        self.assertTrue(all(str(s.get('combat_hint', '')).strip() for s in all_skills))

    def test_selected_scene_descriptions_are_richer_without_losing_exits(self):
        rooms = read('rooms.json')
        for rid in ('village_gate', 'village_square', 'mistwood_trail', 'deep_iron_gallery', 'guiyun_central_square', 'guiyun_martial_hall', 'mistwood_stream'):
            self.assertTrue(rooms[rid].get('desc'))
            self.assertTrue(rooms[rid].get('exits') or rooms[rid].get('hidden_exits'))


if __name__ == '__main__':
    unittest.main()
