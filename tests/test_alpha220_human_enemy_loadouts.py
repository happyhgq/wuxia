"""Alpha220：人形敌人装备、低爆率装备掉落、秘籍习得与黑风寨难度梯度。"""
from unittest.mock import patch

import combat
import engine
from actions import apply_consumable
from player import Player


def test_human_enemy_loadout_uses_existing_item_data_and_affects_stats():
    base = engine.ENEMIES["山贼头目"]
    assert base["equipment"]["weapon"] in engine.ITEMS
    assert base["equipment"]["armor"] in engine.ITEMS
    profile = combat.get_enemy_profile("山贼头目", "bandit_courtyard")
    assert profile["equipment"]["weapon"] in engine.ITEMS
    assert profile["equipment"]["armor"] in engine.ITEMS
    assert profile["equipment_bonus"]["atk"] > 0
    assert profile["equipment_bonus"]["defense"] > 0
    # 生成当前战斗配置不应修改静态敌人定义。
    assert base["equipment"]["weapon"] == "铁剑"


def test_equipment_drop_is_low_probability_and_capped_to_one_worn_item():
    enemy = {
        "exp": 1, "gold": 1,
        "equipment": {"weapon": "铁剑", "armor": "皮甲"},
        "equipment_drop_chance": 1.0,
        "drops": [{"item": "草药", "chance": 0.0}],
    }
    with patch("combat.random.random", side_effect=[0.9, 0.0]), patch("combat.random.choice", return_value="皮甲"):
        reward = combat.resolve_enemy_rewards(enemy)
    gear = [row for row in reward["drops"] if engine.ITEMS[row["item"]].get("type") in ("weapon", "armor")]
    assert gear == [{"item": "皮甲", "quantity": 1}]


def test_normal_human_enemy_does_not_drop_gear_when_roll_fails():
    enemy = dict(engine.ENEMIES["山贼"])
    with patch("combat.random.random", return_value=0.99):
        reward = combat.resolve_enemy_rewards(enemy)
    assert not any(engine.ITEMS.get(row["item"], {}).get("type") in ("weapon", "armor") for row in reward["drops"])


def test_manual_teaches_skill_and_consumes_only_on_success():
    p = Player("秘籍测试", "少林")
    p.level = 5
    p.inventory.append("黑风刀法秘笈")
    assert apply_consumable(p, "黑风刀法秘笈") is True
    assert "黑风刀法秘笈" not in p.inventory
    assert p.get_skill_progress("黑风刀法")["learned"] is True
    assert any(x["name"] == "黑风刀法" for x in p.get_available_skills())


def test_manual_level_gate_does_not_consume_item():
    p = Player("低级秘籍测试", "散人")
    p.level = 1
    p.inventory.append("黑风刀法秘笈")
    assert apply_consumable(p, "黑风刀法秘笈") is False
    assert "黑风刀法秘笈" in p.inventory


def test_blackwind_expansion_has_connected_level_8_to_9_path():
    rooms = engine.ROOMS
    assert rooms["bandit_treasury"]["exits"]["东"] == "bandit_supply_cave"
    assert rooms["bandit_supply_cave"]["exits"]["西"] == "bandit_treasury"
    assert rooms["bandit_supply_cave"]["exits"]["北"] == "bandit_cliff_post"
    assert rooms["bandit_cliff_post"]["exits"]["南"] == "bandit_supply_cave"
    assert rooms["bandit_supply_cave"]["recommended_level"] == 8
    assert rooms["bandit_cliff_post"]["recommended_level"] == 9
    assert "黑风寨执法头目" in rooms["bandit_cliff_post"]["enemies"]
