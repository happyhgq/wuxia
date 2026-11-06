"""Alpha240：让药铺复业后真正补齐药材库存，形成采集—交付—世界结果闭环。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_notice_board, handle_talk_and_ask, handle_quest
from player import Player

QUEST = "百草备货·补齐药材"
FOLLOW_UP = "村道回暖·药铺复业"


def _ready_player(name="药材补货验收"):
    p = Player(name, "散人")
    p.location = "medicine_shop"
    p.set_flag("quest_completed:" + FOLLOW_UP, True)
    p.set_flag("world:main:herb_trade_resumed", True)
    return p


def test_restock_quest_requires_herb_trade_to_have_resumed():
    q = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))[QUEST]
    assert q["target_type"] == "collect"
    assert q["target_name"] == "草药" and q["required_cnt"] == 3
    assert q["turn_in_npc"] == "药铺老板"
    p = Player("药材任务门槛", "散人")
    p.location = "medicine_shop"
    with contextlib.redirect_stdout(io.StringIO()):
        handle_talk_and_ask(p, ["药铺老板", "接受委托", QUEST])
    assert QUEST not in p.active_quests


def test_restock_clue_is_hidden_until_prerequisite_and_then_natural_language():
    p = Player("药材公告线索", "散人")
    p.location = "village_square"
    p.completed_quests.append("新手采药·认识资源")
    p.set_flag("quest_completed:新手采药·认识资源", True)
    p.set_flag("quest_completed:" + FOLLOW_UP, True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_notice_board(p)
    assert "常用药材仍有缺口" not in out.getvalue()
    p.set_flag("world:main:herb_trade_resumed", True)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_notice_board(p)
    assert "常用药材仍有缺口" in out.getvalue()
    assert QUEST not in out.getvalue()
    assert "可接取" not in out.getvalue()


def test_restock_quest_requires_three_herbs_and_turns_in_once():
    p = _ready_player()
    with contextlib.redirect_stdout(io.StringIO()):
        handle_talk_and_ask(p, ["药铺老板", "接受委托", QUEST])
    assert QUEST in p.active_quests
    if "草药" in p.inventory:
        p.inventory.remove("草药")
    p.inventory.extend(["草药", "草药"])
    p.update_quest_progress("草药", event_type="collect")
    p.update_quest_progress("草药", event_type="collect")
    p.update_quest_progress("草药", event_type="collect")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_quest(p, "jiaofu", [QUEST])
    assert QUEST in p.active_quests
    assert "交付失败" in out.getvalue()
    p.inventory.append("草药")
    p.location = "medicine_shop"
    before = p.get_var("village_reputation", 0)
    with contextlib.redirect_stdout(io.StringIO()):
        handle_quest(p, "jiaofu", [QUEST])
    assert QUEST not in p.active_quests
    assert QUEST in p.completed_quests
    assert p.get_flag("world:main:herb_stock_replenished") is True
    assert p.get_flag("quest:village_herb_restock:resolved") is True
    assert p.get_var("village_reputation", 0) == before + 1
    assert p.inventory.count("草药") == 0
    assert p.inventory.count("疗伤药") >= 1
    with contextlib.redirect_stdout(io.StringIO()):
        handle_quest(p, "jiaofu", [QUEST])
    assert p.get_var("village_reputation", 0) == before + 1


def test_restock_quest_data_has_valid_reward_and_existing_npc():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    q = quests[QUEST]
    assert q["requires"]["flags"] == [
        "quest_completed:" + FOLLOW_UP,
        "world:main:herb_trade_resumed",
    ]
    assert q["reward"]["item"] in engine.ITEMS
    assert q["target_name"] in engine.ITEMS
    assert "药铺老板" in engine.NPCS
