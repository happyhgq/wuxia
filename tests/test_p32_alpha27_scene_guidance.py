import json
import os
import re
import unittest
from unittest.mock import patch

import actions
import engine

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Alpha27SceneGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, "data", "economy", "resources.json"), encoding="utf-8") as f:
            cls.resources = json.load(f)

    def test_scene_action_hints_only_suggest_real_resource_commands(self):
        chop_room = next(room_id for room_id, cfg in self.resources.items() if cfg.get("action") == "chop")
        mine_room = next(room_id for room_id, cfg in self.resources.items() if cfg.get("action") != "chop")
        chop = actions._scene_action_hints(chop_room, engine.ROOMS[chop_room], self.resources)
        mine = actions._scene_action_hints(mine_room, engine.ROOMS[mine_room], self.resources)
        self.assertIn("伐木", chop)
        self.assertNotIn("采矿", chop)
        self.assertIn("采矿", mine)
        self.assertNotIn("伐木", mine)

    def test_depleted_resource_hint_does_not_claim_resource_is_ready(self):
        room_id = next(room_id for room_id, cfg in self.resources.items() if cfg.get("action") == "chop")
        cfg = self.resources[room_id]
        state = {"resources": {room_id: {"remaining": 0}}}
        hint = actions._scene_action_hints(room_id, engine.ROOMS[room_id], self.resources, economy_state=state)
        self.assertIn("资源恢复后可用", hint)

    def test_highlighting_preserves_visible_words_and_adds_terminal_colors(self):
        original = '林间可持续恢复的林木，输入“伐木”获取木材。'
        highlighted = actions._highlight_room_desc(original)
        self.assertEqual(original, ANSI.sub("", highlighted))
        self.assertIn(engine.Color.BRIGHT_GREEN, highlighted)
        self.assertIn(engine.Color.BRIGHT_CYAN, highlighted)

    def test_look_shows_exit_directions_and_action_guidance(self):
        class FakePlayer:
            location = "village_gate"
            economy_state = {}
            def propagate_npc_information(self, _): pass
            def get_region_ecology(self, _):
                return {"level": "calm", "danger": "safe", "security": 80, "commerce": 50, "travel": 80}
            def get_npcs_in_room(self, _): return []
            def get_npc_encounters(self, _): return []

        from io import StringIO
        output = StringIO()
        with patch("sys.stdout", output):
            actions.look(FakePlayer(), show_guidance=True)
        visible = ANSI.sub("", output.getvalue())
        self.assertIn("出口：", visible)
        self.assertIn("可用操作：", visible)
        self.assertIn("查看", visible)
        self.assertIn("地图", visible)
        self.assertIn("建议", visible)


    def test_scene_guidance_is_hidden_by_default_after_startup(self):
        class FakePlayer:
            location = "village_gate"
            economy_state = {}
            def propagate_npc_information(self, _): pass
            def get_region_ecology(self, _):
                return {"level": "calm", "danger": "safe", "security": 80, "commerce": 50, "travel": 80}
            def get_npcs_in_room(self, _): return []
            def get_npc_encounters(self, _): return []

        from io import StringIO
        output = StringIO()
        with patch("sys.stdout", output):
            actions.look(FakePlayer())
        visible = ANSI.sub("", output.getvalue())
        self.assertNotIn("可用操作：", visible)
        self.assertNotIn("不确定下一步时", visible)

    def test_player_facing_hints_do_not_leak_internal_room_identifiers(self):
        hint = actions._scene_action_hints("village_gate", engine.ROOMS["village_gate"])
        self.assertNotIn("village_gate", hint)
        self.assertNotIn("room:", hint.lower())


if __name__ == "__main__":
    unittest.main()
