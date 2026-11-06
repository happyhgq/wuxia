# -*- coding: utf-8 -*-
"""Alpha296：客栈住店按实际睡眠推进到下一次黎明。"""
import builtins
import contextlib
import io
import json
import os
import tempfile
from unittest.mock import patch

import pytest

import main
from actions import handle_inn_service
from player import Player
from world_time import format_world_clock, ticks_until_next_dawn, world_hour


def _run_main_loop(player, commands):
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value="y"), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(io.StringIO()):
        main.main()


@pytest.mark.parametrize("clock,expected", [
    (0, 24),   # 06:00 恰好黎明，睡到次日 06:00
    (23, 1),   # 05:00 再睡一个时刻天亮
    (7, 17),   # 13:00 睡到次日 06:00
    (13, 11),  # 19:00 睡到次日 06:00
    (18, 6),   # 00:00 睡到 06:00
])
def test_ticks_until_next_dawn_covers_day_and_night(clock, expected):
    assert ticks_until_next_dawn(clock) == expected
    assert world_hour(clock + expected) == 6


def test_inn_stay_reports_real_sleep_steps_and_restores_health():
    player = Player("住店换算")
    player.location = "inn"
    player.set_var("quest_clock", 7)  # 未时 13:00
    player.hp, player.mp, player.gold = 20, 5, 50
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        steps = handle_inn_service(player, "住店")
    assert steps == 17
    assert player.get_quest_clock() == 7  # 世界推进由主循环统一执行，避免直接调用时重复计时
    assert (player.hp, player.mp, player.gold) == (player.max_hp, player.max_mp, 38)
    assert player.world_state["variables"]["inn_nights_stayed"] == 1
    assert "这一觉过去 17 个世界时刻" in output.getvalue()
    assert "卯时 06:00" in output.getvalue()


def test_main_loop_stay_advances_to_dawn():
    player = Player("过夜主循环")
    player.location = "inn"
    player.set_var("quest_clock", 7)
    player.gold = 50
    _run_main_loop(player, ["住店", "退出"])
    assert player.get_quest_clock() == 24
    assert format_world_clock(player.get_quest_clock()) == "卯时 06:00"
    assert world_hour(player.get_quest_clock()) == 6
    assert player.gold == 38


def test_main_loop_failed_stay_costs_no_time():
    player = Player("住店失败")
    player.location = "inn"
    player.set_var("quest_clock", 7)
    player.gold = 0
    player.hp = 20
    _run_main_loop(player, ["住店", "退出"])
    assert player.get_quest_clock() == 7
    assert player.gold == 0
    assert player.hp == 20


def test_stay_does_not_add_new_save_fields():
    player = Player("住店存档")
    player.location = "inn"
    player.set_var("quest_clock", 7)
    player.gold = 50
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            steps = handle_inn_service(player, "住店")
        player.tick_quest_clock(steps)
        player.save_to_file(path)
        with open(path, encoding="utf8") as f:
            raw = json.load(f)
        assert raw["version"] == 12
        assert raw["world_state"]["variables"]["inn_nights_stayed"] == 1
        assert "inn_overnight" not in raw
        assert "inn_overnight" not in raw["world_state"]
    finally:
        os.remove(path)
