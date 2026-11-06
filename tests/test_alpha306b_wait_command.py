"""Alpha306b：停留指令推进一个时辰，并推送车马过客。"""

import builtins
import contextlib
import io
import json
from unittest.mock import patch

import engine
import main
import world_ambience
from player import Player


def _player(room="village_gate", tick=9):
    player = Player("停留验收", "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def _capture(callback, *args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = callback(*args)
    return result, buffer.getvalue()


def _move_all_out(player):
    for name in ("守卫", "村长", "铁匠", "药铺老板", "柳三娘"):
        player.set_npc_location(name, "village_gate", "test")
    player.drain_npc_movement_messages()
    for name in ("守卫", "村长", "铁匠", "药铺老板", "柳三娘"):
        player.set_npc_location(name, "village_south_street", "schedule")


def _move_five_directions_out(player):
    names = ("守卫", "村长", "铁匠", "药铺老板", "柳三娘")
    for name in names:
        player.set_npc_location(name, "inn_upper_hall", "test")
    player.drain_npc_movement_messages()
    destinations = (
        ("守卫", "inn"),
        ("村长", "inn_upper_tian1"),
        ("铁匠", "inn_upper_tian2"),
        ("药铺老板", "inn_upper_tian3"),
        ("柳三娘", "inn_upper_di1"),
    )
    for name, room in destinations:
        player.set_npc_location(name, room, "schedule")


def test_wait_has_one_command_name_and_one_short_alias():
    assert main.parse_command("停留")[0] == "wait"
    assert main.parse_command("停")[0] == "wait"
    assert main.command_will_be_handled("wait", engine.ROOMS["village_gate"])


def test_traffic_direction_and_place_come_from_real_exits():
    player = _player("village_gate", tick=10)
    text = world_ambience._traffic_message(player, 10)
    assert text
    assert "北边（青石长街）" in text or "南边（黄土官道）" in text


def test_room_without_cardinal_exits_has_no_traffic():
    player = _player("blacksmith_inner", tick=10)
    assert world_ambience._traffic_message(player, 10) is None


def test_consecutive_waits_do_not_repeat_the_same_traffic_line():
    probe = _player("village_gate", tick=11)
    natural = world_ambience._traffic_message(probe, 11)
    player = _player("village_gate", tick=11)
    world_ambience._state(player)["last_traffic"] = natural
    assert world_ambience._traffic_message(player, 11) != natural


def test_consecutive_waits_do_not_reuse_the_same_template():
    probe = _player("inn_upper_hall", tick=11)
    natural = world_ambience._traffic_message(probe, 11)
    template = world_ambience._state(probe)["last_traffic_template"]
    player = _player("inn_upper_hall", tick=11)
    state = world_ambience._state(player)
    state["last_traffic"] = natural
    state["last_traffic_template"] = template
    assert world_ambience._traffic_message(player, 11) != natural
    assert state["last_traffic_template"] != template


def test_upper_floor_traffic_uses_indoor_wording():
    player = _player("inn_upper_hall", tick=10)
    text = world_ambience._traffic_message(player, 10)
    assert text
    assert "天字" in text or "地字" in text
    assert not any(word in text for word in ("骑着", "镖车", "牛车", "驴车", "骏马"))


def test_inn_lobby_traffic_uses_indoor_wording():
    player = _player("inn", tick=10)
    text = world_ambience._traffic_message(player, 10)
    assert text
    assert "青石长街" in text
    assert not any(word in text for word in ("骑着", "镖车", "牛车", "驴车", "骏马"))


def test_indoor_rooms_use_indoor_scene_pool():
    for room in ("inn_upper_hall", "inn", "blacksmith_inner"):
        pool = world_ambience._scene_pool(room)
        assert pool is not world_ambience._SCENE_MESSAGES["main"]
        assert all("犬吠" not in line and "马蹄" not in line for line in pool)


def test_wait_feedback_does_not_repeat_consecutively():
    player = _player("blacksmith_inner", tick=10)
    first = world_ambience.wait_feedback(player)
    player.set_var("quest_clock", 11)
    second = world_ambience.wait_feedback(player)
    assert first == world_ambience._WAIT_FEEDBACK[0]
    assert second != first
    assert second in world_ambience._WAIT_FEEDBACK


def test_wait_advances_exactly_one_tick_and_announces_traffic():
    player = _player(tick=9)
    world_ambience.announce(player)  # 静默记录当前天色与场景节流基准。
    before = player.get_quest_clock()
    messages = main._advance_world_after_action(player, include_traffic=True)
    assert player.get_quest_clock() == before + 1
    assert any("（" in row and "边" in row for row in messages)


def test_traffic_is_deferred_when_five_distinct_movements_fill_the_cap():
    player = _player("inn_upper_hall", tick=9)
    world_ambience.announce(player)
    _move_five_directions_out(player)
    player.set_var("quest_clock", 10)
    collected = world_ambience.collect_messages(player, include_traffic=True)
    assert len(collected["movement_pool"]) == 5
    assert len(collected["messages"]) == 5
    assert collected["traffic"] is None
    assert "traffic" in collected["deferred"]


def test_main_loop_wait_prints_fallback_when_nothing_ambient_happens():
    player = _player("blacksmith_inner", tick=9)
    world_ambience.announce(player)
    state = world_ambience._state(player)
    state["phase"] = world_ambience.phase_for_tick(10)
    state["last_scene_tick"] = 10
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=["停留", "退出"]), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         contextlib.redirect_stdout(output):
        main.main()
    assert "你停下脚步，留意四周的动静。" in output.getvalue()


