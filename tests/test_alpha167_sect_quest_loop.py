"""Alpha167：三大门派晋升历练与任务发布人配置闭环。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_quest, handle_talk_and_ask
from player import Player

ROOT = Path(__file__).resolve().parents[1]


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_each_sect_promotion_trial_is_listed_by_a_present_giver_and_can_be_accepted():
    quests = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))
    npcs = json.loads((ROOT / "data" / "npcs.json").read_text(encoding="utf-8"))
    cases = [
        ("少林", "少林历练·黑风除恶", "少林传功师兄", "shaolin_training_ground"),
        ("武当", "武当历练·以静制动", "武当传功师兄", "wudang_training_ground"),
        ("华山", "华山历练·磨剑黑风", "华山传功师兄", "huashan_training_ground"),
    ]
    for sect, quest_name, giver, room in cases:
        assert quests[quest_name].get("npc") == giver
        assert quest_name in npcs[giver].get("quests", [])
        assert giver in engine.ROOMS[room].get("npcs", [])
        p = Player(f"{sect}历练任务回归", "散人")
        assert p.join_sect(sect)[0]
        p.location = room
        prompt = capture(handle_talk_and_ask, p, [giver])
        assert quest_name in prompt
        accepted = capture(handle_quest, p, "jiequ", [quest_name])
        assert "已接取任务" in accepted
        assert quest_name in p.active_quests


def test_huashan_core_rank_investigation_is_offered_by_its_giver():
    quests = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))
    npcs = json.loads((ROOT / "data" / "npcs.json").read_text(encoding="utf-8"))
    quest_name = "青锋疑云"
    giver = "华山接引执事"
    assert quests[quest_name].get("npc") == giver
    assert quest_name in npcs[giver].get("quests", [])
    p = Player("华山调查入口回归", "散人")
    assert p.join_sect("华山")[0]
    p.level = 3
    p.location = "huashan_guest_hall"
    prompt = capture(handle_talk_and_ask, p, [giver])
    assert quest_name in prompt
    accepted = capture(handle_quest, p, "jiequ", [quest_name])
    assert "已接取任务" in accepted
    assert quest_name in p.active_quests


def test_all_sect_rank_trial_requirements_resolve_to_real_quests_and_givers():
    quests = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))
    npcs = json.loads((ROOT / "data" / "npcs.json").read_text(encoding="utf-8"))
    expected = {
        "少林": "少林历练·黑风除恶",
        "武当": "武当历练·以静制动",
        "华山": "华山历练·磨剑黑风",
    }
    for sect, quest_name in expected.items():
        assert quest_name in quests
        giver = quests[quest_name].get("npc")
        assert giver in npcs
        assert quest_name in npcs[giver].get("quests", [])
        assert quests[quest_name].get("requires", {}).get("sect") == sect
    assert "青锋疑云" in quests
    assert "青锋疑云" in npcs[quests["青锋疑云"].get("npc")].get("quests", [])
