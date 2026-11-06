"""Alpha55：探索发现可开启隐藏出口，并接入真实资源储量。"""
import contextlib
import io
import json
import os
import unittest
import engine
from actions import handle_explore, look
from economy import EconomyManager
from main import resolve_room_exit, show_map
from player import Player

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha55HiddenExplorationTests(unittest.TestCase):
    def test_hidden_cache_is_not_a_normal_exit_before_discovery(self):
        room = engine.ROOMS["sunken_channel"]
        self.assertNotIn("东", room.get("exits", {}))
        self.assertEqual(room["hidden_exits"]["东"]["target"], "sunken_cache")
        player = Player("测试侠客")
        player.location = "sunken_channel"
        destination, message = resolve_room_exit(player, room, "东")
        self.assertIsNone(destination)
        self.assertIn("先在地下暗渠输入", message)

    def test_exploration_unlocks_hidden_cache_and_return_exit_works(self):
        player = Player("测试侠客")
        player.location = "sunken_channel"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_explore(player)
        self.assertTrue(player.get_flag("explore:sunken_channel:cache_found"))
        destination, message = resolve_room_exit(player, engine.ROOMS["sunken_channel"], "东")
        self.assertEqual(destination, "sunken_cache")
        self.assertEqual(message, "")
        self.assertEqual(engine.ROOMS["sunken_cache"]["exits"]["西"], "sunken_channel")

    def test_discovered_hidden_exit_is_shown_in_map_output(self):
        player = Player("测试侠客")
        player.location = "sunken_channel"
        player.set_flag("explore:sunken_channel:cache_found", True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            show_map(player)
        self.assertIn("已发现的隐蔽出口", out.getvalue())
        self.assertIn("沉河暗库", out.getvalue())

    def test_discovered_hidden_exit_is_shown_in_scene_description(self):
        player = Player("测试侠客")
        player.location = "sunken_channel"
        player.set_flag("explore:sunken_channel:cache_found", True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            look(player)
        self.assertIn("东", out.getvalue())
        self.assertIn("沉河暗库", out.getvalue())

    def test_hidden_room_resource_is_finite_and_persisted(self):
        with open(os.path.join(BASE, "data", "economy", "resources.json"), encoding="utf-8") as f:
            resources = json.load(f)
        self.assertEqual(resources["sunken_cache"]["action"], "gather")
        manager = EconomyManager({"resources": {"sunken_cache": {"remaining": 2, "last_tick": 0}}})
        ok, result = manager.gather("sunken_cache", 1)
        self.assertTrue(ok)
        self.assertEqual(result, ("雾露草", 1))
        self.assertEqual(EconomyManager(manager.export_state()).state.resources["sunken_cache"]["remaining"], 1)


if __name__ == "__main__":
    unittest.main()
