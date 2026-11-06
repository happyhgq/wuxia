"""Alpha238：新手狩猎后的村道巡查委托，连接新手任务与黑风山道。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_notice_board, handle_talk_and_ask
from player import Player

QUEST = "村道巡查·清理残匪"


def test_village_road_patrol_is_gated_by_newcomer_hunt_completion():
    quest = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))[QUEST]
    assert quest["npc"] == "村长"
    assert quest["turn_in_npc"] == "村长"
    assert quest["requires"]["flags"] == ["quest_completed:新手狩猎·野外除害"]
    assert quest["target_type"] == "kill"
    assert quest["target_name"] == "山贼"
    assert quest["required_cnt"] == 2
    assert quest["reward"]["item"] in engine.ITEMS
    assert quest["notice_location"] == "村中广场"


def test_notice_board_shows_natural_clue_without_internal_task_name():
    p = Player("村道委托公告验收", "散人")
    p.location = "village_square"
    p.set_flag("newcomer:guide_seen", True)
    p.set_flag("quest_completed:新手狩猎·野外除害", True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_notice_board(p)
    text = output.getvalue()
    assert "黑风山道仍有山贼拦路" in text
    assert "村长宅院" in text
    assert QUEST not in text
    assert "可接取" not in text
    assert "任务 接取" not in text


def test_village_chief_offers_patrol_only_after_hunt_completion():
    p = Player("村道委托流程验收", "散人")
    p.location = "village_head_house"
    p.set_flag("quest_completed:新手狩猎·野外除害", True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_talk_and_ask(p, ["村长", "接受委托", QUEST])
    assert QUEST in p.active_quests
    assert p.get_flag("quest:village_road_patrol:started") is True
    assert "已接取任务" in output.getvalue() and "已加入你的任务列表" in output.getvalue()


def test_village_road_patrol_cannot_be_taken_before_hunt_completion():
    p = Player("村道委托门槛验收", "散人")
    p.location = "village_head_house"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_talk_and_ask(p, ["村长", "接受委托", QUEST])
    assert QUEST not in p.active_quests
    assert "需先完成并交付【初入江湖·野外除害】" in output.getvalue() and "还需先满足一些条件" not in output.getvalue()
