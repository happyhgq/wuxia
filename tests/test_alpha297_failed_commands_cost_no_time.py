# -*- coding: utf-8 -*-
"""Alpha297：失败或无效的指令不推进世界时钟，成功交互仍推进一个时刻。"""
import builtins
import contextlib
import io
from unittest.mock import patch

import engine
import main
from player import Player


def _run_main_loop(player, commands, prompt_input="y"):
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value=prompt_input), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(io.StringIO()):
        main.main()


def _player_at(location, name):
    player = Player(name, "散人")
    player.location = location
    player.set_var("quest_clock", 7)
    return player


def test_buy_without_gold_costs_no_time():
    player = _player_at("medicine_shop", "买不起")
    player.gold = 0
    _run_main_loop(player, ["买 金创药 1", "退出"])
    assert player.get_quest_clock() == 7
    assert player.gold == 0
    assert "金创药" not in player.inventory


def test_sell_missing_item_costs_no_time():
    player = _player_at("medicine_shop", "无货可卖")
    player.gold = 10
    _run_main_loop(player, ["卖 玄铁重剑 1", "退出"])
    assert player.get_quest_clock() == 7
    assert player.gold == 10


def test_travel_without_known_route_costs_no_time():
    player = _player_at("village_square", "无路可走")
    _run_main_loop(player, ["旅行 华山山门", "退出"])
    assert player.get_quest_clock() == 7
    assert player.location == "village_square"


def test_attack_missing_target_costs_no_time():
    player = _player_at("temple", "无人可打")
    _run_main_loop(player, ["攻击 山贼", "退出"])
    assert player.get_quest_clock() == 7


def test_forge_without_materials_costs_no_time():
    player = _player_at("blacksmith", "材料不足")
    player.gold = 0
    ore_before = player.inventory.count("铁矿石")
    _run_main_loop(player, ["锻造", "退出"], prompt_input="1")
    assert player.get_quest_clock() == 7
    assert player.inventory.count("铁矿石") == ore_before
    assert player.gold == 0


def test_forge_cancelled_menu_costs_no_time():
    player = _player_at("blacksmith", "取消锻造")
    player.gold = 100
    _run_main_loop(player, ["锻造", "退出"], prompt_input="0")
    assert player.get_quest_clock() == 7
    assert player.gold == 100


def test_equip_missing_item_costs_no_time():
    player = _player_at("village_square", "无剑可装")
    _run_main_loop(player, ["装备武器 玄铁重剑", "退出"])
    assert player.get_quest_clock() == 7
    assert player.equipment.get("weapon") == "木剑"


def test_use_missing_item_costs_no_time():
    player = _player_at("village_square", "无药可用")
    _run_main_loop(player, ["使用 九转还魂丹", "退出"])
    assert player.get_quest_clock() == 7


def test_inn_meal_without_gold_costs_no_time():
    player = _player_at("inn", "无钱吃饭")
    player.gold = 0
    _run_main_loop(player, ["吃饭", "退出"])
    assert player.get_quest_clock() == 7
    assert player.gold == 0


def test_missing_exit_direction_costs_no_time():
    player = _player_at("village_gate", "走错方向")
    assert "西" not in engine.ROOMS["village_gate"]["exits"]
    _run_main_loop(player, ["西", "退出"])
    assert player.get_quest_clock() == 7
    assert player.location == "village_gate"


def test_successful_buy_still_costs_one_tick():
    player = _player_at("medicine_shop", "正常交易")
    player.gold = 1000
    _run_main_loop(player, ["买 金创药 1", "退出"])
    assert player.get_quest_clock() == 8
    assert player.gold < 1000
    assert player.inventory.count("金创药") == 1


def test_successful_travel_still_costs_one_tick():
    player = _player_at("village_gate", "正常远行")
    for room_id in engine.ROOMS:
        player.set_flag(f"visited:{room_id}", True)
    _run_main_loop(player, ["旅行 归云城南门", "退出"])
    assert player.get_quest_clock() == 8
    assert player.location == "guiyun_south_gate"


def test_successful_inn_meal_still_costs_one_tick():
    player = _player_at("inn", "正常吃饭")
    player.gold = 10
    player.hp = 5
    _run_main_loop(player, ["吃饭", "退出"])
    assert player.get_quest_clock() == 8
    assert player.gold == 6
    assert player.hp == 23
