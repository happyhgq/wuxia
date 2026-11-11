# -*- coding: utf-8 -*-
"""P4.0 P1：确定性失败的只读预检不推进世界，成功路径仍计时。"""
import builtins
import contextlib
import io
from unittest.mock import patch

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


def _player_at(location, name="预检验收"):
    player = Player(name, "散人")
    player.location = location
    player.set_var("quest_clock", 7)
    return player


def test_mine_without_resource_node_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["采矿", "退出"])
    assert player.get_quest_clock() == 7


def test_chop_without_resource_node_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["伐木", "退出"])
    assert player.get_quest_clock() == 7


def test_search_without_forage_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["搜索", "退出"])
    assert player.get_quest_clock() == 7


def test_collect_before_discovery_costs_no_time():
    player = _player_at("wild_fields")
    assert player.get_flag("resource_discovered:wild_fields", False) is False
    _run_main_loop(player, ["采集", "退出"])
    assert player.get_quest_clock() == 7


def test_skill_learn_unknown_or_other_sect_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["武学 学习 罗汉拳", "退出"])
    assert player.get_quest_clock() == 7


def test_skill_forget_not_learned_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["武学 遗忘 罗汉拳", "退出"])
    assert player.get_quest_clock() == 7


def test_sect_join_wrong_place_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["门派 加入 少林", "退出"])
    assert player.get_quest_clock() == 7
    assert player.get_sect() == "散人"


def test_sect_join_below_level_gate_costs_no_time():
    player = _player_at("shaolin_guest_hall")
    player.set_flag("sect:shaolin:entry_interview", True)
    player.level = 2
    _run_main_loop(player, ["门派 加入 少林", "退出"])
    assert player.get_quest_clock() == 7
    assert player.get_sect() == "散人"


def test_sect_promote_without_sect_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["门派 晋升", "退出"])
    assert player.get_quest_clock() == 7


def test_sect_training_without_sect_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["门派 修习", "退出"])
    assert player.get_quest_clock() == 7


def test_unknown_event_trigger_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["事件 触发 不存在的江湖事件", "退出"])
    assert player.get_quest_clock() == 7


def test_security_unknown_action_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["治安 乱输", "退出"])
    assert player.get_quest_clock() == 7


def test_attribute_bad_input_costs_no_time():
    player = _player_at("village_square")
    _run_main_loop(player, ["属性 加点", "退出"])
    assert player.get_quest_clock() == 7

    player = _player_at("village_square")
    _run_main_loop(player, ["属性 力量 999", "退出"])
    assert player.get_quest_clock() == 7
    assert player.attributes["strength"] == 0


def test_successful_search_still_costs_one_tick():
    player = _player_at("wild_fields")
    _run_main_loop(player, ["搜索", "退出"])
    assert player.get_quest_clock() == 8
    assert player.get_flag("resource_discovered:wild_fields", False)


def test_successful_mine_still_costs_one_tick():
    player = _player_at("abandoned_iron_mine")
    _run_main_loop(player, ["采矿", "退出"])
    assert player.get_quest_clock() == 8
    assert player.inventory.count("铁矿石") > 0


def test_successful_attribute_allocation_still_costs_one_tick():
    player = _player_at("village_square")
    player.attribute_points = 3
    strength = player.attributes["strength"]
    _run_main_loop(player, ["属性 力量 1", "退出"])
    assert player.get_quest_clock() == 8
    assert player.attributes["strength"] == strength + 1


def test_exhausted_forage_still_uses_original_tick_order():
    """资源是否恢复依赖时间：耗尽后的采集失败仍按原流程计时。"""
    player = _player_at("wild_fields")
    player.set_flag("resource_discovered:wild_fields", True)
    economy = dict(player.economy_state or {})
    resources = dict(economy.get("resources") or {})
    resources["wild_fields"] = {"remaining": 0, "last_tick": player.get_quest_clock()}
    economy["resources"] = resources
    player.economy_state = economy

    _run_main_loop(player, ["采集", "退出"])

    assert player.get_quest_clock() == 8
