"""Alpha271：任务完成旗标与任务列表必须保持同一完成语义。"""
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import engine
from actions import handle_quest
from player import Player


def test_v12_migration_merges_completion_flags_and_clears_stale_active_quest():
    payload = json.loads(Path("data/save.json").read_text(encoding="utf-8"))
    quest_name = "新手采药·认识资源"
    payload["active_quests"] = {quest_name: 1}
    payload["quest_states"] = {quest_name: {"stage": 0, "progress": 1}}
    payload["completed_quests"] = []
    payload.setdefault("world_state", {}).setdefault("flags", {})[
        f"quest_completed:{quest_name}"
    ] = True
    payload["world_state"]["flags"][f"quest_active:{quest_name}"] = True

    migrated, version = engine.migrate_save_data(payload)

    assert version == engine.SAVE_VERSION
    assert quest_name in migrated["completed_quests"]
    assert quest_name not in migrated["active_quests"]
    assert quest_name not in migrated["quest_states"]
    assert migrated["world_state"]["flags"][f"quest_active:{quest_name}"] is False
    assert migrated["world_state"]["flags"][f"quest_completed:{quest_name}"] is True


def test_completion_flag_alone_blocks_reacceptance_of_nonrepeatable_quest():
    player = Player("完成旗标接取保护", "散人")
    quest_name = "__alpha271_completed_flag__"
    quest = {"title": "已办妥的委托", "npc": None, "reward": {"gold": 10}}
    player.set_flag(f"quest_completed:{quest_name}", True)
    output = io.StringIO()
    with patch.object(engine, "QUESTS", {quest_name: quest}), contextlib.redirect_stdout(output):
        handle_quest(player, "jiequ", [quest_name])
    assert quest_name not in player.active_quests
    assert "已经完成过" in output.getvalue()


def test_stale_active_and_completion_flag_cannot_claim_reward_again():
    player = Player("完成旗标重复交付保护", "散人")
    quest_name = "__alpha271_stale_active__"
    quest = {"title": "旧档残留委托", "required_cnt": 1, "reward": {"gold": 99}}
    player.active_quests[quest_name] = 1
    player.quest_states[quest_name] = {"stage": 0, "progress": 1}
    player.set_flag(f"quest_completed:{quest_name}", True)
    gold_before = player.gold
    output = io.StringIO()
    with patch.object(engine, "QUESTS", {quest_name: quest}), \
         patch.object(player, "save_to_file", return_value=True), \
         contextlib.redirect_stdout(output):
        handle_quest(player, "jiaofu", [quest_name])
    assert player.gold == gold_before
    assert quest_name not in player.active_quests
    assert "不能重复交付" in output.getvalue()


def test_repeatable_quest_still_allows_replay_after_completion_flag():
    player = Player("重复任务兼容", "散人")
    quest_name = "__alpha271_repeatable__"
    quest = {"title": "可重复历练", "repeatable": True, "required_cnt": 1,
             "repeat_reward": {"gold": 3}, "reward": {"gold": 8}}
    player.completed_quests.append(quest_name)
    player.set_flag(f"quest_completed:{quest_name}", True)
    with patch.object(engine, "QUESTS", {quest_name: quest}), \
         patch.object(player, "get_npcs_in_room", return_value=[]):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handle_quest(player, "jiequ", [quest_name])
    assert quest_name in player.active_quests
