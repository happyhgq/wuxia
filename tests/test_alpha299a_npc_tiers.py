# -*- coding: utf-8 -*-
"""Alpha299a：NPC 分层数据、状态纯函数与校验器。"""

import contextlib
import copy
import io

import engine
from data_validator import main as validate_data
from npc_utility import get_npc_current_state


def _state(name, hour):
    # 世界 tick 0 为卯时 06:00，1 tick = 1 小时。
    tick = (hour - 6) % 24
    return get_npc_current_state(engine.NPCS[name], tick)


def test_tiers_are_configured_as_designed():
    for name in ("铁匠", "药铺老板", "村长"):
        assert engine.NPCS[name]["schedule_tier"] == "T1"
    for name in ("守卫", "木匠老许", "货郎周四"):
        assert engine.NPCS[name]["schedule_tier"] == "T2"
    guide = engine.NPCS["青石村接引人"]
    assert guide["schedule_tier"] == "T3"
    assert guide["always_available"] is True
    assert "daily_schedule" not in guide


def test_t1_rest_rooms_are_real_safe_rooms_and_list_the_owner():
    expected = {
        "铁匠": "blacksmith_inner",
        "药铺老板": "apothecary_backyard",
        "村长": "village_chief_room",
    }
    for name, room_id in expected.items():
        assert engine.NPCS[name]["home_room"] == room_id
        room = engine.ROOMS[room_id]
        assert room.get("safe") is True
        assert room.get("safe_zone") is True
        assert name in room.get("npcs", [])


def test_t1_npcs_stay_on_scene_24h_and_never_use_generic_rest_text():
    for name in ("铁匠", "药铺老板", "村长"):
        for hour in range(24):
            state = _state(name, hour)
            assert state["offstage"] is False
            assert state["room_id"] in engine.ROOMS
            assert state["status"]
            assert "在住处休息" not in state["status"]


def test_t1_night_locations_are_their_own_inner_rooms():
    assert _state("铁匠", 22)["room_id"] == "blacksmith_inner"
    assert _state("药铺老板", 21)["room_id"] == "apothecary_backyard"
    assert _state("村长", 22)["room_id"] == "village_chief_room"
    assert _state("铁匠", 9)["room_id"] == "blacksmith"
    assert _state("药铺老板", 15)["room_id"] == "medicine_shop"


def test_t2_npcs_leave_the_scene_by_schedule():
    guard = _state("守卫", 23)
    assert guard["offstage"] is True
    assert guard["room_id"] is None
    assert _state("守卫", 19)["room_id"] == "village_gate"
    assert _state("木匠老许", 20)["offstage"] is True
    assert _state("货郎周四", 22)["offstage"] is True


def test_t3_guide_is_available_at_every_hour():
    for hour in range(24):
        state = _state("青石村接引人", hour)
        assert state["always_available"] is True
        assert state["offstage"] is False
        assert state["room_id"] == "village_square"
        assert state["status"]


def test_absence_notes_cover_t2_scenes_at_offstage_hours():
    checks = [
        ("village_gate", "守卫", 23),
        ("village_square", "木匠老许", 20),
        ("guiyun_general_market", "货郎周四", 22),
    ]
    for room_id, name, hour in checks:
        assert _state(name, hour)["offstage"] is True
        note = engine.ROOMS[room_id]["absence_notes"][name]
        assert note.strip()


def test_state_function_is_pure_and_does_not_touch_schedule():
    for name in ("铁匠", "守卫", "青石村接引人", "挑水老邱"):
        info = engine.NPCS[name]
        before = copy.deepcopy(info)
        get_npc_current_state(info, 16)
        assert info == before


def test_state_function_falls_back_to_home_room_and_scene_status():
    npc = {
        "home_room": "village_square",
        "scene_status": "正在树下打盹",
    }
    state = get_npc_current_state(npc, 12)
    assert state["room_id"] == "village_square"
    assert state["status"] == "正在树下打盹"
    assert state["offstage"] is False

    empty = get_npc_current_state({}, 12)
    assert empty["room_id"] is None
    assert empty["status"] == ""


def test_custom_exits_have_reverse_exits_and_new_rooms_are_map_hidden():
    pairs = [
        ("medicine_shop", "后", "apothecary_backyard", "前"),
        ("blacksmith", "内", "blacksmith_inner", "外"),
        ("village_head_house", "内", "village_chief_room", "外"),
    ]
    for outer, direction, inner, reverse in pairs:
        assert engine.ROOMS[outer]["exits"][direction] == inner
        assert engine.ROOMS[inner]["exits"][reverse] == outer
        assert engine.ROOMS[inner].get("map_hidden") is True


def test_night_hours_and_closed_counter_are_configured():
    assert engine.ROOMS["medicine_shop"]["night_hours"] == [20, 6]
    assert engine.ROOMS["blacksmith"]["night_hours"] == [19, 6]
    assert engine.ROOMS["blacksmith_inner"].get("trade_closed") is True
    assert "night_desc" in engine.ROOMS["apothecary_backyard"]


def test_validator_passes_with_alpha299a_data():
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        result = validate_data()
    assert result == 0, output.getvalue()
    assert "DATA VALIDATION: PASS" in output.getvalue()
