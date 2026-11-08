"""P4.2：首日引导天气、普通行动低频车马与有窗室内的窗外视角。"""

import contextlib
import io
import json
import zlib

import pytest

import engine
import main
import weather
import world_ambience
from player import Player


def _player(room="village_gate", tick=0, name="P42验收"):
    player = Player(name, "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def _capture(player, include_traffic=False):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        messages = world_ambience.announce(player, include_traffic=include_traffic)
    return messages, buffer.getvalue()


def _collect(player, include_traffic=False):
    return world_ambience.collect_messages(player, include_traffic=include_traffic)


# ==================== 首日引导天气 ====================

def test_new_character_guide_changes_weather_within_ten_actions():
    player = main.create_new_player("首日天气")
    assert player.location == "village_gate"
    _capture(player)
    assert weather._state(player, 0)["until_tick"] == 8
    seen = []
    for tick in range(1, 11):
        player.set_var("quest_clock", tick)
        messages, _output = _capture(player)
        seen.extend(messages)
    assert weather.current_kind(player, 8) == "cloudy"
    assert "云层压了下来，天色转阴。" in seen


def test_new_character_guide_reaches_rain_within_twenty_actions():
    player = main.create_new_player("首日小雨")
    _capture(player)
    seen = []
    for tick in range(1, 21):
        player.set_var("quest_clock", tick)
        messages, _output = _capture(player)
        seen.extend(messages)
    assert weather.current_kind(player, 16) == "rain"
    assert "细雨落了下来，四下很快有了水声。" in seen


def test_guide_realigns_weather_changes_to_dawn_after_the_first_day():
    player = main.create_new_player("首日对齐")
    _capture(player)
    kind, changed = weather.advance(player, 20)
    assert kind == "rain" and changed is True
    state = weather._state(player, 20)
    assert state["until_tick"] in (48, 72, 96)
    assert state["until_tick"] % 24 == 0
    # 从下一个黎明（24）起按正常 1~3 天持续，而非从角色创建时刻起算。
    assert state["until_tick"] - 24 in (24, 48, 72)
    assert "guide" not in state


def test_jump_past_guide_steps_reports_only_arrival_weather():
    player = main.create_new_player("首日跳刻")
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 20
    player.set_var("quest_clock", 20)
    messages, _output = _capture(player)
    assert weather.current_kind(player, 20) == "rain"
    assert messages == [world_ambience._WEATHER_PHASE_MESSAGES["rain"]["late_night"]]
    assert "云层压了下来，天色转阴。" not in messages


def test_old_save_without_guide_keeps_clear_until_first_dawn():
    player = _player(tick=0, name="旧档验收")
    _capture(player)
    state = weather._state(player, 0)
    assert state["kind"] == "clear"
    assert state["until_tick"] == 24
    assert "guide" not in state
    assert weather.advance(player, 23) == ("clear", False)


def test_guide_state_survives_v12_save_roundtrip(tmp_path):
    player = main.create_new_player("首日存档")
    _capture(player)
    path = tmp_path / "p42_guide_save.json"
    assert player.save_to_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 12
    assert raw["world_state"]["variables"]["weather_world"]["guide"]
    loaded = Player.load_from_file(str(path))
    assert weather._state(loaded, 0)["until_tick"] == 8
    loaded.set_var("quest_clock", 8)
    _capture(loaded)
    assert weather.current_kind(loaded, 8) == "cloudy"


def test_guide_continues_after_reload_before_first_change(tmp_path):
    player = main.create_new_player("首日续跑")
    _capture(player)
    player.set_var("quest_clock", 5)
    path = tmp_path / "p42_resume_save.json"
    assert player.save_to_file(str(path))
    loaded = Player.load_from_file(str(path))
    assert loaded.get_quest_clock() == 5
    _capture(loaded)
    assert weather.current_kind(loaded, 5) == "clear"
    loaded.set_var("quest_clock", 8)
    messages, _output = _capture(loaded)
    assert weather.current_kind(loaded, 8) == "cloudy"
    assert "云层压了下来，天色转阴。" in messages


def test_cloudy_dawn_reports_transition_instead_of_plain_phase_text():
    player = _player(tick=0, name="动态验收")
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 24
    player.set_var("quest_clock", 24)
    messages, _output = _capture(player)
    assert weather.current_kind(player, 24) == "cloudy"
    assert "云层压了下来，天色转阴。" in messages


@pytest.mark.parametrize("kind", ["rain", "storm", "snow", "fog"])
def test_weather_with_dedicated_phase_text_is_not_duplicated(kind):
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 6
    weather._state(player, 6)["kind"] = kind
    weather._state(player, 6)["until_tick"] = 100
    player.set_var("quest_clock", 6)
    messages, _output = _capture(player)
    assert messages == [world_ambience._WEATHER_PHASE_MESSAGES[kind]["noon"]]
    assert world_ambience._WEATHER_TRANSITIONS[kind][0] not in messages


# ==================== 普通行动低频车马 ====================

def _expected_due_ticks(room, start, end):
    return [
        tick
        for tick in range(start, end)
        if zlib.crc32(f"passersby:{tick}:{room}".encode("utf-8")) % world_ambience.NORMAL_TRAFFIC_PERIOD == 0
    ]


def test_natural_traffic_cadence_is_deterministic_and_low_frequency():
    player = _player(tick=0)
    due = [tick for tick in range(1, 61) if world_ambience._normal_traffic_due(player, tick)]
    assert due == _expected_due_ticks("village_gate", 1, 61)
    assert 2 <= len(due) <= 8


def test_room_without_cardinal_exits_never_triggers_natural_traffic():
    player = _player(room="blacksmith_inner", tick=0)
    assert not any(world_ambience._normal_traffic_due(player, tick) for tick in range(1, 121))


def test_natural_traffic_respects_the_gap_after_a_wait_traffic():
    player = _player(tick=0)
    due = _expected_due_ticks("village_gate", 1, 60)[0]
    state = world_ambience._state(player)
    state["last_traffic_tick"] = due
    assert world_ambience._normal_traffic_due(player, due) is False
    state["last_traffic_tick"] = due - world_ambience.NORMAL_TRAFFIC_GAP
    assert world_ambience._normal_traffic_due(player, due) is True


def test_normal_action_announces_natural_traffic_without_wait():
    player = _player(tick=0)
    _capture(player)
    due = _expected_due_ticks("village_gate", 1, 60)[0]
    world_ambience._state(player)["last_scene_tick"] = due
    world_ambience._state(player)["phase"] = world_ambience.phase_for_tick(due)
    player.set_var("quest_clock", due)
    collected = _collect(player)
    assert collected["traffic"]
    assert collected["traffic"] in collected["messages"]
    assert "边（" in collected["traffic"]


def test_wait_still_always_pushes_traffic():
    player = _player(tick=10)
    _capture(player)
    collected = _collect(player, include_traffic=True)
    assert collected["traffic"]
    assert collected["traffic"] in collected["messages"]


# ==================== 有窗室内的窗外视角 ====================

def test_window_rooms_use_window_wording():
    for room_id in ("inn_upper_hall", "inn_upper_tian1", "inn_upper_tian2", "inn_upper_tian3", "inn_upper_di1"):
        player = _player(room=room_id)
        assert engine.ROOMS[room_id].get("window_view") is True
        assert world_ambience._room_is_indoor(player)
        for kind in world_ambience._WINDOW_WEATHER_TRANSITIONS:
            message = world_ambience._weather_message(player, kind)
            assert message == world_ambience._WINDOW_WEATHER_TRANSITIONS[kind]
            assert message.startswith("窗外")


def test_windowless_indoor_keeps_eave_wording():
    for room_id in ("blacksmith_inner", "general_shop", "inn"):
        player = _player(room=room_id)
        message = world_ambience._weather_message(player, "rain")
        assert message == "檐外传来细密的雨声。"
        assert "窗外" not in message


def test_window_room_weather_transition_uses_window_view():
    player = _player(room="inn_upper_hall", tick=9)
    _capture(player)
    world_ambience._state(player)["weather_seen"] = ["clear", 24]
    world_ambience._state(player)["last_scene_tick"] = 10
    weather._state(player, 9)["kind"] = "rain"
    weather._state(player, 9)["until_tick"] = 100
    player.set_var("quest_clock", 10)
    messages, _output = _capture(player)
    assert messages == [
        world_ambience.PHASE_MESSAGES["dusk"],
        "窗外落着细雨，檐角滴着水。",
    ]


def test_outdoor_and_eave_wording_remain_distinct_from_window_wording():
    assert world_ambience._weather_message(_player(tick=9), "rain") == "细雨落了下来，四下很快有了水声。"
    assert world_ambience._weather_message(_player(room="general_shop"), "rain") == "檐外传来细密的雨声。"
    assert world_ambience._weather_message(_player(room="inn_upper_hall"), "rain") == "窗外落着细雨，檐角滴着水。"
