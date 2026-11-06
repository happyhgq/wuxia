"""Alpha200：任务奖励结算与重复交付防护。"""
from contextlib import redirect_stdout
from io import StringIO

import engine
from actions import handle_quest
from player import Player


def test_completed_quest_cannot_be_turned_in_twice_for_duplicate_rewards():
    player = Player("任务重复交付验收", "散人")
    quest_name = "铁衣门历练·护路除匪"
    quest = engine.QUESTS[quest_name]
    player.level = 25
    player.location = next(
        room_id for room_id, room in engine.ROOMS.items()
        if quest["turn_in_npc"] in room.get("npcs", [])
    )
    assert player.join_sect("铁衣门")[0]
    player.active_quests[quest_name] = quest["required_cnt"]
    player.quest_states[quest_name] = {"stage": 0, "progress": quest["required_cnt"]}

    gold_before = player.gold
    rep_before = player.get_sect_reputation("铁衣门")
    exp_before = player.exp
    with redirect_stdout(StringIO()):
        handle_quest(player, "jiaofu", [quest_name])

    assert quest_name not in player.active_quests
    assert player.gold == gold_before + quest["reward"]["gold"]
    assert player.get_sect_reputation("铁衣门") == rep_before + quest["reward"]["sect_reputation"]["铁衣门"]
    assert player.exp != exp_before or player.level > 1

    gold_after = player.gold
    rep_after = player.get_sect_reputation("铁衣门")
    exp_after = player.exp
    output = StringIO()
    with redirect_stdout(output):
        handle_quest(player, "jiaofu", [quest_name])

    assert "未接取" in output.getvalue()
    assert player.gold == gold_after
    assert player.get_sect_reputation("铁衣门") == rep_after
    assert player.exp == exp_after


def test_incomplete_quest_cannot_be_turned_in_or_receive_rewards():
    player = Player("未完成任务验收", "散人")
    quest_name = "铁衣门历练·护路除匪"
    quest = engine.QUESTS[quest_name]
    player.level = 25
    player.location = next(
        room_id for room_id, room in engine.ROOMS.items()
        if quest["turn_in_npc"] in room.get("npcs", [])
    )
    assert player.join_sect("铁衣门")[0]
    player.active_quests[quest_name] = 0
    player.quest_states[quest_name] = {"stage": 0, "progress": 0}
    gold_before = player.gold
    rep_before = player.get_sect_reputation("铁衣门")
    exp_before = player.exp

    output = StringIO()
    with redirect_stdout(output):
        handle_quest(player, "jiaofu", [quest_name])

    assert "未达成" in output.getvalue()
    assert quest_name in player.active_quests
    assert player.gold == gold_before
    assert player.get_sect_reputation("铁衣门") == rep_before
    assert player.exp == exp_before
