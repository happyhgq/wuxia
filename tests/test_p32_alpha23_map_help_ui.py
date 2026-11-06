import json
import os
import unittest
import io
import contextlib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Alpha23MapHelpUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)
        with open(os.path.join(BASE, 'data', 'economy', 'resources.json'), encoding='utf-8') as f:
            cls.resources = json.load(f)

    def test_multiple_real_mining_logging_and_forage_locations_exist(self):
        mine = [rid for rid, cfg in self.resources.items() if cfg.get('action', 'mine') == 'mine']
        chop = [rid for rid, cfg in self.resources.items() if cfg.get('action') == 'chop']
        forage = [rid for rid, room in self.rooms.items() if room.get('forage') and any(x in room['forage'] for x in ('草药', '木材'))]
        self.assertGreaterEqual(len(mine), 3)
        self.assertGreaterEqual(len(chop), 3)
        self.assertGreaterEqual(len(forage), 3)
        self.assertTrue(set(mine + chop).issubset(self.rooms))

    def test_new_resource_rooms_are_reciprocally_reachable(self):
        custom = {'内', '外', '后', '前'}
        for rid, room in self.rooms.items():
            for direction, target in room.get('exits', {}).items():
                self.assertIn(target, self.rooms, (rid, target))
                if direction in custom:
                    # 自定义出入口只要求目标房间有反向路径。
                    back = {'内': '外', '外': '内', '后': '前', '前': '后'}[direction]
                    self.assertEqual(self.rooms[target].get('exits', {}).get(back), rid, (rid, direction, target))
                    continue
                if room.get('zone', 'main') == self.rooms[target].get('zone', 'main'):
                    opposite = {'北':'南', '南':'北', '东':'西', '西':'东'}[direction]
                    reverse = self.rooms[target].get('exits', {}).get(opposite)
                    hidden_reverse = self.rooms[target].get('hidden_exits', {}).get(opposite, {})
                    self.assertTrue(reverse == rid or (isinstance(hidden_reverse, dict) and hidden_reverse.get('target') == rid), (rid, direction, target))
        for rid in ('bamboo_hollow', 'old_woodlot', 'deep_iron_gallery', 'collapsed_quarry', 'herb_springbank', 'rocky_herb_slope'):
            self.assertIn(rid, self.rooms)

    def test_new_mining_and_logging_rooms_use_real_economy_harvest(self):
        from economy import EconomyManager
        manager = EconomyManager(data_dir=os.path.join(BASE, 'data', 'economy'))
        for room in ('deep_iron_gallery', 'collapsed_quarry'):
            ok, result = manager.mine(room)
            self.assertTrue(ok, room)
            self.assertEqual(result[0], '铁矿石')
        for room in ('bamboo_hollow', 'old_woodlot'):
            ok, result = manager.chop(room)
            self.assertTrue(ok, room)
            self.assertEqual(result[0], '木材')

    def test_resource_commands_are_explained_in_help(self):
        from main import show_help
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_help('采集')
        text = out.getvalue()
        for word in ('采矿', '伐木', '采集', '竹影幽谷', '铁脉长廊'):
            self.assertIn(word, text)

    def test_help_menu_is_grouped_and_has_people_category(self):
        from main import show_help
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_help()
        text = out.getvalue()
        self.assertIn('【二】交谈与人物', text)
        self.assertIn('【一】查看与移动', text)
        self.assertIn('帮助 指令名', text)

    def test_room_interaction_phrases_and_commands_are_colored(self):
        from actions import _highlight_room_desc
        text = _highlight_room_desc('此处可伐木，输入“伐木”采集木材；岩壁可见铁矿脉。')
        self.assertIn('\x1b[92m可伐木', text)
        self.assertIn('\x1b[96m“伐木”', text)
        self.assertIn('\x1b[93m铁矿脉', text)

if __name__ == '__main__':
    unittest.main()
