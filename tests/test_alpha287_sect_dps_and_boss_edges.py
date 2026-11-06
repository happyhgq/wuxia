# -*- coding: utf-8 -*-
"""Alpha287：铁衣门输出校准与 Boss 边缘胜率面板回归。"""
import json
from pathlib import Path

import engine

ROOT = Path(__file__).resolve().parents[1]

IRON_SKILLS = {
    "铁衣功": {
        "mp_cost": 10,
        "power": 1.25,
        "level": 3,
        "effect": {
            "type": "self_status",
            "status": "damage_reduction",
            "chance": 1.0,
            "turns": 2,
            "value": 18,
        },
        "mastery_power_per_level": 0.025,
    },
    "破阵刀": {
        "mp_cost": 20,
        "power": 2.45,
        "level": 4,
        "effect": {
            "type": "status",
            "status": "armor_break",
            "chance": 0.45,
            "turns": 2,
            "value": 3,
        },
        "mastery_power_per_level": 0.035,
    },
}

BOSS_EDGE_PANELS = {
    "山贼二当家": (423, 38, 12, 264, 110),
    "山贼大当家": (545, 49, 16, 390, 240),
    "黑风寨守关首领": (710, 56, 18, 438, 160),
    "黑市头目": (725, 61, 20, 489, 160),
}


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_alpha287_iron_sect_skills_keep_effects_and_raise_power():
    skills = {sk["name"]: sk for sk in _data("skills.json")["铁衣门"]}
    for name, expected in IRON_SKILLS.items():
        skill = skills[name]
        for key, value in expected.items():
            assert skill[key] == value, (name, key, skill[key], value)


def test_alpha287_iron_sect_top_power_matches_peer_sects():
    data = _data("skills.json")
    top = {}
    for sect in ("少林", "武当", "华山", "铁衣门"):
        top[sect] = max(float(sk.get("power", 0)) for sk in data[sect])
    assert top == {"少林": 2.75, "武当": 2.55, "华山": 2.7, "铁衣门": 2.65}
    peers = (top["少林"], top["武当"], top["铁衣门"])
    assert max(peers) - min(peers) <= 0.35


def test_alpha287_boss_edge_panels_only_change_hp_atk_defense():
    for name, expected in BOSS_EDGE_PANELS.items():
        enemy = engine.ENEMIES[name]
        actual = (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"], enemy["gold"])
        assert actual == expected, (name, actual, expected)


def test_alpha287_boss_drops_are_unchanged():
    enemies = engine.ENEMIES
    assert enemies["山贼大当家"]["drops"] == [{"item": "大还丹", "chance": 0.8, "guaranteed": True}]
    assert enemies["黑风寨守关首领"]["drops"] == [
        {"item": "黑风寨军械残片", "chance": 1.0, "guaranteed": True, "quantity": 1},
        {"item": "黑风寨军械残片", "chance": 0.5, "quantity": 1},
    ]
    assert enemies["黑市头目"]["drops"] == [{"item": "大还丹", "chance": 0.55, "guaranteed": True}]
