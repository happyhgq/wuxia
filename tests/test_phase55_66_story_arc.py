import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
from actions import handle_quest, handle_talk_and_ask
from data_validator import main as validate_data
from player import Player

BASE = Path(__file__).resolve().parents[1]


class Phase55To66StoryArcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quests = json.loads((BASE / "data" / "quests.json").read_text(encoding="utf-8"))
        cls.events = json.loads((BASE / "data" / "world_events.json").read_text(encoding="utf-8"))
        cls.items = json.loads((BASE / "data" / "items.json").read_text(encoding="utf-8"))
        cls.npcs = json.loads((BASE / "data" / "npcs.json").read_text(encoding="utf-8"))

    def _player_ready_for_arc(self, name="阶段55测试侠客"):
        p = Player(name, "散人")
        p.level = 10
        p.completed_quests.append("暗仓转运疑云")
        p.set_flag("quest:transfer_warehouse:resolved", True)
        p.set_flag("world:trade_network:warehouse_evidence_secured", True)
        p.set_flag("world:trade_network:warehouse_reviewed", True)
        return p

    def test_noninteractive_startup_does_not_leak_terminal_environment_warning(self):
        output = io.StringIO()
        with patch.object(sys, "stdout", output), patch.object(engine.os, "system") as shell_clear:
            engine.clear_screen()
        shell_clear.assert_not_called()
        self.assertEqual(output.getvalue(), "")

    def test_data_validator_passes(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = validate_data()
        self.assertEqual(result, 0, output.getvalue())
        self.assertIn("DATA VALIDATION: PASS", output.getvalue())

    def test_main_arc_waits_for_warehouse_review_and_npc_clue_is_player_facing(self):
        p = Player("剧情依赖测试侠客", "散人")
        p.level = 10
        p.completed_quests.append("暗仓转运疑云")
        p.set_flag("quest:transfer_warehouse:resolved", True)
        p.set_flag("world:trade_network:warehouse_evidence_secured", True)
        self.assertFalse(engine.check_conditions(self.quests["暗潮·江湖棋局"]["requires"], p.world_state, p.completed_quests, p))
        p.set_flag("world:trade_network:warehouse_reviewed", True)
        self.assertTrue(engine.check_conditions(self.quests["暗潮·江湖棋局"]["requires"], p.world_state, p.completed_quests, p))
        p.location = next(room_id for room_id, room in engine.ROOMS.items() if "捕头" in room.get("npcs", []))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handle_talk_and_ask(p, ["捕头", "暗潮"])
        rendered = output.getvalue()
        self.assertIn("关键中间人", rendered)
        self.assertIn("联络暗记", rendered)
        for token in ("quest:", "world:", "trade_network:", ".py", "Traceback"):
            self.assertNotIn(token, rendered)

    def test_main_arc_has_three_mutually_exclusive_routes_and_keeps_mastermind_hidden(self):
        q = self.quests["暗潮·江湖棋局"]
        branches = q["stages"][0]["branch_choices"]
        self.assertEqual({b["id"] for b in branches}, {"public_route", "covert_route", "dual_route"})
        self.assertEqual({b["next_stage"] for b in branches}, {1})
        self.assertIn("world:trade_network:mastermind_unrevealed", q["on_complete"]["set_flags"])
        self.assertIn("world:trade_network:intermediary_identified", q["on_complete"]["set_flags"])
        self.assertIn("world:trade_network:contact_channel_identified", q["on_complete"]["set_flags"])
        self.assertNotIn("time_limit", q)
        self.assertNotIn("fail_if", q)

    def test_each_route_can_be_selected_saved_and_completed(self):
        route_data = {
            "public_route": ("world:trade_network:route_official", "失约证人"),
            "covert_route": ("world:trade_network:route_blackmarket", "黑市旧账"),
            "dual_route": ("world:trade_network:route_dual", "商队夜行"),
        }
        for route, (flag, side_quest) in route_data.items():
            with self.subTest(route=route):
                p = self._player_ready_for_arc("路线测试侠客")
                output = io.StringIO()
                p.location = next(room_id for room_id, room in engine.ROOMS.items() if "捕头" in room.get("npcs", []))
                with contextlib.redirect_stdout(output):
                    handle_quest(p, "jiequ", ["暗潮·江湖棋局"])
                with contextlib.redirect_stdout(output):
                    p.update_quest_progress("捕头", "talk")
                ok, msg = p.choose_quest_branch("暗潮·江湖棋局", route)
                self.assertTrue(ok, msg)
                self.assertTrue(p.get_flag(flag))
                self.assertTrue(engine.check_conditions(self.quests[side_quest]["requires"], p.world_state, p.completed_quests, p))
                # V12 round-trip keeps the route flag and in-progress quest without a schema bump.
                with tempfile.TemporaryDirectory() as tmp:
                    path = str(Path(tmp) / "route_save.json")
                    with contextlib.redirect_stdout(io.StringIO()):
                        p.save_to_file(path)
                        loaded = Player.load_from_file(path)
                self.assertEqual(engine.SAVE_VERSION, 12)
                self.assertTrue(loaded.get_flag(flag))
                self.assertIn("暗潮·江湖棋局", loaded.active_quests)
                # Complete all remaining stages through the same quest-progress API used by gameplay.
                for stage in self.quests["暗潮·江湖棋局"]["stages"][1:]:
                    with contextlib.redirect_stdout(io.StringIO()):
                        loaded.update_quest_progress(stage["target_name"], stage["target_type"])
                loaded.location = "guiyun_guard_camp"
                with patch.object(loaded, "get_npcs_in_room", return_value=["捕头"]), patch.object(loaded, "save_to_file"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        handle_quest(loaded, "jiaofu", ["暗潮·江湖棋局"])
                self.assertIn("暗潮·江湖棋局", loaded.completed_quests)
                self.assertTrue(loaded.get_flag("world:trade_network:intermediary_identified"))
                self.assertTrue(loaded.get_flag("world:trade_network:contact_channel_identified"))
                self.assertTrue(loaded.get_flag("world:trade_network:mastermind_unrevealed"))
                # Branch choice is one-shot; another choice cannot overwrite the selected route.
                ok2, _ = loaded.choose_quest_branch("暗潮·江湖棋局", "dual_route")
                self.assertFalse(ok2)

    def test_all_six_side_quests_can_be_completed_and_rewarded(self):
        side_names = ["商队夜行", "失约证人", "残缺货单", "黑市旧账", "仓外伏击", "失踪信使"]
        for name in side_names:
            with self.subTest(quest=name):
                p = Player("支线验收侠客", "散人")
                p.set_flag("quest:jianghu_chessboard:started", True)
                for flag in ("world:trade_network:route_official", "world:trade_network:route_blackmarket", "world:trade_network:route_dual"):
                    p.set_flag(flag, True)
                publisher = self.quests[name].get("npc")
                p.location = next(room_id for room_id, room in engine.ROOMS.items() if publisher in room.get("npcs", []))
                with contextlib.redirect_stdout(io.StringIO()):
                    handle_quest(p, "jiequ", [name])
                self.assertIn(name, p.active_quests)
                for stage in self.quests[name]["stages"]:
                    for _ in range(stage.get("required_cnt", 1)):
                        with contextlib.redirect_stdout(io.StringIO()):
                            p.update_quest_progress(stage["target_name"], stage["target_type"])
                turn_in = self.quests[name].get("turn_in_npc")
                p.location = next(room_id for room_id, room in engine.ROOMS.items() if turn_in in room.get("npcs", []))
                with patch.object(p, "save_to_file"):
                    with contextlib.redirect_stdout(io.StringIO()):
                        handle_quest(p, "jiaofu", [name])
                self.assertIn(name, p.completed_quests)
                self.assertTrue(p.get_flag(f"quest_completed:{name}"))

    def test_side_quest_routes_are_gated_and_failures_are_recoverable(self):
        public_only = Player("路线门槛测试侠客", "散人")
        public_only.set_flag("quest:jianghu_chessboard:started", True)
        public_only.set_flag("world:trade_network:route_official", True)
        self.assertTrue(engine.check_conditions(self.quests["失约证人"]["requires"], public_only.world_state, public_only.completed_quests, public_only))
        self.assertFalse(engine.check_conditions(self.quests["黑市旧账"]["requires"], public_only.world_state, public_only.completed_quests, public_only))
        # The main investigation is deliberately untimed and can be abandoned/reaccepted after correcting conditions.
        self.assertNotIn("time_limit", self.quests["暗潮·江湖棋局"])
        self.assertTrue(self.quests["暗潮·江湖棋局"].get("retryable", True))

    def test_escort_failure_changes_world_state_but_can_be_recovered(self):
        p = Player("商队补救测试侠客", "散人")
        p.set_flag("quest:jianghu_chessboard:started", True)
        p.set_flag("world:trade_network:route_official", True)
        p.set_var("merchant_reputation", 5)
        p.location = next(room_id for room_id, room in engine.ROOMS.items() if "万商会会长" in room.get("npcs", []))
        with contextlib.redirect_stdout(io.StringIO()):
            handle_quest(p, "jiequ", ["商队夜行"])
        p.set_var("quest_clock", 10)
        with contextlib.redirect_stdout(io.StringIO()):
            failed = p.check_quest_failures()
        self.assertIn(("商队夜行", "time_limit"), failed)
        self.assertTrue(p.get_flag("world:trade_network:night_caravan_failed"))
        self.assertEqual(p.get_var("merchant_reputation"), 3)
        # The retry remains available; a successful retry clears the temporary failure state.
        p.location = next(room_id for room_id, room in engine.ROOMS.items() if "万商会会长" in room.get("npcs", []))
        with contextlib.redirect_stdout(io.StringIO()):
            handle_quest(p, "jiequ", ["商队夜行"])
        for stage in self.quests["商队夜行"]["stages"]:
            for _ in range(stage.get("required_cnt", 1)):
                with contextlib.redirect_stdout(io.StringIO()):
                    p.update_quest_progress(stage["target_name"], stage["target_type"])
        turn_in = self.quests["商队夜行"]["turn_in_npc"]
        p.location = next(room_id for room_id, room in engine.ROOMS.items() if turn_in in room.get("npcs", []))
        with patch.object(p, "save_to_file"), contextlib.redirect_stdout(io.StringIO()):
            handle_quest(p, "jiaofu", ["商队夜行"])
        self.assertIn("商队夜行", p.completed_quests)
        self.assertFalse(p.get_flag("world:trade_network:night_caravan_failed"))
        self.assertTrue(p.get_flag("world:trade_network:night_caravan_safe"))

    def test_events_are_one_shot_and_only_reveal_intermediary_channel(self):
        event_ids = ["trade_network_public_witness_protected", "trade_network_blackmarket_channel", "trade_network_joint_audit", "trade_network_intermediary_exposed"]
        for event_id in event_ids:
            event = self.events[event_id]
            self.assertTrue(event.get("once"))
            self.assertEqual(event.get("region"), "guiyun_city")
            self.assertIn("text", event)
        story_text = " ".join(self.events[e]["text"] for e in event_ids)
        self.assertIn("幕后主谋", story_text)
        self.assertIn("关键中间人", story_text)
        self.assertIn("联络", story_text)

    def test_new_world_events_execute_once_and_persist_inside_v12_world_state(self):
        cases = {
            "trade_network_public_witness_protected": ["quest:jianghu_chessboard:resolved", "world:trade_network:route_official", "world:trade_network:witness_statement_secured"],
            "trade_network_blackmarket_channel": ["quest:jianghu_chessboard:resolved", "world:trade_network:route_blackmarket", "world:trade_network:blackmarket_ledger_secured"],
            "trade_network_joint_audit": ["quest:jianghu_chessboard:resolved", "world:trade_network:route_dual", "world:trade_network:intermediary_identified", "world:trade_network:contact_channel_identified"],
            "trade_network_intermediary_exposed": ["quest:jianghu_chessboard:resolved", "world:trade_network:intermediary_identified", "world:trade_network:contact_channel_identified"],
        }
        for event_id, flags in cases.items():
            with self.subTest(event=event_id):
                p = Player("事件联动测试侠客", "散人")
                p.location = "guiyun_guard_camp"
                for flag in flags:
                    p.set_flag(flag, True)
                self.assertTrue(p.can_trigger_world_event(event_id))
                ok, message, info = p.trigger_world_event(event_id)
                self.assertTrue(ok, message)
                self.assertIsInstance(info, dict)
                self.assertFalse(p.can_trigger_world_event(event_id))
                count = p.get_world_event_state(event_id).get("count", 0)
                ok2, _, _ = p.trigger_world_event(event_id)
                self.assertFalse(ok2)
                self.assertEqual(p.get_world_event_state(event_id).get("count", 0), count)

    def test_v12_legacy_save_without_new_story_flags_loads_safely(self):
        p = Player("旧档兼容侠客", "散人")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "legacy_v12.json")
            with contextlib.redirect_stdout(io.StringIO()):
                p.save_to_file(path)
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            raw.pop("world_state", None)
            raw["version"] = 12
            Path(path).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                loaded = Player.load_from_file(path)
        self.assertEqual(engine.SAVE_VERSION, 12)
        self.assertFalse(loaded.get_flag("world:trade_network:intermediary_identified"))
        self.assertIsInstance(loaded.world_state, dict)

    def test_player_facing_story_text_contains_no_internal_ids_or_paths(self):
        visible = [self.quests["暗潮·江湖棋局"]["desc"]]
        visible.extend(stage["desc"] for stage in self.quests["暗潮·江湖棋局"]["stages"])
        visible.extend(event["text"] for event in self.events.values() if event.get("title") in {"证人安置妥当", "暗号联络渠道查明", "官商联合复核", "关键中间人浮出水面"})
        joined = "\n".join(visible)
        for token in ("quest:", "world:", "trade_network:", ".py", "Traceback", "/mnt/"):
            self.assertNotIn(token, joined)


if __name__ == "__main__":
    unittest.main()
