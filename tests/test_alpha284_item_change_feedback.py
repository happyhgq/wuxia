"""Alpha284：任务交付与各类物品增减必须给出统一、可核对的反馈。"""
import builtins
import io
from contextlib import redirect_stdout
from types import SimpleNamespace

import engine
from actions import apply_consumable, handle_forge, handle_quest, handle_trading
from item_feedback import (
    add_inventory_items,
    format_item_change,
    remove_inventory_items,
)
from player import Player
from rewards import apply_reward_bundle
from ui_output import _ANSI_RE

QUEST = "新手采药·认识资源"


def capture(callback, *args):
    stream = io.StringIO()
    with redirect_stdout(stream):
        callback(*args)
    return _ANSI_RE.sub("", stream.getvalue())


def _no_official_save(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None, verbose=True: True)


def _quest_player():
    player = Player("物品变动验收", "散人")
    player.location = "medicine_shop"
    player.active_quests[QUEST] = 2
    player.quest_states[QUEST] = {"stage": 0, "progress": 2}
    return player


def test_item_change_format_uses_one_gain_and_loss_contract():
    assert format_item_change("铁矿石", 2, 0) == "获得：铁矿石 ×2（现有 0）"
    assert format_item_change("铁矿石", 2, 1, action="交付物品") == "交付物品：铁矿石 ×2（剩余 1）"
    assert format_item_change("铁矿石", 1, 0, action="消耗") == "消耗：铁矿石 ×1（剩余 0）"


def test_item_removal_fails_atomically_and_reports_current_count():
    player = SimpleNamespace(inventory=["铁矿石"])
    ok, remaining = remove_inventory_items(player, "铁矿石", 2)

    assert ok is False
    assert remaining == 1
    assert player.inventory == ["铁矿石"]


def test_item_addition_reports_total_held_after_stacking():
    player = SimpleNamespace(inventory=["铁矿石"])
    output = capture(add_inventory_items, player, "铁矿石", 2)

    assert player.inventory == ["铁矿石", "铁矿石", "铁矿石"]
    assert "获得：铁矿石 ×2（现有 3）" in output


def test_quest_delivery_reports_deducted_items_before_rewards(monkeypatch):
    _no_official_save(monkeypatch)
    player = _quest_player()
    player.inventory.extend(["草药", "草药"])

    output = capture(handle_quest, player, "jiaofu", [QUEST])

    assert "交付物品：草药 ×2（剩余 1）" in output
    assert output.index("交付物品：草药 ×2") < output.index("获得了 90 点经验。")
    assert output.index("交付物品：草药 ×2") < output.index("任务奖励：银两 +25。")
    assert output.index("任务奖励：银两 +25。") < output.index("恭喜完成任务")
    assert player.inventory.count("草药") == 1


def test_insufficient_quest_items_do_not_complete_or_reward(monkeypatch):
    _no_official_save(monkeypatch)
    player = _quest_player()
    before = (player.exp, player.gold, list(player.inventory))

    output = capture(handle_quest, player, "jiaofu", [QUEST])

    assert "交付失败：需要 草药 ×2（现有 1）。" in output
    assert "恭喜完成任务" not in output
    assert QUEST in player.active_quests
    assert QUEST not in player.completed_quests
    assert (player.exp, player.gold, list(player.inventory)) == before


def test_failed_reward_refunds_delivery_in_original_order(monkeypatch):
    _no_official_save(monkeypatch)
    player = _quest_player()
    player.inventory.extend(["草药", "草药"])
    before = list(player.inventory)
    original = engine.QUESTS[QUEST]
    broken = dict(original)
    broken["reward"] = {"item": "不存在的奖励物品"}
    monkeypatch.setitem(engine.QUESTS, QUEST, broken)

    output = capture(handle_quest, player, "jiaofu", [QUEST])

    assert "退还：草药 ×2（剩余 3）" in output
    assert "交付物已退还" in output
    assert player.inventory == before
    assert QUEST in player.active_quests


def test_consumable_reports_effect_and_remaining_after_atomic_removal(monkeypatch):
    _no_official_save(monkeypatch)
    player = Player("消耗反馈验收", "散人")
    player.inventory = ["疗伤药", "疗伤药"]
    player.hp = 10

    output = capture(apply_consumable, player, "疗伤药")

    assert player.inventory == ["疗伤药"]
    assert "恢复 50 点气血" in output
    assert "已消耗 1 件，剩余：疗伤药 ×1。" in output


def test_missing_consumable_fails_without_crashing_or_consuming():
    player = SimpleNamespace(inventory=[], hp=10, max_hp=100, mp=0, max_mp=100)
    output = capture(apply_consumable, player, "疗伤药")

    assert "行囊里已经没有【疗伤药】，无法使用。" in output
    assert player.inventory == []


def test_forge_announces_ore_consumption(monkeypatch):
    _no_official_save(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *_: "1")
    player = Player("锻造反馈验收", "散人")
    player.location = "blacksmith"
    player.inventory = ["铁矿石", "铁矿石"]
    player.gold = 100

    output = capture(handle_forge, player, [])

    assert "消耗：铁矿石 ×1（剩余 1）" in output
    assert "成功强化至 +1" in output
    assert player.inventory.count("铁矿石") == 1
    assert player.gold == 70


def test_forge_insufficient_ore_does_not_report_success(monkeypatch):
    _no_official_save(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *_: "1")
    player = Player("锻造失败验收", "散人")
    player.location = "blacksmith"
    player.inventory = []
    player.gold = 100

    output = capture(handle_forge, player, [])

    assert "强化材料不足" in output
    assert "成功强化" not in output
    assert player.inventory == []
    assert player.gold == 100


def test_sell_reports_quantity_removed_and_remaining(monkeypatch):
    _no_official_save(monkeypatch)
    player = Player("出售反馈验收", "散人")
    player.location = "medicine_shop"
    player.inventory = ["草药", "草药"]

    output = capture(handle_trading, player, "sell", ["草药", "1"])

    assert "卖出【草药】×1" in output
    assert "行囊中剩余【草药】×1" in output
    assert player.inventory == ["草药"]


def test_reward_bundle_reports_gained_items_with_total():
    player = Player("奖励反馈验收", "散人")
    player.inventory = []

    output = capture(
        apply_reward_bundle,
        player,
        {"items": [{"item": "疗伤药", "quantity": 2}]},
        "测试奖励",
    )

    assert "获得：疗伤药 ×2（现有 2）" in output
    assert player.inventory.count("疗伤药") == 2
