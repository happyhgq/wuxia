# -*- coding: utf-8 -*-
"""Alpha285：等级曲线、怪物模板、区域难度兜底、守势减伤与任务经验回归。"""
import builtins
import copy
import json
from pathlib import Path

import combat
import engine
import world_lifecycle
from player import LEVEL_EXP_TABLE, Player, exp_needed_for_level

ROOT = Path(__file__).resolve().parents[1]

OLD_LEVEL_EXP_TABLE = (60, 85, 115, 150, 195, 250, 320, 410, 520, 650, 1100, 1500, 2000, 2650, 3500)

NORMAL_TEMPLATE = {
    1: (55, 9, 2, 30),
    2: (72, 12, 4, 38),
    3: (100, 16, 5, 46),
    4: (130, 20, 6, 55),
    5: (165, 24, 8, 65),
    6: (200, 28, 9, 76),
    7: (235, 32, 10, 88),
    8: (270, 36, 11, 101),
    9: (300, 40, 12, 115),
    10: (330, 44, 13, 130),
    11: (360, 48, 14, 146),
    12: (390, 52, 15, 163),
    13: (420, 56, 16, 181),
    14: (450, 60, 17, 200),
    15: (480, 64, 18, 220),
}

# Alpha286：攻击/防御/经验保持不变，仅下调高等级普通怪生命，使同级基础攻击回合数回到 7 以内。
ALPHA286_NORMAL_OVERRIDES = {
    "劫镖山贼": (255, 36, 11, 101),
    "黑风寨伏击手": (285, 40, 12, 115),
    "黑风寨游骑": (310, 44, 13, 130),
    "黑风寨悍卒": (335, 48, 14, 146),
    "黑市死士": (345, 52, 15, 163),
}

# Alpha286：Boss 基础攻击胜率校准，经验与掉落保持不变。
ALPHA286_BOSS_OVERRIDES = {
    "山贼大当家": (535, 49, 16, 390),
    "黑风寨守关首领": (710, 57, 18, 438),
}

# Alpha287：Boss 边缘胜率复校，仅调整生命/攻击/防御，经验与掉落不变。
ALPHA287_BOSS_OVERRIDES = {
    "山贼大当家": (545, 49, 16, 390),
    "黑风寨守关首领": (710, 56, 18, 438),
    "黑市头目": (725, 61, 20, 489),
}

# Alpha316：L15 五门派实战复核后微调断魂堡主，经验与掉落不变。
ALPHA316_BOSS_OVERRIDES = {
    "断魂堡主": (920, 80, 23, 660),
}

# Alpha286：击杀任务的实战经验按目标实际房间档位计算，比例为任务经验 ÷（单只实际经验 × 数量）。
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
    "黑风旧卒·外林查哨": ("黑风寨伏击手", "bandit_outer_wood", 3),
    "沉河·闸口除傀": ("沉河尸傀", "sunken_sluice", 3),
}


def _expected_stats(level, tier):
    hp, atk, defense, exp = NORMAL_TEMPLATE[level]
    if tier == "elite":
        return round(hp * 1.4), round(atk * 1.1), round(defense * 1.25), round(exp * 1.8)
    if tier == "boss":
        return round(hp * 1.8), round(atk * 1.18), round(defense * 1.25), round(exp * 3.0)
    return hp, atk, defense, exp


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_level_curve_is_alpha285_values_and_never_below_legacy_requirements():
    assert LEVEL_EXP_TABLE == (150, 185, 225, 275, 335, 410, 500, 610, 745, 910, 1110, 1500, 2000, 2650, 3500)
    assert all(new >= old for new, old in zip(LEVEL_EXP_TABLE, OLD_LEVEL_EXP_TABLE))
    assert LEVEL_EXP_TABLE[11:] == OLD_LEVEL_EXP_TABLE[11:]
    assert exp_needed_for_level(1) == 150
    assert exp_needed_for_level(9) == 745
    assert exp_needed_for_level(12) == 1500
    assert exp_needed_for_level(15) == 3500
    assert exp_needed_for_level(16) == 4725


