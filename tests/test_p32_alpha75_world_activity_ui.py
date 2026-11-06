"""Alpha75：世界营生动态必须能被玩家通过公开中文指令查看。"""
import contextlib
import io
import unittest

from actions import handle_world_activity
from economy import EconomyManager
import main


class Alpha75WorldActivityUITests(unittest.TestCase):
    def test_command_aliases_are_public_chinese(self):
        self.assertEqual(main.CMD_MAP.get("世界动态"), "world_activity")
        self.assertEqual(main.CMD_MAP.get("营生动态"), "world_activity")

    def test_world_activity_command_displays_real_records(self):
        manager = EconomyManager()
        manager.update(120)
        player = type("PlayerStub", (), {"economy_state": manager.export_state()})()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_world_activity(player, ["5"])
        text = out.getvalue()
        self.assertIn("江湖营生动态", text)
        self.assertTrue(any(word in text for word in ("采集", "制作", "交易")))
        self.assertNotIn("world_activity", text)
        self.assertNotIn("confrontation", text)

    def test_empty_state_has_friendly_message(self):
        player = type("PlayerStub", (), {"economy_state": {}})()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_world_activity(player)
        self.assertIn("目前还没有可供查看的营生动态", out.getvalue())

    def test_help_mentions_world_activity(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main.show_help("世界动态")
        text = out.getvalue()
        self.assertIn("世界动态", text)
        self.assertIn("查看人物近期真实采集、制作和交易记录", text)


if __name__ == "__main__":
    unittest.main()
