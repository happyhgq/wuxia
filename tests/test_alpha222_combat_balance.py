"""Alpha222：黑风寨外围战斗强度与奖励曲线校验。"""
import json
from pathlib import Path

import combat
import engine

BASE = Path(__file__).resolve().parents[1]


def test_blackwind_enemy_base_attack_and_reward_values_are_in_line_with_difficulty():
    enemies = engine.ENEMIES
    expected = {
        "黑风寨伏击手": (9, 40, 115, 35),
        "黑风寨刀阵头目": (10, 48, 234, 60),
        "黑风寨守关首领": (11, 56, 438, 160),
    }
    for name, (level, atk, exp, gold) in expected.items():
        enemy = enemies[name]
        assert enemy["level"] == level
        assert enemy["atk"] == atk
        assert enemy["exp"] == exp
        assert enemy["gold"] == gold


def test_blackwind_combat_profiles_keep_real_attack_after_equipment_scaling():
    room_ids = {
        "黑风寨伏击手": "bandit_outer_wood",
        "黑风寨刀阵头目": "bandit_ambush_slope",
        "黑风寨守关首领": "bandit_old_beacon",
    }
    for name, room_id in room_ids.items():
        profile = combat.get_enemy_profile(name, room_id)
        assert profile["atk"] >= engine.ENEMIES[name]["atk"]
        assert profile["atk"] > 10
        assert profile["hp"] >= engine.ENEMIES[name]["hp"]
        assert profile["exp"] >= engine.ENEMIES[name]["exp"]
        assert profile["gold"] >= engine.ENEMIES[name]["gold"]


def test_blackwind_reward_curve_rises_with_level_and_boss_has_meaningful_reward():
    enemies = engine.ENEMIES
    ordered = [enemies[name] for name in ("黑风寨伏击手", "黑风寨刀阵头目", "黑风寨守关首领")]
    assert [e["exp"] for e in ordered] == sorted(e["exp"] for e in ordered)
    assert [e["gold"] for e in ordered] == sorted(e["gold"] for e in ordered)
    assert ordered[-1]["exp"] >= ordered[0]["exp"] * 2
    assert ordered[-1]["gold"] >= ordered[0]["gold"] * 2


def test_blackwind_enemy_balance_values_are_in_data_file_not_runtime_mutations():
    data = json.loads((BASE / "data" / "enemies.json").read_text(encoding="utf-8"))
    for name in ("黑风寨伏击手", "黑风寨刀阵头目", "黑风寨守关首领"):
        assert data[name]["atk"] > 0
        assert data[name]["exp"] > 0
        assert data[name]["gold"] > 0