def test_legacy_l9_save_keeps_level_and_recalculates_progress(tmp_path):
    raw = {
        "version": 12,
        "name": "L9存档确认",
        "sect": "散人",
        "level": 9,
        "exp": 240,
        "exp_to_level": 520,
        "max_hp": 220,
        "hp": 220,
        "max_mp": 130,
        "mp": 130,
        "atk": 34,
        "defense": 21,
        "gold": 500,
        "inventory": [],
        "equipment": {"weapon": None, "armor": None},
        "location": "village_square",
        "active_quests": {},
        "completed_quests": [],
    }
    path = tmp_path / "alpha285_l9.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.level == 9
    assert loaded.exp == 240
    assert loaded.exp_to_level == 745
    assert round(loaded.exp / loaded.exp_to_level * 100, 1) == 32.2


def test_normal_enemy_template_covers_every_level_and_keeps_equipment_variants():
    enemies = engine.ENEMIES
    for level, expected in NORMAL_TEMPLATE.items():
        matches = [
            name for name, enemy in enemies.items()
            if enemy.get("tier") in ("normal", "ranged") and int(enemy.get("level", 0)) == level
            and (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"])
            in (expected, ALPHA286_NORMAL_OVERRIDES.get(name))
        ]
        assert matches, level

    for name, enemy in enemies.items():
        tier = enemy.get("tier")
        if tier not in ("normal", "ranged"):
            continue
        level = int(enemy.get("level", 0))
        if level not in NORMAL_TEMPLATE:
            continue
        expected = ALPHA286_NORMAL_OVERRIDES.get(name, _expected_stats(level, tier))
        actual = (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"])
        assert actual == expected, (name, actual, expected)

    assert enemies["黑风寨游骑"]["loadout_variants"]
    assert enemies["山贼"]["loadout_variants"]


def test_elite_and_boss_templates_apply_approved_multipliers():
    for name, enemy in engine.ENEMIES.items():
        tier = enemy.get("tier")
        if tier not in ("elite", "boss"):
            continue
        actual = (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"])
        expected = (
            ALPHA316_BOSS_OVERRIDES.get(name)
            or ALPHA287_BOSS_OVERRIDES.get(name)
            or ALPHA286_BOSS_OVERRIDES.get(name)
            or _expected_stats(int(enemy["level"]), tier)
        )
        assert actual == expected, (name, actual, expected)


def test_l10_to_l12_have_normal_enemies_placed_in_rooms():
    rooms = engine.ROOMS
    for level in (10, 11, 12):
        names = [
            name for name, enemy in engine.ENEMIES.items()
            if enemy.get("tier") == "normal" and int(enemy.get("level", 0)) == level
        ]
        assert names, level
        for name in names:
            assert any(name in room.get("enemies", []) for room in rooms.values()), name

    l10 = combat.get_enemy_profile("黑风寨游骑", "bandit_outer_wood")
    l11 = combat.get_enemy_profile("黑风寨悍卒", "bandit_old_beacon")
    l12 = combat.get_enemy_profile("黑市死士", "guiyun_black_market_hall")
    assert (l10["level"], l11["level"], l12["level"]) == (10, 11, 12)


def test_rooms_without_difficulty_level_fall_back_to_recommended_level():
    fallbacks = {
        "mistwood_trail": ("雾林野猿", 4),
        "mistwood_stream": ("迷雾毒蛛", 5),
        "sunken_stairs": ("沉河尸傀", 6),
        "sunken_shrine": ("遗祠守墓人", 7),
        "sunken_channel": ("沉河尸傀", 6),
        "northfront_wharf": ("北境劫货客", 8),
        "abandoned_iron_mine": ("雾林野猿", 4),
        "bamboo_hollow": ("雾林野猿", 4),
        "old_woodlot": ("野狼", 2),
        "deep_iron_gallery": ("雾林野猿", 5),
        "collapsed_quarry": ("雾林野猿", 5),
        "herb_springbank": ("迷雾毒蛛", 5),
        "rocky_herb_slope": ("野猪", 4),
        "pine_ridge_foot": ("野狼", 2),
        "cloud_stack_road": ("野猪", 3),
        "songshan_pine_path": ("野猪", 3),
        "mistwood_ridge_path": ("山贼精英", 7),
    }
    rooms = engine.ROOMS
    missing = [rid for rid, room in rooms.items() if room.get("enemies") and not room.get("difficulty_level")]
    assert set(missing) == set(fallbacks)

    for room_id, (enemy_name, recommended) in fallbacks.items():
        room = rooms[room_id]
        assert room["recommended_level"] == recommended
        profile = combat.get_enemy_profile(enemy_name, room_id)
        base_level = int(engine.ENEMIES[enemy_name]["level"])
        assert profile["difficulty_level"] == recommended
        assert profile["level"] == max(base_level, recommended)


def test_guard_reduction_survives_status_tick_and_applies_to_next_player_attack():
    statuses = {}
    engine.add_status(statuses, "damage_reduction", 2, 25)
    engine.process_status_effects(statuses)
    assert "damage_reduction" in statuses
    assert engine.apply_damage_reduction(statuses, 100) == 75
    engine.process_status_effects(statuses)
    assert "damage_reduction" not in statuses


class _GuardPlayer:
    def __init__(self):
        self.name = "守势测试侠客"
        self.hp = 500
        self.max_hp = 500
        self.mp = 100
        self.max_mp = 100
        self.location = "test_room"
        self.inventory = []
        self.saved = False

    def get_total_atk(self):
        return 50

    def get_total_defense(self):
        return 0

    def get_available_skills(self):
        return []

    def update_quest_progress(self, name):
        return None

    def save_to_file(self, *args, **kwargs):
        self.saved = True


def _guard_enemy():
    return {
        "name": "守势傀儡",
        "hp": 500,
        "atk": 0,
        "defense": 0,
        "level": 1,
        "tier": "normal",
        "tier_label": "普通",
        "skills": [],
        "phases": [],
        "exp": 0,
        "gold": 0,
        "drops": [],
    }


def test_combat_guard_branch_reduces_basic_attack_damage(monkeypatch, capsys):
    player = _GuardPlayer()
    monkeypatch.setattr(combat, "get_enemy_profile", lambda *args, **kwargs: copy.deepcopy(_guard_enemy()))
    monkeypatch.setattr(combat, "apply_world_combat_pressure", lambda *args, **kwargs: 0)
    monkeypatch.setattr(combat, "_player_combat_stats", lambda *args, **kwargs: (1.0, 0.0, 0.0))
    monkeypatch.setattr(combat, "resolve_attack", lambda *args, **kwargs: (25, "hit"))
    monkeypatch.setattr(combat, "choose_enemy_action", lambda *args, **kwargs: {"action": "guard", "reduction": 25})
    monkeypatch.setattr(combat, "apply_weapon_combat_effect", lambda *args, **kwargs: [])
    monkeypatch.setattr(combat, "battle_pause", lambda *args, **kwargs: None)
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    monkeypatch.setattr("world_lifecycle.entity_state", lambda *args, **kwargs: ("alive", None))

    feed = iter(["1", "1", "4"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(feed))

    combat.combat(player, "守势傀儡")
    output = capsys.readouterr().out

    assert "你挥舞兵刃发起攻击，造成 25 点伤害！" in output
    assert "你挥舞兵刃发起攻击，造成 18 点伤害！" in output
    assert "下次受到的伤害降低 25%" in output


def test_kill_quest_exp_matches_report_baseline_combat_exp_ratio():
    quests = _data("quests.json")
    for name, (target, room_id, count) in KILL_QUEST_COMBAT_BASELINE.items():
        quest = quests[name]
        assert quest["target_type"] == "kill"
        assert quest["target_name"] == target
        assert quest["required_cnt"] == count
        profile = combat.get_enemy_profile(target, room_id)
        combat_exp = profile["exp"] * count
        ratio = quest["reward"]["exp"] / combat_exp
        assert 0.8 <= ratio <= 1.2, (name, quest["reward"]["exp"], combat_exp, ratio)


def test_non_kill_quest_exp_stays_inside_tier_bands():
    quests = _data("quests.json")
    bands = {
        "入门": (60, 90),
        "普通": (90, 150),
        "进阶": (150, 240),
        "高难": (220, 330),
        "重大": (330, 490),
    }
    for name, info in quests.items():
        if info.get("target_type") == "kill":
            continue
        # Alpha291 的素材兑换任务只回收断魂精铁换取药品与银两，不发放经验，
        # 因此不参与非击杀任务的经验区间校验。
        if "exp" not in info["reward"]:
            continue
        low, high = bands[info["difficulty"]]
        assert low <= info["reward"]["exp"] <= high, (name, info["reward"]["exp"])


def test_boss_respawn_and_save_version_contract_are_unchanged():
    assert engine.SAVE_VERSION == 12
    assert world_lifecycle.BOSS_SECONDS == 300
    assert world_lifecycle.BOSS_CORPSE_SECONDS == 120
