"""Alpha306：世界主动动态消息的排序、节流、抑制与存读档回归。"""

import builtins
import contextlib
import io
import json
from unittest.mock import patch

import main
import world_ambience
from player import Player


def _player(room="village_gate", tick=9):
    player = Player("动态验收", "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def _capture(player, blocked=False):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        messages = world_ambience.announce(player, blocked=blocked)
    return messages, buffer.getvalue()


def _move_all_out(player):
    for name in ("守卫", "村长", "铁匠", "药铺老板", "柳三娘"):
        player.set_npc_location(name, "village_gate", "test")
    player.drain_npc_movement_messages()
    for name in ("守卫", "村长", "铁匠", "药铺老板", "柳三娘"):
        player.set_npc_location(name, "village_south_street", "schedule")


def test_old_save_initializes_phase_silently():
    player = _player(tick=7)
    messages, output = _capture(player)
    assert messages == [] and output == ""
    assert world_ambience._state(player)["phase"] == "noon"


def test_dusk_message_is_natural_and_never_repeated():
    player = _player(tick=9)
    _capture(player)
    player.set_var("quest_clock", 10)
    messages, output = _capture(player)
    assert messages == ["天色渐暗，暮色四合。"]
    assert "【" not in output
    assert output.startswith("\n") and output.endswith("\n")
    assert _capture(player)[0] == []


def test_npc_movement_precedes_time_and_scene_messages():
    player = _player(tick=9)
    _capture(player)
    player.set_npc_location("守卫", "village_gate", "test")
    player.drain_npc_movement_messages()
    player.set_var("quest_clock", 10)
    player.set_npc_location("守卫", "village_south_street", "schedule")
    messages, output = _capture(player)
    assert messages == ["守卫往北边（青石长街）去了。", "天色渐暗，暮色四合。"]
    assert "【动态】" not in output


def test_same_npc_moving_twice_pushes_only_the_latest_message():
    player = _player(tick=9)
    player.set_npc_location("守卫", "village_gate", "test")
    player.drain_npc_movement_messages()
    player.set_npc_location("守卫", "village_south_street", "schedule")
    player.set_npc_location("守卫", "village_gate", "schedule")
    messages, _output = _capture(player)
    assert len([row for row in messages if row.startswith("守卫")]) == 1
    assert "走来" in messages[0]


def test_five_message_cap_merges_same_route_and_time_still_follows():
    player = _player(tick=9)
    _capture(player)
    _move_all_out(player)
    player.set_var("quest_clock", 10)
    messages, _output = _capture(player)
    assert messages == [
        "守卫、村长、铁匠、药铺老板、柳三娘往北边（青石长街）去了。",
        "天色渐暗，暮色四合。",
    ]
    assert player.drain_npc_movement_messages() == []
    follow_up, _output = _capture(player)
    assert follow_up == []


def test_blocked_flush_keeps_movement_and_phase_until_panel_closes():
    player = _player(tick=9)
    _capture(player)
    player.set_npc_location("守卫", "village_gate", "test")
    player.drain_npc_movement_messages()
    player.set_var("quest_clock", 10)
    player.set_npc_location("守卫", "village_south_street", "schedule")
    messages, output = _capture(player, blocked=True)
    assert messages == [] and output == ""
    assert list(player._pending_npc_movement_messages.values()) == ["守卫往北边（青石长街）去了。"]
    messages, _output = _capture(player)
    assert messages == ["守卫往北边（青石长街）去了。", "天色渐暗，暮色四合。"]


def test_scene_sound_waits_for_its_interval():
    player = _player(tick=16)
    _capture(player)
    state = world_ambience._state(player)
    state["phase"] = world_ambience.phase_for_tick(22)
    player.set_var("quest_clock", 22)
    messages, _output = _capture(player)
    assert len(messages) == 1
    assert messages[0] in world_ambience._SCENE_MESSAGES["main"]
    assert _capture(player)[0] == []


def test_ambient_markers_roundtrip_inside_v12_variables(tmp_path):
    player = _player(tick=9)
    _capture(player)
    player.set_var("quest_clock", 10)
    _capture(player)
    path = tmp_path / "ambient_save.json"
    assert player.save_to_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 12
    assert "ambient_world" in raw["world_state"]["variables"]
    loaded = Player.load_from_file(str(path))
    loaded.set_var("quest_clock", 10)
    assert _capture(loaded)[0] == []


def test_phase_order_is_complete_for_single_tick_actions():
    player = _player(tick=0)
    _capture(player)
    seen = []
    for tick in range(1, 18):
        player.set_var("quest_clock", tick)
        messages, _output = _capture(player)
        seen.extend(row for row in messages if row in world_ambience.PHASE_MESSAGES.values())
    assert seen == [
        world_ambience.PHASE_MESSAGES["morning"],
        world_ambience.PHASE_MESSAGES["noon"],
        world_ambience.PHASE_MESSAGES["dusk"],
        world_ambience.PHASE_MESSAGES["night"],
        world_ambience.PHASE_MESSAGES["late_night"],
    ]


def test_batched_advance_reports_only_arrival_phase():
    player = _player(tick=0)
    _capture(player)
    world_ambience._state(player)["last_scene_tick"] = 13  # 排除场景声响干扰
    player.set_var("quest_clock", 14)  # 一次过夜/连推跨过清晨、正午、黄昏
    messages, _output = _capture(player)
    assert messages == [world_ambience.PHASE_MESSAGES["night"]]
    assert world_ambience._state(player)["phase"] == "night"


def test_blank_line_only_when_messages_exist_and_not_between_messages():
    player = _player(tick=0)
    _capture(player)
    player.set_var("quest_clock", 6)
    messages, output = _capture(player)
    assert len(messages) == 2
    assert output.startswith("\n") and not output.startswith("\n\n")
    assert "\n\n" not in output
    assert output.count("\n") == len(messages) + 1


def test_collect_messages_merges_same_route_and_exposes_order():
    player = _player(tick=9)
    _capture(player)
    _move_all_out(player)
    player.set_var("quest_clock", 10)
    collected = world_ambience.collect_messages(player)
    assert world_ambience.MAX_MESSAGES == 5
    assert len(collected["movement_pool"]) == 1
    assert collected["movement_pool"][0].startswith("守卫、村长、铁匠、药铺老板、柳三娘")
    assert collected["movement_selected"] == collected["movement_pool"][:5]
    assert collected["deferred"] == []
    assert len(collected["messages"]) == 2


def test_help_explains_that_time_advances_with_actions():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main.show_help()
        main.show_help("新手")
    assert "世界时间随你的行动推进" in buffer.getvalue()


def test_message_cap_is_five():
    assert world_ambience.MAX_MESSAGES == 5


def test_same_route_movements_merge_into_one_sentence_with_all_names():
    events = [
        {"npc": "守卫", "kind": "in", "direction": "南", "place": "青石村口", "text": "守卫从南边（青石村口）走来。"},
        {"npc": "村长", "kind": "in", "direction": "南", "place": "青石村口", "text": "村长从南边（青石村口）走来。"},
        {"npc": "铁匠", "kind": "in", "direction": "南", "place": "青石村口", "text": "铁匠从南边（青石村口）走来。"},
    ]
    assert world_ambience._merge_movement_events(events) == [
        "守卫、村长、铁匠从南边（青石村口）走来。"
    ]


def test_different_directions_do_not_merge():
    events = [
        {"npc": "守卫", "kind": "out", "direction": "北", "place": "青石长街", "text": "守卫往北边（青石长街）去了。"},
        {"npc": "村长", "kind": "out", "direction": "南", "place": "黄土官道", "text": "村长往南边（黄土官道）去了。"},
    ]
    assert world_ambience._merge_movement_events(events) == [
        "守卫往北边（青石长街）去了。",
        "村长往南边（黄土官道）去了。",
    ]


def test_different_movement_kinds_do_not_merge_even_on_the_same_route():
    events = [
        {"npc": "守卫", "kind": "out", "direction": "北", "place": "青石长街", "text": "守卫往北边（青石长街）去了。"},
        {"npc": "村长", "kind": "in", "direction": "北", "place": "青石长街", "text": "村长从北边（青石长街）走来。"},
        {"npc": "铁匠", "kind": "up_out", "text": "铁匠上楼去了。"},
        {"npc": "柳三娘", "kind": "up_out", "text": "柳三娘上楼去了。"},
        {"npc": "药铺老板", "kind": "special", "text": "药铺老板离开了这里。"},
        {"npc": "店小二", "kind": "special", "text": "店小二离开了这里。"},
    ]
    assert world_ambience._merge_movement_events(events) == [
        "守卫往北边（青石长街）去了。",
        "村长从北边（青石长街）走来。",
        "铁匠、柳三娘上楼去了。",
        "药铺老板离开了这里。",
        "店小二离开了这里。",
    ]


def test_collect_messages_merges_same_route_npc_movements():
    player = _player(tick=9)
    _capture(player)
    for name in ("守卫", "村长", "铁匠"):
        player.set_npc_location(name, "village_gate", "test")
    player.drain_npc_movement_messages()
    for name in ("守卫", "村长", "铁匠"):
        player.set_npc_location(name, "village_south_street", "schedule")
    collected = world_ambience.collect_messages(player)
    assert collected["movement_pool"] == ["守卫、村长、铁匠往北边（青石长街）去了。"]


def test_look_lists_all_present_npcs_when_movement_messages_exceed_the_cap():
    import actions
    import actor_display
    import engine
    import npc_utility

    player = _player(tick=9)
    _capture(player)
    names = ("守卫", "村长", "铁匠", "药铺老板", "柳三娘", "店小二")
    for name in names:
        player.set_npc_location(name, "blacksmith", "test", announce=False)
    player.drain_npc_movement_messages()
    for name in names:
        player.set_npc_location(name, "village_gate", "event:story_arrival")
    collected = world_ambience.collect_messages(player)
    assert len(collected["movement_events"]) == 6
    assert len(collected["messages"]) == world_ambience.MAX_MESSAGES
    # 最后一条移动消息被上限丢弃，但人物位置已经落到当前场景。
    assert "店小二" not in "".join(collected["messages"])
    assert all(player.get_npc_location(name, refresh=False) == player.location for name in names)
    presence = set(player.get_npcs_in_room())
    assert set(names) <= presence
    # 按作息本就在村口的守卫，其纯函数状态与 look 列表一致。
    guard_state = npc_utility.get_npc_current_state(engine.NPCS["守卫"], player.get_quest_clock())
    assert guard_state["room_id"] == player.location

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        actions.look(player)
    people = output.getvalue().split("【人物】", 1)[1]
    for name in names:
        label = actor_display.format_room_label(name, engine.NPCS[name])
        assert label in people


def test_main_loop_prints_ambient_after_input_before_command_output():
    player = _player(tick=9)
    _capture(player)  # 先让旧存档静默记录当前天色，确保本轮跨入黄昏。
    output = io.StringIO()
    commands = ["交谈 守卫", "退出"]
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "handle_talk_and_ask", return_value=None), \
         contextlib.redirect_stdout(output):
        main.main()
    rendered = output.getvalue()
    assert rendered.count("天色渐暗，暮色四合。") == 1
    assert rendered.index("天色渐暗，暮色四合。") < rendered.index("少侠保重")
