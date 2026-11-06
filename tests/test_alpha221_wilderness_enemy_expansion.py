"""Alpha221：黑风寨外围高难度野外路线与人形敌人配置完整性。"""
import json
from pathlib import Path
from unittest.mock import patch

import combat
import engine

BASE = Path(__file__).resolve().parents[1]


def _load(name):
    return json.loads((BASE / "data" / name).read_text(encoding="utf-8"))


def test_new_blackwind_wilderness_route_is_bidirectionally_connected():
    rooms = engine.ROOMS
    assert rooms["bandit_cliff_post"]["exits"]["东"] == "bandit_outer_wood"
    assert rooms["bandit_outer_wood"]["exits"]["西"] == "bandit_cliff_post"
    assert rooms["bandit_outer_wood"]["exits"]["北"] == "bandit_ambush_slope"
    assert rooms["bandit_ambush_slope"]["exits"]["南"] == "bandit_outer_wood"
    assert rooms["bandit_ambush_slope"]["exits"]["北"] == "bandit_old_beacon"
    assert rooms["bandit_old_beacon"]["exits"]["南"] == "bandit_ambush_slope"
    assert [rooms[x]["recommended_level"] for x in ("bandit_outer_wood", "bandit_ambush_slope", "bandit_old_beacon")] == [10, 10, 11]


def test_new_human_enemies_have_real_equipment_skills_and_low_drop_rates():
    enemies = engine.ENEMIES
    items = engine.ITEMS
    for name in ("黑风寨伏击手", "黑风寨刀阵头目", "黑风寨守关首领"):
        enemy = enemies[name]
        assert enemy["equipment"]["weapon"] in items
        assert enemy["equipment"]["armor"] in items
        assert enemy["skills"]
        assert 0 < enemy["equipment_drop_chance"] <= 0.12
        assert all(items[enemy["equipment"][slot]]["type"] == expected for slot, expected in (("weapon", "weapon"), ("armor", "armor")))
    assert items["断岳刀"]["type"] == "weapon"
    assert items["黑风寨军械残片"]["type"] == "material"


def test_all_loadout_variants_reference_valid_weapon_and_armor():
    enemies = _load("enemies.json")
    items = _load("items.json")
    count = 0
    for name, enemy in enemies.items():
        for variant in enemy.get("loadout_variants", []):
            count += 1
            equipment = variant.get("equipment", {})
            for slot, expected_type in (("weapon", "weapon"), ("armor", "armor")):
                item_name = equipment.get(slot)
                assert item_name in items, (name, slot, item_name)
                assert items[item_name].get("type") == expected_type, (name, slot, item_name)
    assert count >= 20


def test_manual_drop_rate_remains_very_low_and_capped():
    enemies = engine.ENEMIES
    for name in ("山贼大当家", "黑风寨守关首领"):
        manual = enemies[name]["manual_drop"]
        assert 0 < manual["chance"] <= 0.002
    for name in ("黑风寨刀阵头目", "黑风寨精锐", "黑风寨执法头目"):
        assert "manual_drop" not in enemies[name]


def test_profile_variant_is_snapshot_only_and_does_not_mutate_enemy_data():
    enemy = engine.ENEMIES["黑风寨伏击手"]
    original = json.dumps(enemy, ensure_ascii=False, sort_keys=True)
    with patch("combat.random.choices", return_value=[enemy["loadout_variants"][1]]):
        profile = combat.get_enemy_profile("黑风寨伏击手", "bandit_outer_wood")
    assert profile["equipment"]["weapon"] == "雾隐短刃"
    assert json.dumps(enemy, ensure_ascii=False, sort_keys=True) == original


def test_new_enemy_reward_drops_do_not_use_high_frequency_equipment_entries():
    enemies = engine.ENEMIES
    for name in ("黑风寨伏击手", "黑风寨刀阵头目", "黑风寨守关首领"):
        enemy = enemies[name]
        assert all(engine.ITEMS.get(row.get("item"), {}).get("type") not in ("weapon", "armor") for row in enemy.get("drops", []))
        # 守关首领的军械残片已改为保底 1 件 + 50% 额外 1 件；保底掉落不受概率上限约束。
        assert all(row.get("guaranteed") or row.get("chance", 0) <= 0.5 for row in enemy.get("drops", []))
