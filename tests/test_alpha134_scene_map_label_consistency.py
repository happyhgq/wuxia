"""Alpha134：场景出口、地图及已发现的隐蔽出口统一使用显示名称。"""
import contextlib
import io
import unittest

from player import Player
from actions import look
from main import show_map
from ui_output import _ANSI_RE


class Alpha134SceneMapLabelConsistencyTests(unittest.TestCase):
    def capture(self, fn, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            fn(*args)
        return _ANSI_RE.sub("", output.getvalue())

    def test_scene_exit_uses_same_road_label_as_map(self):
        player = Player("路线测试", "散人")
        player.location = "official_road"
        scene = self.capture(look, player, None, False)
        map_output = self.capture(show_map, player)
        self.assertIn("东 → 黄土官道（东段）", scene)
        self.assertIn("东 -> 黄土官道（东段）", map_output)

    def test_gate_scene_uses_disambiguated_road_label(self):
        player = Player("路线测试", "散人")
        player.location = "village_gate"
        scene = self.capture(look, player, None, False)
        self.assertIn("南 → 黄土官道（村口段）", scene)

    def test_hidden_exit_label_appears_only_after_discovery(self):
        player = Player("路线测试", "散人")
        player.location = "sunken_channel"
        hidden_target = "sunken_cache"
        hidden_name = __import__("engine").ROOMS[hidden_target]["name"]
        undiscovered = self.capture(show_map, player)
        self.assertNotIn(hidden_name, undiscovered)
        player.set_flag("explore:sunken_channel:cache_found", True)
        discovered = self.capture(show_map, player)
        self.assertIn(f"东 → {hidden_name}", discovered)


if __name__ == "__main__":
    unittest.main()
