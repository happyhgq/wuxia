"""Alpha266：NPC 场景移动方向、出口一致性与局部动态提示。"""

import engine
from player import Player
import main


def _player_at(room):
    player = Player("方向验收", "散人")
    player.location = room
    return player


def test_npc_departure_reports_real_exit_direction_and_name():
    player = _player_at("village_gate")
    player.get_npc_location("守卫")
    assert player.set_npc_location("守卫", "village_south_street", "schedule")
    messages = player.drain_npc_movement_messages()
    assert messages == ["守卫往北边（青石长街）去了。"]


def test_npc_arrival_reports_direction_from_actual_entry_exit():
    player = _player_at("village_south_street")
    player.get_npc_location("守卫")
    assert player.set_npc_location("守卫", "village_south_street", "schedule")
    messages = player.drain_npc_movement_messages()
    assert messages == ["守卫从南边（青石村口）走来。"]


def test_non_exit_teleport_is_not_falsely_reported_as_directional_walk():
    player = _player_at("village_gate")
    player.get_npc_location("守卫")
    # 把守卫放回玩家所在场景，确保传送提示只由本次跨房间改位产生。
    player.set_npc_location("守卫", "village_gate", "test")
    player.drain_npc_movement_messages()
    assert player.set_npc_location("守卫", "blacksmith", "teleport:story")
    messages = player.drain_npc_movement_messages()
    assert messages == ["守卫被传送离开了。"]
    assert "往" not in messages[0]


def test_multiple_npcs_moving_emit_individual_direction_messages():
    player = _player_at("village_gate")
    player.set_npc_location("守卫", "village_gate", "test")
    player.set_npc_location("村长", "village_gate", "test")
    player.drain_npc_movement_messages()
    player.set_npc_location("守卫", "village_south_street", "schedule")
    player.set_npc_location("村长", "official_road", "schedule")
    messages = player.drain_npc_movement_messages()
    assert len(messages) == 2
    assert any("守卫往北边" in row for row in messages)
    assert any("村长往南边" in row for row in messages)


def test_pathfinding_never_uses_a_nonexistent_exit():
    player = _player_at("village_gate")
    assert player._npc_room_path("village_gate", "blacksmith") == ("北", "village_south_street")
    assert player._npc_room_path("village_gate", "not_a_room") is None
    # 每条返回路径的首步必须确实存在于当前房间 exits。
    direction, target = player._npc_room_path("village_gate", "blacksmith")
    assert engine.ROOMS["village_gate"].get("exits", {}).get(direction) == target


def test_schedule_long_distance_movement_advances_only_one_exit_per_tick(monkeypatch):
    player = _player_at("village_gate")
    info = engine.NPCS["守卫"]
    old_schedule = info.get("daily_schedule")
    info["daily_schedule"] = [{"start": 6, "end": 7, "location": "blacksmith", "state": "normal"}]
    try:
        # 自定义日程 6–7 点对应世界 tick 0（卯时初）。
        player.set_var("quest_clock", 0)
        player.refresh_npc_schedules()
        assert player.get_npc_location("守卫", refresh=False) == "village_south_street"
        assert player.drain_npc_movement_messages() == ["守卫往北边（青石长街）去了。"]
    finally:
        if old_schedule is None:
            info.pop("daily_schedule", None)
        else:
            info["daily_schedule"] = old_schedule


def test_movement_announcement_is_dynamic_only_and_does_not_redraw_scene(monkeypatch, capsys):
    player = _player_at("village_gate")
    player.get_npc_location("守卫")
    player.set_npc_location("守卫", "village_south_street", "schedule")
    calls = []
    monkeypatch.setattr(main, "look", lambda *args, **kwargs: calls.append("look"))
    main.announce_pending_npc_movement(player)
    output = capsys.readouterr().out
    assert "往北边（青石长街）去了" in output
    assert "【动态】" not in output
    assert calls == []
    assert player.drain_npc_movement_messages() == []


def test_return_home_and_vanish_have_distinct_non_directional_wording():
    player = _player_at("village_gate")
    player.set_npc_location("守卫", "village_gate", "test")
    player.set_npc_location("守卫", "blacksmith", "return:indoor")
    assert player.drain_npc_movement_messages() == ["守卫转身回了打铁铺。"]
    player.set_npc_location("守卫", "village_gate", "test")
    player.drain_npc_movement_messages()
    player.set_npc_location("守卫", "blacksmith", "vanish:story")
    assert player.drain_npc_movement_messages() == ["守卫悄然消失在人群中。"]


def test_schedule_refresh_does_not_move_npc_multiple_exits_in_same_tick():
    player = _player_at("village_gate")
    info = engine.NPCS["守卫"]
    old_schedule = info.get("daily_schedule")
    info["daily_schedule"] = [{"start": 6, "end": 7, "location": "blacksmith", "state": "normal"}]
    try:
        # 自定义日程 6–7 点对应世界 tick 0（卯时初）。
        player.set_var("quest_clock", 0)
        player.refresh_npc_schedules()
        first = player.get_npc_location("守卫", refresh=False)
        player.refresh_npc_schedules()
        second = player.get_npc_location("守卫", refresh=False)
        assert first == second == "village_south_street"
    finally:
        if old_schedule is None:
            info.pop("daily_schedule", None)
        else:
            info["daily_schedule"] = old_schedule


def test_unreachable_schedule_destination_does_not_teleport_npc():
    player = _player_at("village_gate")
    info = engine.NPCS["守卫"]
    old_schedule = info.get("daily_schedule")
    engine.ROOMS["alpha266_isolated_room"] = {"name": "孤立房间", "exits": {}, "npcs": []}
    info["daily_schedule"] = [{"start": 6, "end": 7, "location": "alpha266_isolated_room", "state": "normal"}]
    try:
        # 自定义日程 6–7 点对应世界 tick 0（卯时初）。
        player.set_var("quest_clock", 0)
        player.refresh_npc_schedules()
        assert player.get_npc_location("守卫", refresh=False) == "village_gate"
        assert player.drain_npc_movement_messages() == []
    finally:
        engine.ROOMS.pop("alpha266_isolated_room", None)
        if old_schedule is None:
            info.pop("daily_schedule", None)
        else:
            info["daily_schedule"] = old_schedule


def test_adjacent_event_move_uses_direction_but_distant_event_move_does_not_fake_it():
    player = _player_at("village_gate")
    player.set_npc_location("守卫", "village_gate", "test")
    player.set_npc_location("守卫", "village_south_street", "event:patrol")
    assert player.drain_npc_movement_messages() == ["守卫往北边（青石长街）去了。"]
    player.location = "village_south_street"
    player.set_npc_location("守卫", "blacksmith", "event:teleport")
    assert player.drain_npc_movement_messages() == ["守卫离开了这里。"]
