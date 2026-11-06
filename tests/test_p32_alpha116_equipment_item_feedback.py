"""Alpha116：装备与使用物品的反馈应准确，成功使用后保存。"""
from types import SimpleNamespace

import engine
import actions


class FakePlayer:
    def __init__(self, inventory):
        self.inventory = list(inventory)
        self.hp = 20
        self.max_hp = 100
        self.mp = 10
        self.max_mp = 100
        self.gold = 100
        self.economy_state = {"events": {}}
        self.world_state = {"variables": {"quest_clock": 1}}
        self.save_count = 0

    def save_to_file(self):
        self.save_count += 1


def test_use_requires_unambiguous_item_name_and_does_not_consume_on_ambiguity(monkeypatch, capsys):
    player = FakePlayer(["小还丹", "小还丹（旧）"])
    monkeypatch.setattr(actions, "apply_consumable", lambda *_: (_ for _ in ()).throw(AssertionError("must not use ambiguous item")))
    actions.handle_equipment_and_items(player, "use", ["丹"])
    output = capsys.readouterr().out
    assert "请尽量输入完整物品名称" in output
    assert player.inventory == ["小还丹", "小还丹（旧）"]
    assert player.save_count == 0


def test_use_exact_item_saves_only_after_success(monkeypatch, capsys):
    player = FakePlayer(["小还丹"])
    called = []
    monkeypatch.setattr(actions, "apply_consumable", lambda p, name: called.append(name) or True)
    actions.handle_equipment_and_items(player, "use", ["小还丹"])
    output = capsys.readouterr().out
    assert called == ["小还丹"]
    assert player.save_count == 1
    assert "已消耗 1 件" in output


def test_failed_use_does_not_claim_saved_success(monkeypatch, capsys):
    player = FakePlayer(["小还丹"])
    monkeypatch.setattr(actions, "apply_consumable", lambda *_: False)
    actions.handle_equipment_and_items(player, "use", ["小还丹"])
    output = capsys.readouterr().out
    assert player.save_count == 0
    assert "已消耗 1 件" not in output
