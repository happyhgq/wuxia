# -*- coding: utf-8 -*-
"""Alpha300：NPC 五态行为纯函数与写时记录边界。"""
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest

import npc_behavior
import npc_utility
from actions import look
from player import Player


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


class NpcBehaviorPureTests(unittest.TestCase):
    def test_choose_behavior_has_exactly_five_states(self):
        self.assertEqual(
            npc_behavior.BEHAVIORS,
            ("idle", "working", "resting", "moving", "interacting"),
        )

    def test_schedule_state_maps_to_behavior_without_mutation(self):
        npc = {
            "daily_schedule": [
                {"start": 8, "end": 12, "state": "busy", "location": "medicine_shop"},
                {"start": 20, "end": 6, "state": "away", "location": None},
            ]
        }
        before = copy.deepcopy(npc)
        self.assertEqual(npc_behavior.choose_behavior(npc, 2), "working")  # 08:00
        self.assertEqual(npc_behavior.choose_behavior(npc, 14), "resting")  # 20:00
        self.assertEqual(npc, before)

    def test_uncovered_npc_uses_action_then_scene_status_then_idle(self):
        self.assertEqual(
            npc_behavior.choose_behavior({}, 0, {"action": "patrol"}), "moving")
        self.assertEqual(
            npc_behavior.choose_behavior({}, 0, {"action": "rest"}), "resting")
        self.assertEqual(
            npc_behavior.choose_behavior({}, 0, {"interacting": True}), "interacting")
        self.assertEqual(
            npc_behavior.choose_behavior({"scene_status": "守在广场指路"}, 0), "working")
        self.assertEqual(
            npc_behavior.choose_behavior({"scene_status": "在檐下歇息"}, 0), "resting")
        self.assertEqual(npc_behavior.choose_behavior({}, 0), "idle")

    def test_schedule_entry_lookup_supports_overnight_windows(self):
        entry = {
            "daily_schedule": [
                {"start": 22, "end": 6, "state": "busy", "location": "village_gate"}
            ]
        }
        schedule = entry["daily_schedule"]
        self.assertIsNotNone(npc_utility.active_schedule_entry(schedule, 17))  # 23:00
        self.assertIsNotNone(npc_utility.active_schedule_entry(schedule, 23))  # 05:00
        self.assertIsNone(npc_utility.active_schedule_entry(schedule, 6))  # 12:00


class NpcBehaviorWriteTickTests(unittest.TestCase):
    def test_read_only_look_does_not_create_behavior_records(self):
        player = Player("行为只读", "散人")
        player.location = "village_gate"
        capture(look, player)
        self.assertIsNone(player.get_npc_behavior("青石村接引人"))
        self.assertNotIn("npc_behaviors", player.world_state.get("variables", {}))

    def test_world_tick_records_only_npcs_not_covered_by_schedule(self):
        player = Player("行为写时", "散人")
        player.set_var("quest_clock", 0)
        player.tick_quest_clock(1)
        variables = player.world_state["variables"]
        self.assertIn("npc_behaviors", variables)
        self.assertNotIn("npc_behaviors", player.world_state)
        self.assertIsNotNone(player.get_npc_behavior("青石村接引人"))
        self.assertIn(player.get_npc_behavior("青石村接引人")["behavior"],
                      npc_behavior.BEHAVIORS)
        # 铁匠有覆盖全天的 T1 日程，写 tick 也不得用行为层覆盖日程。
        self.assertIsNone(player.get_npc_behavior("铁匠"))

    def test_behavior_records_survive_v12_save_without_top_level_field(self):
        player = Player("行为存档", "散人")
        player.set_var("quest_clock", 0)
        player.tick_quest_clock(1)
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            player.save_to_file(path)
            with open(path, encoding="utf8") as handle:
                raw = json.load(handle)
            self.assertEqual(raw["version"], 12)
            self.assertNotIn("npc_behaviors", raw)
            self.assertIn("npc_behaviors", raw["world_state"]["variables"])
            loaded = Player.load_from_file(path)
            self.assertEqual(
                loaded.get_npc_behavior("青石村接引人"),
                player.get_npc_behavior("青石村接引人"),
            )
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
