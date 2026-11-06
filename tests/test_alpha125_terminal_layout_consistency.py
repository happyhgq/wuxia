"""Alpha125：统一帮助、百科、背包的终端折行与区域术语。"""
import contextlib
import io
import unittest
from unittest.mock import patch

import engine
from main import show_help, show_encyclopedia, show_inventory
from player import Player
from ui_output import BODY_WIDTH, _ANSI_RE


class Alpha125TerminalLayoutConsistencyTests(unittest.TestCase):
    def capture(self, callback, *args, **kwargs):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            callback(*args, **kwargs)
        return _ANSI_RE.sub("", stream.getvalue())

    def test_region_help_uses_situation_and_danger_language(self):
        menu = self.capture(show_help)
        category = self.capture(show_help, "江湖与消息")
        region = self.capture(show_help, "区域")
        encyclopedia = self.capture(show_encyclopedia, "区域")
        self.assertIn("江湖与消息", menu)
        self.assertIn("【区域】", category)
        self.assertIn("区域局势与危险程度", region)
        self.assertIn("后台计算", encyclopedia)
        self.assertNotIn("区域指标", menu + category + region + encyclopedia)
        self.assertNotIn("区域安全、商路、通行和危险度", region)

    def test_inventory_long_description_wraps_without_losing_content(self):
        player = Player("界面测试侠客", "散人")
        item_name = "一柄名字特别长的江湖制式精钢长剑"
        description = "这是一段较长的装备说明，用于确认背包列表在终端中会自动折行，而不是把整条物品信息挤到屏幕之外。"
        player.inventory = [item_name]
        fake_items = {item_name: {"desc": description, "type": "weapon", "atk": 12, "price": 99}}
        with patch.object(engine, "ITEMS", fake_items):
            output = self.capture(show_inventory, player)
        self.assertIn(item_name, output)
        self.assertIn(description, output.replace("\n", ""))
        self.assertGreater(len(output.splitlines()), 4)
        item_lines = [line for line in output.splitlines() if item_name in line]
        self.assertTrue(item_lines)
        self.assertLessEqual(len(item_lines[0]), BODY_WIDTH)

    def test_help_long_topic_lines_are_wrapped(self):
        output = self.capture(show_help, "新手")
        self.assertIn("不强制按固定路线游玩", output.replace("\n", ""))
        # All lines except the deliberately decorative frame should fit the chosen terminal width.
        for line in output.splitlines():
            self.assertLessEqual(len(line), BODY_WIDTH, line)


if __name__ == "__main__":
    unittest.main()
