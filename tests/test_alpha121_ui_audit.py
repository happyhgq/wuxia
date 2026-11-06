import contextlib
import io
import unittest

import engine
from main import show_map, show_status
from player import Player
from ui_output import _ANSI_RE


class Alpha121UIAuditTests(unittest.TestCase):
    def capture(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fn(*args)
        return _ANSI_RE.sub('', out.getvalue())

    def test_status_separates_secondary_attributes_and_attribute_points(self):
        player = Player('排版审查侠客', '散人')
        output = self.capture(show_status, player, 'combat')
        self.assertIn('其他属性：', output)
        self.assertIn('可用属性点：', output)
        self.assertNotIn('属性续项：', output)

    def test_discovered_hidden_exits_are_listed_one_per_line(self):
        original_rooms = engine.ROOMS
        original_engine = engine.MAP_ENGINE
        try:
            engine.ROOMS = {
                'test_room': {'name': '测试地点', 'hidden_exits': {
                    '东': {'flag': 'hidden_east_found', 'target': 'east_room'},
                    '北': {'flag': 'hidden_north_found', 'target': 'north_room'},
                }},
                'east_room': {'name': '东侧密道'},
                'north_room': {'name': '北侧隐秘石阶'},
            }
            class DummyMap:
                def render(self, location, player=None):
                    return '测试地图'
            engine.MAP_ENGINE = DummyMap()
            player = Player('排版审查侠客', '散人')
            player.location = 'test_room'
            player.set_flag('hidden_east_found', True)
            player.set_flag('hidden_north_found', True)
            output = self.capture(show_map, player)
            self.assertIn('已发现的隐蔽出口：\n  - 东 → 东侧密道\n  - 北 → 北侧隐秘石阶', output)
        finally:
            engine.ROOMS = original_rooms
            engine.MAP_ENGINE = original_engine


if __name__ == '__main__':
    unittest.main()
