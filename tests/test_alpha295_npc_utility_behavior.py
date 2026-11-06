# -*- coding: utf-8 -*-
"""Alpha295：NPC 效用行为层与 V12 存档兼容。"""

import json
import os
import tempfile

import engine
import npc_utility
from player import Player


def _context(**overrides):
    base = {
        "name": "测试村民",
        "clock": 1,  # 07:00
        "location": "village_south_street",
        "home": "old_qiu_residence",
        "state": "normal",
        "schedule_room": "village_south_street",
        "schedule_state": "busy",
        "schedule_reason": "清早挑水",
        "work_room": "village_south_street",
        "work_hours_ok": True,
        "meal_room": "village_square",
        "meal_allowed": False,
        "social_room": "village_square",
        "route": [],
        "security": 70,
        "allowed_actions": list(npc_utility.DEFAULT_ALLOWED_ACTIONS),
        "needs": {"fatigue": 20, "social": 35, "hunger": 30},
    }
    base.update(overrides)
    return base


def test_work_wins_during_work_hours_and_rest_wins_at_night():
    work = npc_utility.choose_action(_context(clock=1))
    assert work["action"] == "work"
    assert work["target"] == "village_south_street"

    rest = npc_utility.choose_action(_context(
        clock=15,  # 21:00
        work_hours_ok=False,
        schedule_room="old_qiu_residence",
        schedule_state="normal",
        schedule_reason="收工回家",
        needs={"fatigue": 60, "social": 20, "hunger": 30},
    ))
    assert rest["action"] == "rest"
    assert rest["reason"].startswith("夜深了")


def test_meal_breaks_the_work_routine_at_meal_time():
    decision = npc_utility.choose_action(_context(
        clock=6,  # 12:00
        meal_allowed=True,
        needs={"fatigue": 30, "social": 40, "hunger": 60},
    ))
    assert decision["action"] == "meal"
    assert decision["target"] == "village_square"


def test_anchor_keeps_quest_npc_on_routine_and_blocks_wandering():
    decision = npc_utility.choose_action(_context(
        clock=6,
        anchor=True,
        schedule_room="village_square",
        route=["village_square", "village_gate"],
        social_room="village_square",
    ))
    actions = {item["action"] for item in decision["candidates"]}
    assert decision["action"] == "routine"
    assert "patrol" not in actions
    assert "socialize" not in actions
    assert "seek_player" not in actions


def test_blocked_state_stays_in_place_without_candidates():
    decision = npc_utility.choose_action(_context(state="fear"))
    assert decision["action"] == "rest"
    assert decision["target"] == "village_south_street"
    assert decision["score"] == 0.0


def test_needs_stay_bounded_and_noise_is_stable():
    tired = npc_utility.advance_needs({"fatigue": 99, "social": 99, "hunger": 99}, 24, "work")
    assert all(0 <= tired[key] <= 100 for key in tired)
    rested = npc_utility.advance_needs({"fatigue": 0, "social": 0, "hunger": 0}, 24, "rest")
    assert all(0 <= rested[key] <= 100 for key in rested)
    assert npc_utility.stable_noise("挑水老邱", "work", 3) == npc_utility.stable_noise("挑水老邱", "work", 3)


def test_utility_runner_moves_one_real_exit_toward_work():
    player = Player("效用移动", "散人")
    player.set_var("quest_clock", 1)  # 07:00，学徒应在打铁铺
    player.set_npc_location("铁匠学徒小石", "village_south_street", source="test")
    profile = player._npc_utility_profile("铁匠学徒小石")
    decision = player._npc_utility_decide("铁匠学徒小石", profile, 1)
    assert decision["action"] == "work"
    result = player._execute_npc_utility_action("铁匠学徒小石", decision)
    assert result["action"] == "work"
    assert player.get_npc_location("铁匠学徒小石", refresh=False) != "village_south_street"


def test_quest_givers_are_treated_as_anchors():
    player = Player("锚点检查", "散人")
    anchors = player._npc_quest_anchor_names()
    assert "村长" in anchors
    assert "挑水老邱" not in anchors


def test_utility_profiles_are_opt_in_and_reference_real_rooms():
    enabled = []
    for name, info in engine.NPCS.items():
        profile = info.get("utility_profile")
        if not isinstance(profile, dict):
            continue
        enabled.append(name)
        assert profile.get("enabled") is True, name
        for key in ("work_room", "meal_room", "social_room"):
            if key in profile:
                assert profile[key] in engine.ROOMS, (name, key)
        if "work_hours" in profile:
            hours = profile["work_hours"]
            assert isinstance(hours, list) and len(hours) == 2, name
            assert all(isinstance(value, int) and 0 <= value <= 23 for value in hours), name
    assert len(enabled) >= 4


def test_utility_state_is_saved_under_v12_world_state():
    player = Player("效用存档", "散人")
    player.set_var("quest_clock", 2)
    player.process_npc_autonomy()
    assert "npc_utility" in player.world_state["variables"]
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        player.save_to_file(path)
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        assert raw["version"] == 12
        assert "npc_utility" in raw["world_state"]["variables"]
        assert "npc_utility" not in raw
    finally:
        os.remove(path)
