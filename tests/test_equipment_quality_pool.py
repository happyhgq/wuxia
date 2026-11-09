# -*- coding: utf-8 -*-
"""装备品质池接入：穿戴装备掉落命中后按品质池解析为变体。"""
from unittest.mock import patch

import combat
import engine

QUALITY_HOLDERS = {
    "山贼头目": {"精良"},
    "山贼二当家": {"精良", "稀有"},
    "宝库大总管": {"精良", "稀有"},
    "山贼大当家": {"稀有", "史诗"},
    "黑市护卫": {"精良", "稀有"},
    "黑风寨守关首领": {"精良", "稀有"},
    "黑市头目": {"稀有", "史诗"},
    "断魂堡死卫": {"精良", "稀有"},
}


def _worn_variant_items(enemy):
    equipment = enemy.get("equipment") or {}
    worn = [equipment.get(slot) for slot in ("weapon", "armor") if equipment.get(slot) in engine.ITEMS]
    return [item for item in worn if engine.ITEMS[item].get("quality_variants")]


def test_only_designated_enemies_carry_equipment_quality_pool():
    holders = {name for name, enemy in engine.ENEMIES.items() if enemy.get("equipment_quality_pool")}
    assert holders == set(QUALITY_HOLDERS)
    for name, qualities in QUALITY_HOLDERS.items():
        enemy = engine.ENEMIES[name]
        pool = enemy["equipment_quality_pool"]
        assert {entry["quality"] for entry in pool} == qualities, name
        assert 0 < enemy["equipment_drop_chance"] <= 0.25, name
        total = sum(entry["chance"] for entry in pool)
        assert 0 < total <= 1.0, name
        assert _worn_variant_items(enemy), name


def test_enemy_profile_keeps_quality_pool_for_combat():
    profile = combat.get_enemy_profile("山贼二当家", "bandit_courtyard")
    assert profile["equipment_quality_pool"] == engine.ENEMIES["山贼二当家"]["equipment_quality_pool"]
    assert "loadout_variants" not in profile


def test_worn_gear_drop_resolves_declared_quality_variant():
    enemy = {
        "exp": 1,
        "gold": 1,
        "equipment": {"weapon": "精铁剑", "armor": "锁子甲"},
        "equipment_drop_chance": 1.0,
        "equipment_quality_pool": [
            {"quality": "精良", "chance": 0.5},
            {"quality": "史诗", "chance": 0.1},
        ],
    }
    with patch("combat.random.random", side_effect=[0.0, 0.2]), \
            patch("combat.random.choice", return_value="精铁剑"):
        rewards = combat.resolve_enemy_rewards(enemy)
    assert rewards["drops"] == [{"item": "精铁剑·精良", "quantity": 1}]


def test_quality_pool_hits_later_tier_when_first_entry_misses():
    enemy = {
        "exp": 1,
        "gold": 1,
        "equipment": {"weapon": "精铁剑", "armor": "锁子甲"},
        "equipment_drop_chance": 1.0,
        "equipment_quality_pool": [
            {"quality": "精良", "chance": 0.5},
            {"quality": "史诗", "chance": 0.1},
        ],
    }
    with patch("combat.random.random", side_effect=[0.0, 0.55]), \
            patch("combat.random.choice", return_value="锁子甲"):
        rewards = combat.resolve_enemy_rewards(enemy)
    assert rewards["drops"] == [{"item": "锁子甲·史诗", "quantity": 1}]


def test_quality_pool_miss_keeps_base_gear():
    enemy = {
        "exp": 1,
        "gold": 1,
        "equipment": {"weapon": "精铁剑", "armor": "锁子甲"},
        "equipment_drop_chance": 1.0,
        "equipment_quality_pool": [{"quality": "精良", "chance": 0.3}],
    }
    with patch("combat.random.random", side_effect=[0.0, 0.9]), \
            patch("combat.random.choice", return_value="精铁剑"):
        rewards = combat.resolve_enemy_rewards(enemy)
    assert rewards["drops"] == [{"item": "精铁剑", "quantity": 1}]


def test_worn_item_without_variants_stays_base_even_on_pool_hit():
    enemy = {
        "exp": 1,
        "gold": 1,
        "equipment": {"weapon": "苍脊刀", "armor": "锁子甲"},
        "equipment_drop_chance": 1.0,
        "equipment_quality_pool": [{"quality": "精良", "chance": 1.0}],
    }
    with patch("combat.random.random", side_effect=[0.0, 0.0]), \
            patch("combat.random.choice", return_value="苍脊刀"):
        rewards = combat.resolve_enemy_rewards(enemy)
    assert rewards["drops"] == [{"item": "苍脊刀", "quantity": 1}]


def test_enemy_without_pool_keeps_plain_worn_gear():
    enemy = {
        "exp": 1,
        "gold": 1,
        "equipment": {"weapon": "精铁剑", "armor": "锁子甲"},
        "equipment_drop_chance": 1.0,
    }
    with patch("combat.random.random", side_effect=[0.0]), \
            patch("combat.random.choice", return_value="精铁剑"):
        rewards = combat.resolve_enemy_rewards(enemy)
    assert rewards["drops"] == [{"item": "精铁剑", "quantity": 1}]


def test_failed_gear_roll_never_consumes_quality_roll():
    enemy = {
        "exp": 1,
        "gold": 1,
        "equipment": {"weapon": "精铁剑", "armor": "锁子甲"},
        "equipment_drop_chance": 0.1,
        "equipment_quality_pool": [{"quality": "史诗", "chance": 1.0}],
    }
    with patch("combat.random.random", side_effect=[0.9]):
        rewards = combat.resolve_enemy_rewards(enemy)
    assert rewards["drops"] == []
