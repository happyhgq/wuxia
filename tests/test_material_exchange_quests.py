# -*- coding: utf-8 -*-
"""材料兑换委托：接取按库存登记、多物品交付、奖励失败回滚与复做冷却。"""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path

import engine
from actions import handle_quest
from player import Player

ROOT = Path(__file__).resolve().parents[1]

HERB_QUEST = "百草堂·草药换伤药"
MEAT_QUEST = "悦来客栈·野味换干粮"
SCRAP_QUEST = "打铁铺·军械回炉"
COIN_QUEST = "沉河·铜钱换伤药"


def _data(name):
    return json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))[name]


def _run(player, command, quest_name):
    output = StringIO()
    with redirect_stdout(output):
        ok = handle_quest(player, command, [quest_name])
    return ok, output.getvalue()


def _herb_player():
    player = Player("草药兑换验收", "散人")
    player.level = 5
    player.location = "medicine_shop"
    return player


def test_exchange_definitions_are_repeatable_with_shared_cooldown():
    expected = {
        HERB_QUEST: ("药铺老板", {"item": "金创药"}),
        SCRAP_QUEST: ("铁匠", {"items": [{"item": "铁矿石", "quantity": 2}]}),
        COIN_QUEST: ("沉河捞尸人", {"items": [{"item": "金创药", "quantity": 1}]}),
    }
    for name, (npc, reward) in expected.items():
        quest = _data(name)
        assert quest["npc"] == npc and quest["turn_in_npc"] == npc
        assert quest["repeatable"] is True and quest["retryable"] is True
        assert quest["repeat_cooldown_ticks"] == 12
        assert quest["reward"] == reward
        assert quest["repeat_reward"] == reward

    meat = _data(MEAT_QUEST)
    assert meat["repeatable"] is True and meat["repeat_cooldown_ticks"] == 12
    assert [stage["target_type"] for stage in meat["stages"]] == ["collect", "collect"]
    assert [(stage["target_name"], stage["required_cnt"]) for stage in meat["stages"]] == [
        ("野猪肉", 3),
        ("山獐肉", 2),
    ]
    assert meat["reward"] == {"item": "行军干粮"}
    assert meat["repeat_reward"] == {"item": "行军干粮"}


def test_herb_exchange_registers_hoarded_materials_and_consumes_them(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = _herb_player()
    player.inventory.extend(["草药"] * 6)
    held_before = player.inventory.count("草药")

    ok, output = _run(player, "jiequ", HERB_QUEST)
    assert ok is True
    assert "已按行囊现有材料登记" in output
    assert player.active_quests[HERB_QUEST] == 6
    assert player.is_quest_goal_complete(HERB_QUEST) is True

    ok, output = _run(player, "jiaofu", HERB_QUEST)
    assert ok is True
    assert "恭喜完成任务" in output
    assert player.inventory.count("草药") == held_before - 6
    assert player.inventory.count("金创药") == 1
    assert HERB_QUEST in player.completed_quests
    assert HERB_QUEST not in player.active_quests


def test_meat_exchange_delivers_two_kinds_of_material_together(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("野味兑换验收", "散人")
    player.level = 6
    player.location = "inn"
    player.inventory.extend(["野猪肉"] * 3 + ["山獐肉"] * 2)

    ok, output = _run(player, "jiequ", MEAT_QUEST)
    assert ok is True
    assert "野猪肉 3/3" in output and "山獐肉 2/2" in output

    ok, output = _run(player, "jiaofu", MEAT_QUEST)
    assert ok is True
    assert "恭喜完成任务" in output
    assert player.inventory.count("野猪肉") == 0
    assert player.inventory.count("山獐肉") == 0
    assert player.inventory.count("行军干粮") == 1


def test_meat_exchange_keeps_materials_when_one_kind_is_short(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("野味缺料验收", "散人")
    player.level = 6
    player.location = "inn"
    player.inventory.extend(["野猪肉"] * 3 + ["山獐肉"] * 1)
    ok, _ = _run(player, "jiequ", MEAT_QUEST)
    assert ok is True
    assert player.is_quest_goal_complete(MEAT_QUEST) is False
    pork_before = player.inventory.count("野猪肉")

    ok, output = _run(player, "jiaofu", MEAT_QUEST)
    assert ok is False
    assert "交付失败" in output and "山獐肉 ×2（现有 1）" in output
    assert player.inventory.count("野猪肉") == pork_before
    assert player.inventory.count("山獐肉") == 1
    assert MEAT_QUEST in player.active_quests


def test_multi_item_delivery_rolls_back_when_reward_bundle_is_invalid(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("野味回滚验收", "散人")
    player.level = 6
    player.location = "inn"
    player.inventory.extend(["野猪肉"] * 3 + ["山獐肉"] * 2)
    original = engine.QUESTS[MEAT_QUEST]
    broken = dict(original)
    broken["reward"] = {"item": "不存在的奖励物品"}
    monkeypatch.setitem(engine.QUESTS, MEAT_QUEST, broken)
    ok, _ = _run(player, "jiequ", MEAT_QUEST)
    assert ok is True
    before = list(player.inventory)

    ok, output = _run(player, "jiaofu", MEAT_QUEST)
    assert ok is False
    assert "交付物已退还" in output
    assert player.inventory == before
    assert MEAT_QUEST in player.active_quests
    assert MEAT_QUEST not in player.completed_quests


def test_repeat_exchange_requires_cooldown_and_can_run_again(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = _herb_player()
    player.inventory.extend(["草药"] * 6)
    assert _run(player, "jiequ", HERB_QUEST)[0] is True
    assert _run(player, "jiaofu", HERB_QUEST)[0] is True
    assert player.inventory.count("金创药") == 1

    ok, output = _run(player, "jiequ", HERB_QUEST)
    assert ok is False
    assert "再等待 12 个世界时刻" in output

    player.set_var("quest_clock", 12)
    player.inventory.extend(["草药"] * 6)
    ok, output = _run(player, "jiequ", HERB_QUEST)
    assert ok is True, output
    ok, output = _run(player, "jiaofu", HERB_QUEST)
    assert ok is True
    assert player.inventory.count("金创药") == 2
    assert player.get_var(f"quest_repeat_last_completed:{HERB_QUEST}") == player.get_quest_clock()


def test_scrap_and_coin_exchanges_pay_out_their_items(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    for quest_name, location, material, payout, payout_count in (
        (SCRAP_QUEST, "blacksmith", "黑风寨军械残片", "铁矿石", 2),
        (COIN_QUEST, "sunken_weir", "沉河铜钱", "金创药", 1),
    ):
        player = Player(f"{quest_name}验收", "散人")
        player.level = 10
        player.location = location
        player.inventory.extend([material] * 6)
        paid_before = player.inventory.count(payout)

        assert _run(player, "jiequ", quest_name)[0] is True
        ok, output = _run(player, "jiaofu", quest_name)
        assert ok is True, output
        assert player.inventory.count(material) == 0
        assert player.inventory.count(payout) == paid_before + payout_count
        assert quest_name in player.completed_quests
