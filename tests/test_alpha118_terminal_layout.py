import contextlib
import io
import unittest

import engine
from actions import look
from main import show_help, show_status
from player import Player


class Alpha118TerminalLayoutTests(unittest.TestCase):
    def capture(self, callback, *args, **kwargs):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            callback(*args, **kwargs)
        return stream.getvalue()

    def test_status_panel_splits_combat_stats_and_equipment_into_readable_lines(self):
        player = Player("界面排版测试侠客", "散人")
        output = self.capture(show_status, player)
        combat = self.capture(show_status, player, "combat")
        self.assertIn("========== 侠客状态 ==========", output)
        self.assertIn("攻击：", combat)
        self.assertIn("防御：", combat)
        self.assertNotIn("兵刃：", output)
        self.assertNotIn("防具：", output)
        self.assertIn("身上状态：", combat)
        self.assertNotIn("攻击：10 (基础10)  防御：5", combat)

    def test_scene_region_metrics_and_caravan_actions_are_separated(self):
        player = Player("场景排版测试", "散人")
        player.location = "village_square"
        output = self.capture(look, player, None, True)
        self.assertIn("【环境】", output)
        self.assertIn("【区域局势】", output)
        self.assertNotIn("区域指标：安全", output)
        self.assertRegex(output, r"【区域局势】.*平静.*危险度：一般")
        self.assertIn("【下一步可以做什么】", output)
        self.assertLess(output.index("【环境】"), output.index("【区域局势】"))

    def test_all_numbered_help_entries_have_details(self):
        # The public menu should never send a player into an empty placeholder entry.
        import help_system
        for category_no, category in enumerate(help_system.CATEGORIES, 1):
            for entry_no in range(1, len(category["entries"]) + 1):
                with self.subTest(category=category["id"], entry=entry_no):
                    output = self.capture(show_help, f"{category_no} {entry_no}")
                    self.assertNotIn("详细说明正在整理中", output)
                    self.assertIn("用途：", output)
                    self.assertIn("用法：", output)

    def test_map_layout_expands_for_long_room_names_without_losing_labels(self):
        rooms = {
            "a": {"name": "青石村南门外的长街入口", "zone": "main", "exits": {"东": "b"}},
            "b": {"name": "天衡广场", "zone": "main", "exits": {"西": "a"}},
        }
        rendered = engine.MapEngine(rooms).render("a")
        self.assertIn("青石村南门外的长街入口", rendered)
        self.assertIn("天衡广场", rendered)
        # Adaptive columns preserve both labels instead of writing one over another.
        lines = rendered.splitlines()
        self.assertTrue(any("青石村南门外的长街入口" in line for line in lines))
        self.assertTrue(any("天衡广场" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
