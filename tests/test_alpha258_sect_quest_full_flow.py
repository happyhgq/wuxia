"""Alpha258：四门派后续历练的接取、目标、交付、奖励与存档回归。"""
import contextlib
import io
import json
from pathlib import Path

import pytest
import engine
from actions import handle_quest
from player import Player

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("少林", "少林历练·黑风除恶", "少林历练·巡山护戒", "少林传功师兄", "shaolin_training_ground", "黑风寨精锐", 2),
    ("武当", "武当历练·以静制动", "武当历练·松径清扰", "武当传功师兄", "wudang_training_ground", "黑风寨精锐", 2),
    ("华山", "华山历练·磨剑黑风", "华山历练·险道试剑", "华山传功师兄", "huashan_training_ground", "黑风寨刀阵头目", 1),
    ("铁衣门", "铁衣门历练·护路除匪", "铁衣门历练·清除巡哨", "铁衣门护运执事", "tieyi_outer_court", "黑风寨精锐", 2),
]


def capture(fn, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        fn(*args)
    return output.getvalue()


@pytest.mark.parametrize("sect,prerequisite,quest,npc,room,target,count", CASES)
def test_followup_trial_full_flow_and_v12_save_restore(
    sect, prerequisite, quest, npc, room, target, count, tmp_path, monkeypatch
):
    # Quest completion ordinarily saves to the game path. Isolate that side effect;
    # this test explicitly exercises save/load against a temporary V12 save instead.
    real_save_to_file = Player.save_to_file
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player(f"{sect}历练全流程测试", "散人")
    player.level = 30
    ok, message = player.join_sect(sect)
    assert ok, message
    player.completed_quests.append(prerequisite)
    player.location = room

    before_gold = player.gold
    before_rep = player.get_sect_reputation(sect)
    before_exp = player.exp

    accepted = capture(handle_quest, player, "jiequ", [quest])
    assert "已接取任务" in accepted
    assert quest in player.active_quests

    # Progress must not exceed the configured objective count.
    for _ in range(count + 1):
        capture(player.update_quest_progress, target, "kill")
    assert player.active_quests[quest] == count

    # Active task progress must survive a V12 save/load before the quest is turned in.
    active_save = tmp_path / f"{sect}_active_save.json"
    assert real_save_to_file(player, str(active_save))
    active_raw = json.loads(active_save.read_text(encoding="utf-8"))
    assert active_raw["version"] == engine.SAVE_VERSION
    player = Player.load_from_file(str(active_save))
    assert player is not None
    assert player.active_quests[quest] == count

    # Delivery is tied to the configured NPC, not any arbitrary location.
    player.location = "village_square" if room != "village_square" else "main_road"
    blocked = capture(handle_quest, player, "jiaofu", [quest])
    assert f"请回到【{npc}】处交付任务" in blocked
    assert quest in player.active_quests
    assert player.gold == before_gold
    assert player.get_sect_reputation(sect) == before_rep

    player.location = room
    completed = capture(handle_quest, player, "jiaofu", [quest])
    assert "奖励已结算" in completed
    assert quest not in player.active_quests
    assert quest in player.completed_quests
    assert player.gold > before_gold
    assert player.get_sect_reputation(sect) > before_rep
    assert player.exp >= before_exp

    save_path = tmp_path / f"{sect}_save.json"
    assert real_save_to_file(player, str(save_path))
    raw = json.loads(save_path.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION
    restored = Player.load_from_file(str(save_path))
    assert restored is not None
    assert quest in restored.completed_quests
    assert quest not in restored.active_quests
    assert restored.get_sect() == sect
    assert restored.get_sect_reputation(sect) == player.get_sect_reputation(sect)


def test_followup_trial_cannot_be_accepted_without_its_prerequisite():
    sect, prerequisite, quest, npc, room, *_ = CASES[0]
    player = Player("门派历练前置条件测试", "散人")
    player.level = 30
    assert player.join_sect(sect)[0]
    player.location = room
    output = capture(handle_quest, player, "jiequ", [quest])
    assert "接取失败" in output
    assert quest not in player.active_quests
