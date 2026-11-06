"""Alpha239：村道清理后的药铺复业后续委托与公告条件。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_notice_board, handle_talk_and_ask, handle_quest
from player import Player

QUEST = "村道回暖·药铺复业"
PATROL = "村道巡查·清理残匪"


def test_followup_is_locked_before_road_patrol_completion():
    p = Player("药铺后续未解锁", "散人")
    p.location = "village_square"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_notice_board(p)
    assert "村道安稳了些" not in out.getvalue()
    p.location = "village_head_house"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_talk_and_ask(p, ["村长", "接受委托", QUEST])
    assert QUEST not in p.active_quests


def test_followup_notice_appears_after_prerequisite_is_completed():
    p = Player("药铺后续线索", "散人")
    p.location = "village_square"
    p.set_flag("quest_completed:新手狩猎·野外除害", True)
    p.set_flag("quest_completed:" + PATROL, True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_notice_board(p)
    text = out.getvalue()
    assert "黑风山道近来安稳了些" in text
    assert QUEST not in text
    assert "可接取" not in text


def test_followup_talk_progress_and_turn_in_apply_world_outcome_once():
    p = Player("药铺复业流程", "散人")
    p.location = "village_head_house"
    p.set_flag("quest_completed:" + PATROL, True)
    with contextlib.redirect_stdout(io.StringIO()):
        handle_talk_and_ask(p, ["村长", "接受委托", QUEST])
    assert QUEST in p.active_quests
    p.update_quest_progress("药铺老板", event_type="talk")
    assert p.active_quests[QUEST] == 1
    p.location = "village_head_house"
    p.economy_state = getattr(p, "economy_state", {})
    # Use the normal quest-delivery path; no physical item is required for this talk objective.
    with contextlib.redirect_stdout(io.StringIO()):
        handle_quest(p, "jiaofu", [QUEST])
    assert QUEST not in p.active_quests
    assert QUEST in p.completed_quests
    assert p.get_flag("world:main:herb_trade_resumed") is True
    assert p.get_flag("quest:village_road_herb_trade:resolved") is True
    reputation = p.get_var("village_reputation", 0)
    with contextlib.redirect_stdout(io.StringIO()):
        handle_quest(p, "jiaofu", [QUEST])
    assert p.get_var("village_reputation", 0) == reputation


def test_followup_has_valid_target_and_reward_item_free_completion():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    q = quests[QUEST]
    assert q["npc"] == "村长" and q["turn_in_npc"] == "村长"
    assert q["requires"]["flags"] == ["quest_completed:" + PATROL]
    assert q["stages"][0]["target_type"] == "talk"
    assert q["stages"][0]["target_name"] == "药铺老板"
    assert q["stages"][0]["target_name"] in engine.NPCS
