# -*- coding: utf-8 -*-
"""P3.1.8 阶段 28–30：存档备份与损坏恢复专项测试。"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import engine
from player import Player


class SaveRecoveryPhase2830Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "save.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_save_creates_previous_valid_v12_backup(self):
        player = Player("备份测试侠", "散人")
        player.gold = 111
        self.assertTrue(player.save_to_file(self.path))
        player.gold = 222
        self.assertTrue(player.save_to_file(self.path))

        with open(self.path + ".bak", encoding="utf-8") as f:
            backup = json.load(f)
        with open(self.path, encoding="utf-8") as f:
            current = json.load(f)
        self.assertEqual(backup["version"], 12)
        self.assertEqual(backup["gold"], 111)
        self.assertEqual(current["gold"], 222)
        self.assertNotIn("gold", backup.get("world_state", {}))

    def test_corrupt_primary_restores_previous_backup_without_changing_schema(self):
        player = Player("恢复测试侠", "散人")
        player.gold = 80
        self.assertTrue(player.save_to_file(self.path))
        player.gold = 95
        self.assertTrue(player.save_to_file(self.path))

        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"version":12,broken-json')
        with patch("builtins.print") as output:
            restored = Player.load_from_file(self.path)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.name, "恢复测试侠")
        self.assertEqual(restored.gold, 80)
        self.assertTrue(any("存档恢复" in str(call.args[0]) for call in output.call_args_list if call.args))
        with open(self.path + ".bak", encoding="utf-8") as f:
            backup = json.load(f)
        self.assertEqual(backup["version"], 12)

    def test_terminal_width_ignores_ansi_and_counts_chinese(self):
        self.assertEqual(engine.get_display_width("江湖"), 4)
        self.assertEqual(engine.get_display_width("\033[31m江湖\033[0m"), 4)
        self.assertEqual(engine.get_display_width("A江B"), 4)
        self.assertEqual(engine.get_display_width("e\u0301"), 1)
        padded = engine.pad_to_width("\033[32m江湖\033[0m", 8, "left")
        self.assertEqual(engine.get_display_width(padded), 8)

    def test_parseable_but_wrong_typed_identity_fields_are_normalized(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"version": 12, "name": None, "sect": ["少林"], "gold": 88}, f)
        with patch("builtins.print"):
            restored = Player.load_from_file(self.path)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.name, "无名侠客")
        self.assertEqual(restored.get_sect(), "散人")
        self.assertEqual(restored.gold, 88)

    def test_failed_primary_replace_keeps_existing_save_intact(self):
        player = Player("原存档侠", "散人")
        player.gold = 111
        self.assertTrue(player.save_to_file(self.path))
        player.gold = 222
        real_replace = os.replace

        def fail_only_primary(source, destination):
            if os.path.abspath(destination) == os.path.abspath(self.path):
                raise OSError("模拟主存档替换中断")
            return real_replace(source, destination)

        with patch("player.os.replace", side_effect=fail_only_primary), patch("builtins.print"):
            self.assertFalse(player.save_to_file(self.path))
        with open(self.path, "r", encoding="utf-8") as f:
            current = json.load(f)
        self.assertEqual(current["gold"], 111)
        self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(self.tmp.name)))

    def test_invalid_primary_and_invalid_backup_fail_gracefully(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("not-json")
        with open(self.path + ".bak", "w", encoding="utf-8") as f:
            f.write("also-not-json")
        with patch("builtins.print"):
            self.assertIsNone(Player.load_from_file(self.path))


if __name__ == "__main__":
    unittest.main()
