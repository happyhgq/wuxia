"""Alpha306：NPC 移动播报节流与在岗不擅自离岗回归。"""

from player import Player


def _guard_from_street_to_gate(clock=8):
    """14:00 守卫按日程在村口值守，玩家也站在村口。"""
    player = Player("移动节流", "散人")
    player.location = "village_gate"
    player.set_var("quest_clock", clock)
    player.set_npc_location("守卫", "village_south_street", source="test")
    player.drain_npc_movement_messages()
    return player


def test_schedule_move_is_not_reverted_in_same_tick():
    player = _guard_from_street_to_gate()
    player.process_npc_autonomy()
    assert player.get_npc_location("守卫", refresh=False) == "village_gate"

    # 同一世界时刻再次刷新，不应把刚按日程到达的守卫再拉走。
    player.refresh_npc_schedules()
    assert player.get_npc_location("守卫", refresh=False) == "village_gate"
    assert player.drain_npc_movement_messages() == ["守卫从北边（青石长街）走来。"]


def test_on_duty_guard_stays_at_post_across_ticks():
    player = Player("在岗守卫", "散人")
    player.location = "village_gate"
    player.set_npc_location("守卫", "village_gate", source="schedule")
    player.drain_npc_movement_messages()
    for clock in (8, 9, 10, 11, 12):
        player.set_var("quest_clock", clock)
        player.process_npc_autonomy()
        assert player.get_npc_location("守卫", refresh=False) == "village_gate"
    assert player.drain_npc_movement_messages() == []


def test_one_movement_message_per_npc_per_tick():
    player = _guard_from_street_to_gate()
    player.set_npc_location("守卫", "village_square", source="autonomy:patrol")
    player.set_npc_location("守卫", "village_gate", source="schedule")
    messages = player.drain_npc_movement_messages()
    assert len(messages) == 1
    assert "守卫" in messages[0]


def test_on_post_patrol_records_action_without_leaving():
    player = Player("在岗巡查", "散人")
    player.location = "village_gate"
    player.set_var("quest_clock", 8)
    player.refresh_npc_schedules()
    action = player._execute_npc_autonomous_action("守卫", "patrol")
    assert action["action"] == "patrol"
    assert action["from"] == "village_gate"
    assert action["to"] == "village_gate"
