import contextlib
import io
import re
import unittest

from main import show_status
from player import Player


ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Alpha128StatusPanelTests(unittest.TestCase):
    def capture(self, player, panel="combat"):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            show_status(player, panel)
        return ANSI.sub("", stream.getvalue())

    def test_route_tendencies_are_compact_horizontal_line(self):
        output = self.capture(Player("排版测试", "散人"), "growth")
        route_line = next(line for line in output.splitlines() if line.startswith("路线倾向："))
        self.assertIn("侠客 0", route_line)
        self.assertIn("官府 0", route_line)
        self.assertIn("商会 0", route_line)
        self.assertIn("黑市 0", route_line)
        self.assertIn("独行 0", route_line)
        self.assertNotIn("路线倾向：\n", output)

    def test_identity_and_combat_sections_are_separated(self):
        output = self.capture(Player("排版测试", "散人"), "combat")
        self.assertIn("========== 战斗属性 ==========", output)
        self.assertIn("身上状态：", output)
        self.assertIn("攻击：", output)
        self.assertIn("防御：", output)

    def test_status_labels_are_not_split_to_align(self):
        player = Player("排版测试", "散人")
        output = self.capture(player, "sect") + self.capture(player, "combat") + self.capture(player, "main")
        for label in ("姓名：", "门派职位：", "等级：", "攻击：", "防御："):
            self.assertIn(label, output)
        self.assertNotIn("姓       名：", output)
        self.assertNotIn("等      级：", output)


if __name__ == "__main__":
    unittest.main()
