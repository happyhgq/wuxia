"""Alpha256：四大门派历练任务形成可验证的前后衔接。"""
import json
from pathlib import Path

import engine
from actions import _quest_npc_status, _quests_for_npc
from player import Player

ROOT = Path(__file__).resolve().parents[1]


def test_each_sect_has_a_followup_trial_after_its_introductory_trial():
    expected = {
        "少林": ("少林历练·黑风除恶", "少林历练·巡山护戒", "少林传功师兄"),
        "武当": ("武当历练·以静制动", "武当历练·松径清扰", "武当传功师兄"),
        "华山": ("华山历练·磨剑黑风", "华山历练·险道试剑", "华山传功师兄"),
        "铁衣门": ("铁衣门历练·护路除匪", "铁衣门历练·清除巡哨", "铁衣门护运执事"),
    }
    for sect, (first, second, npc) in expected.items():
        row = engine.QUESTS[second]
        assert row["npc"] == npc and row["turn_in_npc"] == npc
        assert row["requires"]["sect"] == sect
        assert first in row["requires"]["completed_quests"]
        assert row["target_type"] == "kill" and row["required_cnt"] >= 1
        assert row["target_name"] in engine.ENEMIES
        assert second in _quests_for_npc(npc)


def test_followup_quest_is_locked_until_introductory_trial_is_completed():
    p = Player("门派历练衔接测试", "散人")
    p.level = 20
    assert p.join_sect("少林")[0]
    state, detail = _quest_npc_status(p, "少林历练·巡山护戒")
    assert state == "未开放"
    assert "少林历练·黑风除恶" in detail
    p.completed_quests.append("少林历练·黑风除恶")
    state, _ = _quest_npc_status(p, "少林历练·巡山护戒")
    assert state == "未领取"


def test_followup_quests_have_natural_language_npc_guidance():
    npcs = json.loads((ROOT / "data" / "npcs.json").read_text(encoding="utf-8"))
    expected = {
        "少林传功师兄": "少林历练·巡山护戒",
        "武当传功师兄": "武当历练·松径清扰",
        "华山传功师兄": "华山历练·险道试剑",
        "铁衣门护运执事": "铁衣门历练·清除巡哨",
    }
    for npc, quest in expected.items():
        assert quest in npcs[npc]["quests"]
        assert quest in npcs[npc].get("info", {}).get("后续历练", "")
