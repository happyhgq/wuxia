# -*- coding: utf-8 -*-
"""Alpha286：Boss 胜率校准、高等级普通怪生命微调与击杀任务经验回归。"""
import json
from pathlib import Path

import combat
import engine

ROOT = Path(__file__).resolve().parents[1]

ALPHA286_NORMALS = {
    "劫镖山贼": (255, 36, 11, 101, 35),
    "黑风寨伏击手": (285, 40, 12, 115, 35),
    "黑风寨游骑": (310, 44, 13, 130, 58),
    "黑风寨悍卒": (335, 48, 14, 146, 66),
    "黑市死士": (345, 52, 15, 163, 82),
}

# Alpha287 再次校准后保持的最终面板。
ALPHA286_BOSSES = {
    "山贼大当家": (545, 49, 16, 390, 240),
    "黑风寨守关首领": (710, 56, 18, 438, 160),
    "黑市头目": (725, 61, 20, 489, 160),
}

ALPHA286_UNCHANGED_BOSSES = {
    "山贼二当家": (423, 38, 12, 264, 110),
}

ALPHA286_QUEST_EXP = {
    "少林历练·黑风除恶": 292,
    "武当历练·以静制动": 292,
    "华山历练·磨剑黑风": 292,
    "少林历练·巡山护戒": 292,
    "武当历练·松径清扰": 292,
    "铁衣门历练·清除巡哨": 292,
    "铁衣门历练·护路除匪": 162,
    "清剿黑风山": 228,
    "华山历练·险道试剑": 188,
}

KILL_QUEST_COMBAT_BASELINE = {
    "新手狩猎·野外除害": ("野猪", "official_road", 1),
    "村道巡查·清理残匪": ("山贼", "bandit_courtyard", 2),
    "铁脉清障·深处探矿": ("铁背矿獾", "deep_iron_gallery", 2),
    "沉河旧商队遗证": ("遗祠守墓人", "sunken_shrine", 1),
    "雾溪除蛛·护药浅滩": ("迷雾毒蛛", "mistwood_stream", 2),
    "黑风限时追缉": ("山贼", "bandit_courtyard", 2),
    "华山历练·险道试剑": ("黑风寨刀阵头目", "bandit_outer_wood", 1),
    "清剿黑风山": ("山贼二当家", "bandit_camp", 1),
    "少林历练·黑风除恶": ("黑风寨精锐", "bandit_treasury", 2),
    "武当历练·以静制动": ("黑风寨精锐", "bandit_treasury", 2),
    "华山历练·磨剑黑风": ("黑风寨精锐", "bandit_treasury", 2),
    "少林历练·巡山护戒": ("黑风寨精锐", "bandit_treasury", 2),
    "武当历练·松径清扰": ("黑风寨精锐", "bandit_treasury", 2),
    "铁衣门历练·清除巡哨": ("黑风寨精锐", "bandit_treasury", 2),
    "铁衣门历练·护路除匪": ("劫镖山贼", "guiyun_dart_yard", 2),
}


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_alpha286_normal_hp_tuning_keeps_all_non_hp_values():
    enemies = engine.ENEMIES
    for name, (hp, atk, defense, exp, gold) in ALPHA286_NORMALS.items():
        enemy = enemies[name]
        assert enemy["tier"] in ("normal", "ranged")
        assert (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"], enemy["gold"]) == (hp, atk, defense, exp, gold)


def test_alpha286_boss_tuning_keeps_defense_exp_gold_and_drops():
    enemies = engine.ENEMIES
    for name, (hp, atk, defense, exp, gold) in ALPHA286_BOSSES.items():
        enemy = enemies[name]
        assert (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"], enemy["gold"]) == (hp, atk, defense, exp, gold)

    assert enemies["山贼大当家"]["drops"] == [{"item": "大还丹", "chance": 0.8, "guaranteed": True}]
    assert enemies["黑风寨守关首领"]["drops"] == [
        {"item": "黑风寨军械残片", "chance": 1.0, "guaranteed": True, "quantity": 1},
        {"item": "黑风寨军械残片", "chance": 0.5, "quantity": 1},
    ]

    for name, expected in ALPHA286_UNCHANGED_BOSSES.items():
        enemy = enemies[name]
        assert (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"], enemy["gold"]) == expected


def test_alpha286_tuned_normal_drops_are_unchanged():
    enemies = engine.ENEMIES
    assert enemies["劫镖山贼"]["drops"] == [
        {"item": "铁矿石", "chance": 0.55},
        {"item": "金创药", "chance": 0.2},
    ]
    assert enemies["黑风寨伏击手"]["drops"] == [
        {"item": "黑风寨军械残片", "chance": 0.2, "min_qty": 1, "max_qty": 2},
    ]
    assert enemies["黑风寨游骑"]["drops"] == [
        {"item": "黑风寨军械残片", "chance": 0.2, "min_qty": 1, "max_qty": 2},
        {"item": "金创药", "chance": 0.15},
    ]
    assert enemies["黑风寨悍卒"]["drops"] == [
        {"item": "黑风寨军械残片", "chance": 0.25},
        {"item": "金创药", "chance": 0.18},
    ]
    assert enemies["黑市死士"]["drops"] == [
        {"item": "大还丹", "chance": 0.12},
        {"item": "铁矿石", "chance": 0.3},
    ]


def test_alpha286_nine_kill_quest_rewards_are_applied():
    quests = _data("quests.json")
    for name, exp in ALPHA286_QUEST_EXP.items():
        assert quests[name]["reward"]["exp"] == exp, name

    assert quests["铁衣门历练·护路除匪"]["repeat_reward"] == {"exp": 40, "gold": 22}


def test_alpha286_kill_quest_exp_matches_actual_room_profile_combat_exp():
    quests = _data("quests.json")
    for name, (target, room_id, count) in KILL_QUEST_COMBAT_BASELINE.items():
        quest = quests[name]
        profile = combat.get_enemy_profile(target, room_id)
        combat_exp = profile["exp"] * count
        ratio = quest["reward"]["exp"] / combat_exp
        assert 0.8 <= ratio <= 1.2, (name, quest["reward"]["exp"], combat_exp, ratio)


def test_alpha286_total_quest_exp_reaches_level_14_threshold():
    quests = _data("quests.json")
    total = sum(info["reward"].get("exp", 0) for info in quests.values())
    assert total == 11654
    assert total > 8955
