import contextlib
import io
import unittest
from unittest.mock import patch

from actions import look
from ui_output import _ANSI_RE
from player import Player


class Alpha119SceneReadabilityTests(unittest.TestCase):
    def capture(self, callback, *args, **kwargs):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            callback(*args, **kwargs)
        return stream.getvalue()

    def test_exits_are_compact_and_directional(self):
        player = Player("排版测试侠客", "散人")
        player.location = "village_square"
        output = self.capture(look, player, None, True)
        self.assertIn("【可前往地点】", output)
        visible = _ANSI_RE.sub("", output)
        section = visible.split("【可前往地点】", 1)[1].split("【人物】", 1)[0]
        self.assertIn("出口：", section)
        exit_lines = [line.strip() for line in section.splitlines() if "→" in line]
        self.assertGreater(len(exit_lines), 0)
        self.assertTrue(any("出口：" in line for line in exit_lines))
        self.assertIn("北", section)
        self.assertIn("南", section)

    def test_people_are_not_joined_into_one_long_line(self):
        player = Player("排版测试侠客", "散人")
        player.location = "village_square"
        with patch.object(player, "get_npcs_in_room", return_value=["甲人物", "乙人物", "丙人物"]):
            output = self.capture(look, player, None, True)
        visible = _ANSI_RE.sub("", output)
        section = visible.split("【人物】", 1)[1].split("【下一步可以做什么】", 1)[0]
        self.assertIn("甲人物：", section)
        self.assertIn("乙人物：", section)
        self.assertIn("丙人物：", section)
        self.assertNotIn("· 甲人物", section)
        self.assertNotIn("甲人物, 乙人物, 丙人物", section)

    def test_caravan_guidance_separates_browse_and_sell_actions(self):
        source = open("actions.py", encoding="utf-8").read()
        self.assertIn('查看货物：商店 {caravan_name}', source)
        self.assertIn('出售物品：出售 物品 数量 给 {caravan_name}', source)
        self.assertNotIn('操作：输入“商店 {caravan_name}”查看货物；输入“出售 物品 数量 给 {caravan_name}”', source)


if __name__ == "__main__":
    unittest.main()
