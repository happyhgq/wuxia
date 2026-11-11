# -*- coding: utf-8 -*-
"""P4.0 P2：治疗反馈取实际恢复量、延迟存档顺序、非四向出口预检。"""
import builtins
import contextlib
import io
import json
from unittest.mock import patch

import main
import player as player_module
from player import Player


def _run_main_loop(player, commands, prompt_input="y"):
    output = io.StringIO()
    with patch.object(main.os.path, "exists", return_value=True), \
         patch.object(main.Player, "load_from_file", return_value=player), \
         patch.object(main.Player, "save_to_file", lambda self, filename=None: True), \
         patch.object(builtins, "input", return_value=prompt_input), \
         patch.object(main, "read_command", side_effect=list(commands)), \
         patch.object(main, "clear_screen"), \
         patch.object(main, "look"), \
         patch.object(main, "announce_pending_npc_movement"), \
         patch.object(main, "announce_pending_caravan_arrivals"), \
         contextlib.redirect_stdout(output):
        main.main()
    return output.getvalue()


def _player_at(location, name="P2验收"):
    player = Player(name, "散人")
    player.location = location
    player.set_var("quest_clock", 7)
    return player


def test_heal_rejects_full_health_without_advancing_time():
    player = _player_at("village_square")
    player.hp = player.max_hp
    player.mp = player.max_mp

    output = _run_main_loop(player, ["疗伤", "退出"])

    assert "你气血充盈，无需打坐调息。" in output
    assert player.hp == player.max_hp and player.mp == player.max_mp
    assert player.get_quest_clock() == 7


def test_heal_reports_percentage_recovery_and_mp_cost():
    player = _player_at("village_square")
    player.hp = player.max_hp - 10
    player.mp = player.max_mp

    output = _run_main_loop(player, ["疗伤", "退出"])

    assert "恢复了 5 点气血，消耗 5 点内力。" in output
    assert player.hp == player.max_hp - 5
    assert player.mp == player.max_mp - 5
    assert player.get_quest_clock() == 8


def test_deferred_save_waits_for_post_action_tick(tmp_path, monkeypatch):
    target = tmp_path / "save.json"
    monkeypatch.setattr(player_module, "SAVE_PATH", str(target))
    player = _player_at("village_square")

    player.begin_deferred_save()
    assert player.save_to_file(str(target), verbose=False) is True
    assert not target.exists()

    player.set_var("quest_clock", 8)
    assert player.flush_deferred_save() is True

    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["world_state"]["variables"]["quest_clock"] == 8


def test_deferred_save_explicit_path_is_written_immediately(tmp_path):
    target = tmp_path / "explicit_save.json"
    player = _player_at("village_square")

    player.begin_deferred_save()
    assert player.save_to_file(str(target), verbose=False) is True
    assert target.exists()

    # 显式路径不属于延迟窗口，收尾时不应再补写一次。
    assert player.flush_deferred_save() is False
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["world_state"]["variables"]["quest_clock"] == 7


def test_missing_indoor_exit_costs_no_time():
    player = _player_at("village_square")
    assert "内" not in main.engine.ROOMS["village_square"].get("exits", {})

    _run_main_loop(player, ["内", "退出"])

    assert player.get_quest_clock() == 7


def test_missing_outdoor_exit_costs_no_time():
    player = _player_at("village_square")
    assert "外" not in main.engine.ROOMS["village_square"].get("exits", {})

    _run_main_loop(player, ["外", "退出"])

    assert player.get_quest_clock() == 7
