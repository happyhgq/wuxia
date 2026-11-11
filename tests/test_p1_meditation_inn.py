# -*- coding: utf-8 -*-
"""第一批：打坐按百分比恢复/耗蓝，失败不计时；古庙只驱散病邪类状态。"""
import builtins
import contextlib
import io
from unittest.mock import patch

import pytest

import engine
import main
from player import Player


@pytest.fixture(autouse=True)
def _clean_player_statuses():
    engine.p_statuses_global.clear()
    yield
    engine.p_statuses_global.clear()


def _run_main_loop(player, commands):
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, *args, **kwargs: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(output):
        main.main()
    return output.getvalue()


def _player_at(location):
    player = Player("打坐验收", "散人")
    player.location = location
    player.set_var("quest_clock", 7)
    return player


def test_meditation_restores_five_percent_and_costs_ten_percent_mp():
    player = _player_at("village_square")
    player.hp, player.mp = 80, 50

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "恢复了 5 点气血，消耗 5 点内力。" in output
    assert (player.hp, player.mp) == (85, 45)


def test_meditation_advances_exactly_one_world_tick():
    player = _player_at("village_square")
    player.hp, player.mp = 80, 50

    _run_main_loop(player, ["打坐", "退出"])

    assert player.get_quest_clock() == 8


def test_meditation_percentages_scale_with_attributes():
    player = _player_at("village_square")
    player.max_hp, player.hp = 200, 150
    player.max_mp, player.mp = 80, 80

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "恢复了 10 点气血，消耗 8 点内力。" in output
    assert (player.hp, player.mp) == (160, 72)


def test_meditation_does_not_refill_mp():
    player = _player_at("village_square")
    player.hp, player.mp = 80, 30

    _run_main_loop(player, ["打坐", "退出"])

    assert player.mp == 25


def test_meditation_without_enough_mp_rejects_and_costs_no_time():
    player = _player_at("village_square")
    player.hp, player.mp = 80, 4

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "内力不足，无法运功打坐。" in output
    assert (player.hp, player.mp) == (80, 4)
    assert player.get_quest_clock() == 7


def test_meditation_in_unsafe_room_rejects_and_costs_no_time():
    player = _player_at("stone_creek_bridge")
    player.hp, player.mp = 80, 50

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "此处不宜入定。" in output
    assert (player.hp, player.mp) == (80, 50)
    assert player.get_quest_clock() == 7


def test_meditation_in_combat_rejects():
    player = _player_at("village_square")
    player.hp, player.mp = 80, 50
    player._in_combat = True

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "此处不宜入定。" in output
    assert (player.hp, player.mp) == (80, 50)
    assert player.get_quest_clock() == 7


def test_temple_meditation_keeps_single_bonus_and_does_not_refill_mp():
    player = _player_at("temple")
    player.hp, player.mp = 80, 40

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "古庙石佛前盘膝打坐，气血恢复 5 点，消耗 5 点内力。" in output
    assert (player.hp, player.mp) == (85, 35)


def test_temple_meditation_purges_afflictions_but_keeps_wounds_and_buffs():
    player = _player_at("temple")
    player.hp, player.mp = 80, 50
    engine.add_status(engine.p_statuses_global, "stun", 2)
    engine.add_status(engine.p_statuses_global, "armor_break", 2, 5)
    engine.add_status(engine.p_statuses_global, "poison", 2, 3)
    engine.add_status(engine.p_statuses_global, "bleed", 2, 2)
    engine.add_status(engine.p_statuses_global, "shield", 2, 10)

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "一身病邪异状皆被驱散！" in output
    assert "stun" not in engine.p_statuses_global
    assert "armor_break" not in engine.p_statuses_global
    assert "poison" in engine.p_statuses_global
    assert "bleed" in engine.p_statuses_global
    assert "shield" in engine.p_statuses_global


def test_temple_meditation_does_not_claim_cleansing_without_afflictions():
    player = _player_at("temple")
    player.hp, player.mp = 80, 50
    engine.add_status(engine.p_statuses_global, "poison", 2, 3)
    engine.add_status(engine.p_statuses_global, "bleed", 2, 2)

    output = _run_main_loop(player, ["打坐", "退出"])

    assert "一身病邪异状皆被驱散！" not in output
    assert set(engine.p_statuses_global) == {"poison", "bleed"}
