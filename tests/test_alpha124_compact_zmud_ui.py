"""Alpha124：场景与动态地图采用紧凑、易扫读的传统文字 MUD 排版。"""
import contextlib
import io
import unittest
from unittest.mock import patch

import engine
from actions import look
from player import Player
from ui_output import _ANSI_RE


class Alpha124CompactZmudUiTests(unittest.TestCase):
    def capture(self, callback, *args, **kwargs):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            callback(*args, **kwargs)
        return stream.getvalue()

    def test_scene_keeps_only_region_situation_and_danger(self):
        player = Player("界面测试侠客", "散人")
        player.location = "village_square"
        output = _ANSI_RE.sub("", self.capture(look, player, None, True))
        self.assertRegex(output, r"【区域局势】\s*平静\s*\|\s*危险度：一般")
        self.assertNotIn("区域指标：", output)
        self.assertNotIn("安全 72/100", output)

    def test_exit_list_is_inline_and_direction_order_is_stable(self):
        player = Player("界面测试侠客", "散人")
        player.location = "village_square"
        output = _ANSI_RE.sub("", self.capture(look, player, None, True))
        section = output.split("【可前往地点】", 1)[1].split("【人物】", 1)[0]
        self.assertIn("出口：北 →", section)
        self.assertIn("南 →", section)
        self.assertIn("东 →", section)
        self.assertLess(section.index("北 →"), section.index("南 →"))
        self.assertLess(section.index("南 →"), section.index("东 →"))
        self.assertNotIn("\n出口：", section)

    def test_people_are_rendered_once_per_line_with_state(self):
        player = Player("界面测试侠客", "散人")
        player.location = "village_square"
        with patch.object(player, "get_npcs_in_room", return_value=["甲人物", "乙人物"]), \
             patch.object(player, "get_npc_daily_activity", side_effect=[{"reason": "正在巡逻"}, {"reason": "在住处休息"}]):
            output = _ANSI_RE.sub("", self.capture(look, player, None, True))
        section = output.split("【人物】", 1)[1].split("【下一步可以做什么】", 1)[0]
        self.assertIn("甲人物：正在巡逻。", section)
        self.assertIn("乙人物：在住处休息。", section)
        self.assertNotIn("· 甲人物", section)
        self.assertEqual(section.count("甲人物"), 1)
        self.assertEqual(section.count("乙人物"), 1)

    def test_linear_map_uses_compact_node_spacing(self):
        rooms = {
            "a": {"name": "村长宅院", "zone": "main", "exits": {"东": "b"}},
            "b": {"name": "村北街", "zone": "main", "exits": {"西": "a", "东": "c"}},
            "c": {"name": "居民巷", "zone": "main", "exits": {"西": "b", "东": "d"}},
            "d": {"name": "公共水井", "zone": "main", "exits": {"西": "c"}},
        }
        rendered = _ANSI_RE.sub("", engine.MapEngine(rooms).render("b"))
        map_line = next(line for line in rendered.splitlines() if "村长宅院" in line)
        self.assertIn("[村长宅院]──", map_line)
        self.assertIn("──[公共水井]", map_line)
        self.assertNotIn("        [", map_line)
        positions = [map_line.index(name) for name in ("村长宅院", "村北街", "居民巷", "公共水井")]
        gaps = [positions[i + 1] - (positions[i] + len(("村长宅院", "村北街", "居民巷", "公共水井")[i])) for i in range(3)]
        self.assertLess(max(gaps), 12)


if __name__ == "__main__":
    unittest.main()
