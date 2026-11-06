"""Alpha204：武器附带效果应由物品数据驱动，且只在命中后触发。"""
import combat
import engine
from types import SimpleNamespace


def _player(weapon):
    return SimpleNamespace(equipment={"weapon": weapon})


def test_heavy_sword_can_apply_armor_break(monkeypatch):
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    statuses = {}
    messages = combat.apply_weapon_combat_effect(_player("玄铁重剑"), statuses)
    assert statuses["armor_break"] == {"turns": 2, "value": 6}
    assert messages and "破防" in messages[0]


def test_quality_variant_inherits_base_weapon_effect(monkeypatch):
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    statuses = {}
    combat.apply_weapon_combat_effect(_player("玄铁重剑·史诗"), statuses)
    assert statuses["armor_break"]["turns"] == 2


def test_short_blade_applies_bleed(monkeypatch):
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    statuses = {}
    combat.apply_weapon_combat_effect(_player("雾隐短刃"), statuses)
    assert statuses["bleed"] == {"turns": 2, "value": 4}


def test_missed_attack_does_not_apply_weapon_effect(monkeypatch):
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    statuses = {}
    messages = combat.apply_weapon_combat_effect(_player("玄铁重剑"), statuses, target_hit=False)
    assert messages == []
    assert statuses == {}


def test_weapons_with_no_special_effect_remain_unchanged(monkeypatch):
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    statuses = {}
    assert combat.apply_weapon_combat_effect(_player("铁剑"), statuses) == []
    assert statuses == {}


def test_weapon_effects_reference_supported_statuses():
    for name in ("玄铁重剑", "雾隐短刃", "北境巡河刀"):
        effect = engine.ITEMS[name]["weapon_effect"]
        assert effect["type"] == "status"
        assert effect["status"] in engine.STATUS_EFFECTS
        assert 0 <= effect["chance"] <= 1
