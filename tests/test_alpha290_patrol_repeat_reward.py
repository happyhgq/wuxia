# -*- coding: utf-8 -*-
"""Alpha290：断魂岭·巡道除匪复做奖励调整为 160 经验 / 60 银两。"""
import contextlib
import io
import json
from pathlib import Path

import engine
import player as player_module
from actions import handle_quest
from player import Player

ROOT = Path(__file__).resolve().parents[1]
QUEST_NAME = "断魂岭·巡道除匪"


def _deliver(player):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_quest(player, "jiaofu", [QUEST_NAME])
    return output.getvalue()


def _ready_player(completed):
    player = Player("巡道复做奖励测试", "华山")
    player.level = 12
    player.exp = 0
    player.exp_to_level = player_module.exp_needed_for_level(12)
    player.gold = 100
    player.location = "duanhun_camp"
    if completed:
        player.completed_quests.append(QUEST_NAME)
        player.set_var("quest_clock", 100)
        player.set_var(f"quest_repeat_last_completed:{QUEST_NAME}", 40)
    player.active_quests[QUEST_NAME] = 2
    return player


def test_patrol_reward_data_keeps_first_completion_and_separate_repeat_reward():
    quest = engine.QUESTS[QUEST_NAME]
    assert quest["reward"] == {"exp": 300, "gold": 90, "honor_delta": 1}
    assert quest["repeat_reward"] == {"exp": 160, "gold": 60}
    assert "honor_delta" not in quest["repeat_reward"]
    assert quest["repeat_cooldown_ticks"] == 48


def test_patrol_first_completion_uses_full_reward(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = _ready_player(completed=False)
    output = _deliver(player)
    assert "恭喜完成任务" in output
    assert player.exp == 300
    assert player.gold == 190
    assert QUEST_NAME in player.completed_quests
    assert QUEST_NAME not in player.active_quests


def test_patrol_repeat_completion_uses_160_exp_60_gold(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = _ready_player(completed=True)
    output = _deliver(player)
    assert "恭喜完成任务" in output
    assert player.exp == 160
    assert player.gold == 160
    assert player.get_var(f"quest_repeat_last_completed:{QUEST_NAME}") == player.get_quest_clock()


def test_patrol_repeat_reward_stays_out_of_permanent_growth():
    data = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))[QUEST_NAME]
    assert set(data["repeat_reward"]) == {"exp", "gold"}
