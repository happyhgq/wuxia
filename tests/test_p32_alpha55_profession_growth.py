"""Alpha55：玩家采集职业成长、收益上限与旧存档兼容。"""
import contextlib
import io
import json
import os
import tempfile
import unittest
import engine
from player import Player
from economy import EconomyManager
from main import CMD_MAP, show_help


class Alpha55ProfessionGrowthTests(unittest.TestCase):
    def test_profession_levels_progress_and_roundtrip(self):
        manager = EconomyManager({})
        self.assertEqual(manager.profession_level("chop"), 1)
        first = manager.record_profession_action("chop", 5)
        self.assertTrue(first["leveled_up"])
        self.assertEqual(first["level"], 2)
        second = manager.record_profession_action("chop", 10)
        self.assertTrue(second["leveled_up"])
        self.assertEqual(second["level"], 3)
        resumed = EconomyManager(manager.export_state())
        self.assertEqual(resumed.profession_level("chop"), 3)
        row = next(x for x in resumed.profession_summary() if x["name"] == "伐木")
        self.assertEqual(row["xp"], 15)
        self.assertEqual(row["total_gathered"], 15)

    def test_level_three_bonus_is_limited_by_resource_and_inventory_space(self):
        manager = EconomyManager({
            "professions": {"伐木": {"xp": 15, "level": 3, "actions": 5, "total_gathered": 15}},
            "resources": {"mistwood_trail": {"remaining": 10, "last_tick": 0}},
        })
        ok, result = manager.chop("mistwood_trail", 3, max_quantity=4)
        self.assertTrue(ok)
        self.assertEqual(result, ("木材", 4))
        self.assertEqual(manager.state.resources["mistwood_trail"]["remaining"], 6)
        ok, result = manager.chop("mistwood_trail", 3, max_quantity=2)
        self.assertTrue(ok)
        self.assertEqual(result, ("木材", 2))

    def test_old_v12_economy_state_defaults_professions_safely(self):
        manager = EconomyManager({"tick": 7, "resources": {}, "npc_inventory": {}})
        self.assertEqual(manager.profession_level("gather"), 1)
        manager.update(1)
        resumed = EconomyManager(manager.export_state())
        self.assertEqual(resumed.state.tick, 8)
        self.assertEqual(resumed.profession_summary()[0]["level"], 1)

    def test_profession_progress_survives_real_v12_save_load(self):
        player = Player("营生测试侠客")
        manager = EconomyManager(player.economy_state)
        manager.record_profession_action("mine", 15)
        player.economy_state = manager.export_state()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "save.json")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(player.save_to_file(path))
                loaded = Player.load_from_file(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.economy_state["professions"]["采矿"]["xp"], 15)
            self.assertEqual(loaded.economy_state["professions"]["采矿"]["level"], 3)
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            self.assertEqual(raw["version"], 12)
            self.assertEqual(engine.SAVE_VERSION, 12)

    def test_profession_command_and_help_are_registered(self):
        self.assertEqual(CMD_MAP["职业"], "profession")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_help("职业")
        self.assertIn("熟练等级", out.getvalue())
        self.assertIn("职业", out.getvalue())


if __name__ == "__main__":
    unittest.main()
