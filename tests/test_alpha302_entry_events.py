# -*- coding: utf-8 -*-
"""Alpha302：入口事件静态条件表、一次性持久化与移动挂钩。"""
import contextlib
import inspect
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import engine
import entry_events
import travel_system
from actions import look
from player import Player


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def player_at(room_id, tick):
    player = Player("事件测试侠客", "散人")
    player.location = room_id
    player.set_var("quest_clock", tick)
    return player


class EntryEventDataTests(unittest.TestCase):
    def test_events_data_targets_existing_rooms_and_valid_hours(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "events.json")
        with open(path, encoding="utf-8") as handle:
            events = json.load(handle)
        self.assertTrue(events)
        for event_id, event in events.items():
            self.assertTrue(event.get("title"), event_id)
            self.assertTrue(event.get("text"), event_id)
            self.assertTrue(event.get("rooms") or event.get("zone"), event_id)
            for room_id in event.get("rooms", []) or []:
                self.assertIn(room_id, engine.ROOMS, event_id)
            hours = event.get("hours")
            if hours is not None:
                self.assertEqual(len(hours), 2, event_id)
                self.assertNotEqual(hours[0], hours[1], event_id)
                self.assertTrue(all(0 <= hour <= 23 for hour in hours), event_id)


class EntryEventEligibilityTests(unittest.TestCase):
    def test_room_and_hours_filter_entries(self):
        player = player_at("village_gate", 16)  # 22:00
        ids = [event_id for event_id, _event in entry_events.eligible_events(player, "village_gate")]
        self.assertEqual(ids, ["village_gate_night_lantern"])
        player.set_var("quest_clock", 6)  # 12:00
        self.assertEqual(entry_events.eligible_events(player, "village_gate"), [])
        self.assertEqual(entry_events.eligible_events(player, "village_square"), [])

    def test_requires_zone_and_priority_are_respected(self):
        table = {
            "low_priority": {
                "text": "低优先级事件。", "rooms": ["village_gate"], "once": True, "priority": 1,
            },
            "high_priority": {
                "text": "高优先级事件。", "zone": "main", "once": True, "priority": 9,
            },
            "blocked": {
                "text": "缺旗标不应触发。", "rooms": ["village_gate"], "once": True,
                "requires": {"flags": ["entry:test:missing"]},
            },
        }
        player = player_at("village_gate", 0)
        with mock.patch.object(engine, "EVENTS", table):
            ids = [event_id for event_id, _event in entry_events.eligible_events(player, "village_gate")]
        self.assertIn("high_priority", ids)
        self.assertIn("low_priority", ids)
        self.assertNotIn("blocked", ids)
        self.assertLess(ids.index("high_priority"), ids.index("low_priority"))

    def test_cooldown_allows_only_after_ticks_elapse(self):
        table = {
            "repeatable": {
                "text": "可重复事件。", "rooms": ["village_gate"],
                "once": False, "cooldown": 3, "priority": 1,
            }
        }
        player = player_at("village_gate", 16)
        with mock.patch.object(engine, "EVENTS", table), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(entry_events.trigger_entry_events(player, "village_gate"), "repeatable")
            player.set_var("quest_clock", 18)
            self.assertEqual(entry_events.eligible_events(player, "village_gate"), [])
            player.set_var("quest_clock", 19)
            self.assertEqual(entry_events.trigger_entry_events(player, "village_gate"), "repeatable")
        record = player.world_state["variables"]["entry_events"]["repeatable"]
        self.assertEqual(record, {"count": 2, "last_clock": 19})


class EntryEventWriteTests(unittest.TestCase):
    def test_trigger_prints_once_and_records_event(self):
        player = player_at("village_gate", 16)
        output, event_id = capture(entry_events.trigger_entry_events, player, "village_gate")
        self.assertEqual(event_id, "village_gate_night_lantern")
        self.assertIn("【夜过村口】", output)
        self.assertIn("夜风卷过村口", output)
        record = player.world_state["variables"]["entry_events"]["village_gate_night_lantern"]
        self.assertEqual(record, {"count": 1, "last_clock": 16})
        again, second_id = capture(entry_events.trigger_entry_events, player, "village_gate")
        self.assertIsNone(second_id)
        self.assertNotIn("【夜过村口】", again)

    def test_look_is_read_only_and_does_not_trigger_events(self):
        player = player_at("village_gate", 16)
        output, _ = capture(look, player)
        self.assertNotIn("【夜过村口】", output)
        self.assertNotIn("entry_events", player.world_state.get("variables", {}))

    def test_effects_are_applied_and_persisted_in_v12_save(self):
        table = {
            "effect_event": {
                "title": "效果事件", "text": "效果事件正文。", "rooms": ["village_gate"],
                "once": True, "priority": 1,
                "effects": {
                    "set_flags": {"entry:test:seen": True},
                    "increment_variables": {"entry_test_count": 2},
                },
            }
        }
        player = player_at("village_gate", 16)
        with mock.patch.object(engine, "EVENTS", table), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(entry_events.trigger_entry_events(player, "village_gate"), "effect_event")
        self.assertTrue(player.get_flag("entry:test:seen"))
        self.assertEqual(player.get_var("entry_test_count"), 2)

        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        path = handle.name
        handle.close()
        try:
            player.save_to_file(path)
            with open(path, encoding="utf-8") as saved:
                raw = json.load(saved)
            self.assertEqual(raw["version"], 12)
            self.assertNotIn("entry_events", raw)
            self.assertIn("entry_events", raw["world_state"]["variables"])
            loaded = Player.load_from_file(path)
            self.assertEqual(
                loaded.world_state["variables"]["entry_events"]["effect_event"],
                {"count": 1, "last_clock": 16},
            )
            self.assertTrue(loaded.get_flag("entry:test:seen"))
        finally:
            os.remove(path)


class EntryEventHookTests(unittest.TestCase):
    def test_travel_success_triggers_entry_events(self):
        player = player_at("village_gate", 0)
        calls = []
        with mock.patch.object(travel_system, "available_destinations",
                               return_value=([("village_square", "中心广场", 1)], "")), \
                mock.patch("actions.look", lambda _player: None), \
                mock.patch.object(travel_system, "trigger_entry_events",
                                  lambda _player, room_id: calls.append(room_id)), \
                contextlib.redirect_stdout(io.StringIO()):
            ok = travel_system.handle_travel(player, ["中心广场"])
        self.assertTrue(ok)
        self.assertEqual(player.location, "village_square")
        self.assertEqual(calls, ["village_square"])

    def test_main_movement_hook_runs_after_look_before_encounter(self):
        import main
        source = inspect.getsource(main.main)
        hook = source.index("trigger_entry_events(player, player.location)")
        self.assertGreater(hook, source.index("look(player)", source.index("player.mark_visited(player.location)")))
        self.assertLess(hook, source.index("select_random_encounter(player, next_room"))


if __name__ == "__main__":
    unittest.main()
