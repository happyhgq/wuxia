"""Alpha61：新增日常村民与城中闲人，验证资料、日程和可交谈内容。"""
import json
import os
import unittest

from player import Player
import engine

BASE = os.path.dirname(os.path.dirname(__file__))
NEW_NPCS = {
    '菜贩孙婶': 'village_square',
    '挑水老邱': 'village_south_street',
    '农家阿禾': 'village_north_street',
    '铁匠学徒小石': 'blacksmith',
    '货郎周四': 'guiyun_general_market',
    '马夫赵六': 'guiyun_stable',
    '书生陆文清': 'guiyun_central_square',
}

class Alpha61DailyVillagerTests(unittest.TestCase):
    def test_all_new_npcs_have_home_dialogue_and_daily_schedules(self):
        with open(os.path.join(BASE, 'data', 'npcs.json'), encoding='utf-8') as f:
            npcs = json.load(f)
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            rooms = json.load(f)
        for name, home in NEW_NPCS.items():
            with self.subTest(npc=name):
                self.assertIn(name, npcs)
                self.assertIn(name, rooms[home].get('npcs', []))
                self.assertTrue(npcs[name].get('dialogue'))
                self.assertTrue(npcs[name].get('daily_schedule'))
                self.assertTrue(npcs[name].get('dialogue_choices'))
                for entry in npcs[name]['daily_schedule']:
                    # T2 人物离场时段用 location=null 表示不在场景中。
                    if entry.get('location') is None:
                        self.assertEqual(npcs[name].get('schedule_tier'), 'T2')
                        continue
                    self.assertIn(entry.get('location'), rooms)

    def test_daily_schedule_moves_npcs_to_their_work_places(self):
        p = Player('日常人物测试')
        # tick 0 = 卯时 06:00；tick 2 对应 08:00。
        p.world_state.setdefault('variables', {})['quest_clock'] = 2
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location('菜贩孙婶'), 'public_drying_yard')
        self.assertEqual(p.get_npc_location('挑水老邱'), 'public_well')
        self.assertEqual(p.get_npc_location('农家阿禾'), 'farm_lane')
        self.assertEqual(p.get_npc_location('货郎周四'), 'guiyun_market_east')
        self.assertEqual(p.get_npc_location('马夫赵六'), 'guiyun_stable')
        self.assertEqual(p.get_npc_location('书生陆文清'), 'guiyun_central_square')

    def test_schedule_location_changes_with_world_clock(self):
        p = Player('日程变化测试')
        variables = p.world_state.setdefault('variables', {})
        variables['quest_clock'] = 6
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location('货郎周四'), 'guiyun_general_market')
        self.assertEqual(p.get_npc_location('农家阿禾'), 'farm_lane')
        variables['quest_clock'] = 12
        p.refresh_npc_schedules()
        self.assertEqual(p.get_npc_location('马夫赵六'), 'guiyun_stable')
        self.assertEqual(p.get_npc_location('书生陆文清'), 'guiyun_central_street_s')

if __name__ == '__main__':
    unittest.main()
