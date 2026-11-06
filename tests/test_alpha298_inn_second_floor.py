# -*- coding: utf-8 -*-
"""Alpha298：悦来客栈二楼、上下楼指令、安全室内区与女性 NPC 回归验收。"""
import builtins
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import engine
import main
from actions import handle_explore, handle_trading, look
from player import Player

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UPPER_ROOMS = ("inn_upper_tian1", "inn_upper_tian2", "inn_upper_tian3")
MEDICINES = ("金创药", "回内丹", "清心散", "凝露丸")


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def run_commands(player, commands):
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(output):
        main.main()
    return output.getvalue()


def test_second_floor_data_is_complete_and_safe():
    rooms, regions, npcs = load("rooms"), load("world_regions"), load("npcs")
    inn = rooms["inn"]
    assert inn["exits"]["上"] == "inn_upper_hall"
    assert "大堂西侧有木梯通往二楼客房（输入“上”或“上楼”）" in inn["desc"]
    assert inn["floor"] == 1

    upper_ids = [rid for rid, room in rooms.items() if room.get("zone") == "inn_upper"]
    assert set(upper_ids) == {"inn_upper_hall", *UPPER_ROOMS, "inn_upper_di1"}
    for room_id in upper_ids:
        room = rooms[room_id]
        assert room["floor"] == 2
        assert room["safe"] is True
        assert room["danger"] == "safe"
        assert not room.get("enemies")
    assert len({rooms[rid]["name"] for rid in upper_ids}) == len(upper_ids)

    hall = rooms["inn_upper_hall"]
    assert hall["exits"] == {
        "下": "inn",
        "东": "inn_upper_tian1",
        "西": "inn_upper_tian2",
        "南": "inn_upper_tian3",
        "北": "inn_upper_di1",
    }
    assert hall["exit_notes"]["北"] == "（门锁着）"
    locked = rooms["inn_upper_di1"]
    assert locked["access"]["locked"] is True
    assert "门锁着" in locked["access"]["blocked_text"]
    assert not locked.get("npcs")

    region = regions["inn_upper"]
    assert region["name"] == "悦来客栈二楼"
    assert region["indoor"] is True
    assert region["danger"] == "safe"
    assert region["exploration_events"] == []
    assert region["conflict_events"] == []
    assert region["faction_exposure"] == []

    assert npcs["苏挽晴"]["home_room"] == "inn_upper_tian2"
    assert npcs["苏挽晴"]["type"] == "trader"
    assert set(npcs["苏挽晴"]["shop"]) == set(MEDICINES)


def test_command_aliases_do_not_override_other_commands():
    assert main.parse_command("上")[0] == "u"
    assert main.parse_command("上楼")[0] == "u"
    assert main.parse_command("up")[0] == "u"
    assert main.parse_command("下")[0] == "d"
    assert main.parse_command("下楼")[0] == "d"
    assert main.parse_command("down")[0] == "d"
    # 历史浏览仍保留独立别名，避免上下楼吞掉原功能。
    assert main.parse_command("上条")[0] == "history_up"
    assert main.parse_command("下条")[0] == "history_down"
    assert main.parse_command("上一条")[0] == "history_up"
    assert main.parse_command("下一条")[0] == "history_down"
    assert "u" not in main.CMD_MAP and "d" not in main.CMD_MAP


def test_up_and_down_aliases_move_between_floors_and_cost_one_tick_each():
    for up_cmd, down_cmd in (("上", "下"), ("上楼", "下楼"), ("up", "down"), ("u", "d")):
        player = Player(f"上下楼{up_cmd}", "散人")
        player.location = "inn"
        player.set_var("quest_clock", 7)
        run_commands(player, [up_cmd, down_cmd, "退出"])
        assert player.location == "inn", (up_cmd, down_cmd)
        assert player.get_quest_clock() == 9, (up_cmd, down_cmd)


def test_guest_room_down_uses_dedicated_stair_hint_and_costs_no_time():
    for room_id in UPPER_ROOMS:
        player = Player(f"客房下楼{room_id}", "散人")
        player.location = room_id
        player.set_var("quest_clock", 7)
        output = run_commands(player, ["下", "退出"])
        assert player.location == room_id
        assert player.get_quest_clock() == 7
        assert "这间客房没有楼梯，请先回到走廊再下楼。" in output
        assert "这里没有通往楼下的路" not in output


