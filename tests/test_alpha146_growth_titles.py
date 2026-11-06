import contextlib
import io
import re
import unittest

from main import show_status
from player import Player
from actions import handle_skills


ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Alpha146GrowthTitleTests(unittest.TestCase):
    def test_character_level_titles_are_readable_and_do_not_change_level(self):
        p = Player("称号测试", "散人")
        cases = [(1, "初入江湖"), (5, "初窥门径"), (10, "略有小成"),
                 (15, "渐入佳境"), (20, "出类拔萃"), (30, "名动一方"),
                 (40, "一代高手"), (50, "武林宗师"), (99, "武林宗师")]
        for level, title in cases:
            with self.subTest(level=level):
                p.level = level
                self.assertEqual(p.get_character_realm_title(), title)
                self.assertEqual(p.level, level)

    def test_skill_mastery_titles_cover_progression(self):
        cases = [(0, "初学乍练"), (10, "略有小成"), (25, "驾轻就熟"),
                 (40, "融会贯通"), (60, "炉火纯青"), (80, "登峰造极"),
                 (100, "返璞归真")]
        for mastery, title in cases:
            with self.subTest(mastery=mastery):
                self.assertEqual(Player.get_skill_mastery_title(mastery, 100, True), title)
        self.assertEqual(Player.get_skill_mastery_title(100, 100, False), "尚未入门")

    def test_status_panel_shows_character_title(self):
        p = Player("状态称号测试", "散人")
        p.level = 10
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_status(p)
        text = ANSI.sub("", out.getvalue())
        self.assertIn("等级：        10 级（略有小成）", text)

    def test_skill_panel_shows_mastery_title(self):
        p = Player("武学称号测试", "散人")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_skills(p, [])
        text = ANSI.sub("", out.getvalue())
        self.assertIn("基础吐纳", text)
        self.assertIn("初学乍练", text)


if __name__ == "__main__":
    unittest.main()
