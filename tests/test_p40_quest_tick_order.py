# -*- coding: utf-8 -*-
"""P4.0 P0：任务变更先按行动时的时钟结算，再推进世界时刻。"""
import builtins
import contextlib
import io
from unittest.mock import patch

import engine
import main
from player import Player

CHIEF_ROOM = "village_chief_room"
TIMED_QUEST = "黑风限时追缉"
KILL_QUEST = "清剿黑风山"


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


def _player_with_quest(quest_name, clock, progress, accepted_at=0):
    player = Player("任务计时验收", "散人")
    player.location = CHIEF_ROOM
    player.set_var("quest_clock", clock)
    player.active_quests[quest_name] = progress
    player.quest_states[quest_name] = {
        "stage": 0,
        "progress": progress,
        "accepted_at": accepted_at,
    }
    return player


def _chief_in_chief_room(clock):
    """确认测试前提：该时刻村长确实位于任务发布房间。"""
    player = _player_with_quest(KILL_QUEST, clock, 1)
    return "村长" in player.get_npcs_in_room(CHIEF_ROOM)


def test_timed_quest_delivered_on_last_on_time_tick_completes():
    player = _player_with_quest(TIMED_QUEST, clock=7, progress=2, accepted_at=0)
    assert engine.QUESTS[TIMED_QUEST]["time_limit"] == 8
    assert _chief_in_chief_room(7)
    gold_before = player.gold

    _run_main_loop(player, [f"交付 {TIMED_QUEST}", "退出"])

    assert TIMED_QUEST not in player.active_quests
    assert TIMED_QUEST in player.completed_quests
    assert not player.get_flag(f"quest_failed:{TIMED_QUEST}", False)
    assert player.gold == gold_before + engine.QUESTS[TIMED_QUEST]["reward"]["gold"]
    assert player.get_quest_clock() == 8


def test_chief_schedule_boundary_does_not_break_turn_in_at_clock_7():
    player = _player_with_quest(KILL_QUEST, clock=7, progress=1)
    assert _chief_in_chief_room(7)
    gold_before = player.gold

    _run_main_loop(player, [f"交付 {KILL_QUEST}", "退出"])

    assert KILL_QUEST not in player.active_quests
    assert KILL_QUEST in player.completed_quests
    assert player.gold == gold_before + engine.QUESTS[KILL_QUEST]["reward"]["gold"]
    assert player.get_quest_clock() == 8


def test_deliver_not_active_quest_costs_no_time():
    player = _player_with_quest(KILL_QUEST, clock=7, progress=1)
    player.active_quests.clear()
    player.quest_states.clear()
    player.location = "village_square"

    _run_main_loop(player, ["交付 清剿黑风山", "退出"])

    assert player.get_quest_clock() == 7


def test_malformed_branch_choice_costs_no_time():
    player = _player_with_quest(KILL_QUEST, clock=7, progress=1)
    player.location = "village_square"

    _run_main_loop(player, ["选择", "退出"])

    assert player.get_quest_clock() == 7
    assert KILL_QUEST in player.active_quests


def test_abandon_unknown_quest_costs_no_time_but_success_advances():
    player = _player_with_quest(KILL_QUEST, clock=7, progress=1)
    player.location = "village_square"

    _run_main_loop(player, ["放弃 不存在的任务", "退出"])
    assert player.get_quest_clock() == 7
    assert KILL_QUEST in player.active_quests

    _run_main_loop(player, [f"放弃 {KILL_QUEST}", "退出"])
    assert player.get_quest_clock() == 8
    assert KILL_QUEST not in player.active_quests