def test_locked_room_denies_entry_without_advancing_time():
    player = Player("锁门", "散人")
    player.location = "inn_upper_hall"
    player.set_var("quest_clock", 7)
    output = run_commands(player, ["北", "退出"])
    assert player.location == "inn_upper_hall"
    assert player.get_quest_clock() == 7
    assert "地字一号房的门锁着" in output


def test_look_and_map_show_indoor_status_and_floor_exits():
    player = Player("地图验收", "散人")
    player.location = "inn_upper_hall"
    output, _ = capture(look, player)
    assert "【区域局势】 安全" in output
    assert "危险度" not in output
    assert "下 → 一楼大堂" in output
    assert "北（门锁着） → 地字一号房" in output

    map_text = engine.MAP_ENGINE.render("inn_upper_hall", player)
    assert "悦来客栈二楼" in map_text
    assert "inn_upper" not in map_text
    assert "下 -> 一楼大堂" in map_text

    first_floor_map = engine.MAP_ENGINE.render("inn", player)
    assert "上 -> 客栈二楼走廊" in first_floor_map


def test_upper_floor_is_safe_from_exploration_and_encounters():
    player = Player("二楼安稳", "散人")
    player.location = "inn_upper_tian1"
    output, _ = capture(handle_explore, player)
    assert "过于安稳" in output
    assert player.get_region_exploration_event("inn_upper", []) == []
    ecology = player.get_region_ecology("inn_upper")
    assert ecology["danger"] == "safe" and ecology["level"] == "calm"
    for _ in range(200):
        assert main.select_random_encounter(player, engine.ROOMS["inn_upper_tian1"], "inn_upper", 100, 40) is None


def test_su_wanqing_sells_all_configured_medicines_with_valid_prices():
    player = Player("苏挽晴货架", "散人")
    player.location = "inn_upper_tian2"
    player.gold = 500
    output, _ = capture(handle_trading, player, "shop", ["苏挽晴"])
    for name in MEDICINES:
        info = engine.ITEMS[name]
        assert info["type"] == "consumable"
        assert isinstance(info["price"], int) and info["price"] > 0
        assert name in output
    # 交易成功会写存档；测试必须隔离，避免覆盖本地正式进度。
    with patch.object(Player, "save_to_file", lambda *args, **kwargs: True):
        capture(handle_trading, player, "buy", ["苏挽晴", "金创药", "1"])
    assert player.inventory.count("金创药") == 1
    assert player.gold == 500 - 51


def test_old_save_npcs_appear_via_home_room_and_room_roster():
    player = Player("旧档二楼", "散人")
    player.world_state.setdefault("variables", {}).pop("npc_locations", None)
    expected = {
        "inn_upper_hall": {"柳三娘", "小翠"},
        "inn_upper_tian1": {"沈青霜"},
        "inn_upper_tian2": {"苏挽晴"},
        "inn_upper_tian3": {"阿蘅"},
    }
    for room_id, names in expected.items():
        assert names <= set(player.get_npcs_in_room(room_id))
        for name in names:
            assert player.get_npc_location(name, refresh=False) == room_id


def test_cross_floor_npc_messages_do_not_mix_with_room_directions():
    player = Player("播报验收", "散人")
    player.location = "inn"
    player._queue_npc_movement_message("小翠", "inn", "inn_upper_hall", source="autonomy")
    assert player.drain_npc_movement_messages() == ["小翠上楼去了。"]

    player.location = "inn_upper_hall"
    player._queue_npc_movement_message("小翠", "inn", "inn_upper_hall", source="autonomy")
    assert player.drain_npc_movement_messages() == ["小翠从楼下走来。"]

    player.location = "inn"
    player._queue_npc_movement_message("小翠", "inn_upper_hall", "inn", source="autonomy")
    assert player.drain_npc_movement_messages() == ["小翠从楼上下来。"]

    player.location = "inn_upper_hall"
    player._queue_npc_movement_message("沈青霜", "inn_upper_hall", "inn_upper_tian1", source="autonomy")
    assert player.drain_npc_movement_messages() == ["沈青霜往东边（天字一号房）去了。"]