def test_main_loop_wait_advances_once_and_prints_traffic():
    player = _player(tick=9)
    world_ambience.announce(player)
    before = player.get_quest_clock()
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=["停留", "退出"]), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         contextlib.redirect_stdout(output):
        main.main()
    assert player.get_quest_clock() == before + 1
    rendered = output.getvalue()
    assert "北边（青石长街）" in rendered or "南边（黄土官道）" in rendered


def test_wait_does_not_add_top_level_save_fields(tmp_path):
    player = _player(tick=9)
    world_ambience.announce(player)
    main._advance_world_after_action(player, include_traffic=True)
    path = tmp_path / "wait_save.json"
    assert player.save_to_file(str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 12
    assert "ambient_world" in raw["world_state"]["variables"]


def test_help_lists_wait_and_short_alias():
    _result, menu = _capture(main.show_help)
    _result, category = _capture(main.show_help, "查看与移动")
    _result, detail = _capture(main.show_help, "停留")
    assert "查看与移动" in menu
    assert "停留" in category
    assert "停留" in detail and "停" in detail


def test_indoor_rooms_use_indoor_traffic_pool():
    for room in (
        "blacksmith",
        "guiyun_general_shop",
        "guiyun_yunlai_inn",
        "guiyun_yamen_hall",
        "huashan_master_hall",
        "bandit_camp",
        "sunken_channel",
        "mistwood_hut",
        "duanhun_keep",
    ):
        assert world_ambience._traffic_pool(engine.ROOMS[room]) is world_ambience._INDOOR_TRAFFIC_TEMPLATES
        text = world_ambience._traffic_message(_player(room, tick=10), 10)
        assert text
        assert not any(word in text for word in ("骑着", "镖车", "牛车", "驴车", "骏马", "货郎", "捕快"))


def test_all_indoor_flagged_rooms_use_indoor_scene_and_traffic_wording():
    for room_id, room in engine.ROOMS.items():
        if room.get("indoor") is not True and room.get("safe_zone") is not True:
            continue
        assert world_ambience._scene_pool(room_id) is world_ambience._INDOOR_SCENE
        assert world_ambience._traffic_pool(room) is world_ambience._INDOOR_TRAFFIC_TEMPLATES
    for line in world_ambience._INDOOR_SCENE:
        assert not any(word in line for word in ("巷口", "犬吠", "街面", "车马", "马蹄", "山风", "松林", "钟响"))


def test_open_air_streets_and_courtyards_keep_street_wording():
    for room in (
        "village_square",
        "guiyun_south_gate_inner",
        "guiyun_martial_yard",
        "village_head_house",
        "guiyun_medicine_inner",
        "guiyun_dart_yard",
    ):
        assert world_ambience._traffic_pool(engine.ROOMS[room]) is world_ambience._TRAFFIC_TEMPLATES
        assert world_ambience._scene_pool(room) is not world_ambience._INDOOR_SCENE
