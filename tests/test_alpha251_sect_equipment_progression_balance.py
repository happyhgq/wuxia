"""Alpha251：门派武器成长、强化成本与中期战斗平衡回归。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_sect_reward_weapons_form_a_bounded_stat_and_price_tier():
    items = load("items.json")
    expected = {
        "少林戒棍": (24, 320, "armor_break"),
        "武当云纹剑": (25, 360, "stun"),
        "华山松纹剑": (26, 380, "bleed"),
    }
    for name, (atk, price, effect) in expected.items():
        item = items[name]
        assert item["type"] == "weapon"
        assert item["atk"] == atk
        assert item["price"] == price
        assert item["weapon_effect"]["status"] == effect
        assert item["enhance_max"] == 6
        assert item["enhance_ore_cost"] == 1
        assert item["enhance_gold_cost"] == 60
    # 门派奖励略高于普通铁剑、精铁剑，但没有越级压过玄铁重剑。
    assert max(items[n]["atk"] for n in expected) > items["精铁剑"]["atk"]
    assert max(items[n]["atk"] for n in expected) < items["玄铁重剑"]["atk"]


def test_signature_skills_have_distinct_roles_and_bounded_costs():
    skills = load("skills.json")
    expected = {
        "少林": ("金刚护体拳", "self_status", "shield"),
        "武当": ("绕指柔剑", "self_status", "damage_reduction"),
        "华山": ("苍松迎客剑", "combo", None),
    }
    for sect, (name, effect_type, status) in expected.items():
        skill = next(s for s in skills[sect] if s["name"] == name)
        assert 2.2 <= skill["power"] <= 2.5
        assert 25 <= skill["mp_cost"] <= 32
        assert skill["learn_min_rank"] >= 3
        assert skill["learn_min_reputation"] >= 100
        effect = skill.get("effect", {})
        assert effect["type"] == effect_type
        if status:
            assert effect["status"] == status
            assert 1 <= effect["turns"] <= 2
        else:
            assert 0.4 <= effect["chance"] <= 0.6
            assert effect["hits"] == 2
            assert 0.5 <= effect["damage_ratio"] <= 0.7


def test_enemy_equipment_and_manual_drop_rates_stay_low_and_separate():
    enemies = load("enemies.json")
    items = load("items.json")
    for name in ("黑风寨巡哨", "黑风刀手", "黑风寨精锐"):
        enemy = enemies[name]
        assert 0 < enemy["equipment_drop_chance"] <= 0.10
        for slot in ("weapon", "armor"):
            worn = enemy.get("equipment", {}).get(slot)
            assert worn in items
            assert items[worn]["type"] in ("weapon", "armor")
        manual = enemy.get("manual_drop")
        if manual:
            assert 0 < manual["chance"] <= 0.01
            assert manual["item"] in items
