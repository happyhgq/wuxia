"""Alpha98：最终验收——世界长跑、V12 存档往返及动态经济状态边界。"""
import contextlib
import io
import json
import os
import random
import tempfile
import unittest

import engine
from player import Player


class Alpha98FinalAcceptanceTests(unittest.TestCase):
    def test_world_runs_2000_ticks_and_remains_json_serializable(self):
        random.seed(20261017)
        player = Player("最终验收侠客", "散人")
        player.tick_quest_clock(2000)

        self.assertEqual(player.get_quest_clock(), 2000)
        self.assertEqual(engine.SAVE_VERSION, 12)
        self.assertIsInstance(player.world_state, dict)
        self.assertIsInstance(player.world_state.get("flags"), dict)
        self.assertIsInstance(player.world_state.get("variables"), dict)
        self.assertIsInstance(player.economy_state, dict)
        payload = {
            "version": engine.SAVE_VERSION,
            "world_state": player.world_state,
            "economy_state": player.economy_state,
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(encoded)
        self.assertEqual(json.loads(encoded)["version"], 12)

    def test_v12_save_load_roundtrip_preserves_world_clock_and_economy(self):
        random.seed(20261017)
        player = Player("存档验收侠客", "散人")
        player.tick_quest_clock(100)
        expected_clock = player.get_quest_clock()
        expected_economy = json.loads(json.dumps(player.economy_state, ensure_ascii=False))

        with tempfile.TemporaryDirectory() as directory:
            save_path = os.path.join(directory, "acceptance_save.json")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(player.save_to_file(save_path))
                loaded = Player.load_from_file(save_path)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.get_quest_clock(), expected_clock)
            self.assertEqual(loaded.economy_state, expected_economy)
            with open(save_path, "r", encoding="utf-8") as stream:
                raw = json.load(stream)
            self.assertEqual(raw["version"], 12)
            self.assertIn("world_state", raw)
            self.assertIn("economy_state", raw)


if __name__ == "__main__":
    unittest.main()
