# -*- coding: utf-8 -*-
"""Alpha283 成长修订：伤害、经验、衰减、首领、新任务与 V12 回归。"""
import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import combat
import engine
from actions import _quest_notice_clues, handle_quest
from player import LEVEL_EXP_TABLE, Player, exp_needed_for_level

BASE = Path(__file__).resolve().parents[1]
NEW_QUEST = "药囊递送·雾林问诊"


def capture(fn, *args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        fn(*args)
    return output.getvalue()


def test_percentage_damage_formula_keeps_defense_meaningful_without_zero_damage():
    assert combat.calculate_damage(50, 5) == 47
    assert combat.calculate_damage(50, 8) == 46
    assert combat.calculate_damage(10, 0) == 10
    assert combat.calculate_damage(10, 100) == 5
    assert combat.calculate_damage(10, 100, 2.0) == 10
    # 极低攻击或极高防御仍保留最低 1 点伤害，不会把战斗锁死。
    assert combat.calculate_damage(0, 0) == 1
    assert combat.calculate_damage(10, 100000) == 1


def test_staged_exp_curve_and_level_up_apply_table_values():
    assert LEVEL_EXP_TABLE[:5] == (150, 185, 225, 275, 335)
    assert exp_needed_for_level(1) == 150
    assert exp_needed_for_level(15) == 3500
    assert exp_needed_for_level(16) == int(3500 * 1.35)

    p = Player("经验曲线回归", "散人")
    capture(p.gain_exp, exp_needed_for_level(1))
    assert p.level == 2
    assert p.exp == 0
    assert p.exp_to_level == 185
    assert (p.max_hp, p.max_mp, p.atk, p.defense, p.attribute_points) == (115, 60, 13, 7, 3)


def test_normalize_exp_progress_handles_legacy_curve_overflow():
    p = Player("旧曲线重算", "散人")
    p.level = 2
    p.exp = 200
    p.exp_to_level = 999
    p.normalize_exp_progress()
    assert p.level == 3
    assert p.exp == 15
    assert p.exp_to_level == 225


def test_v12_load_recalculates_legacy_exp_threshold_without_schema_change(tmp_path):
    p = Player("旧档经验迁移", "散人")
    path = tmp_path / "legacy_exp.json"
    capture(p.save_to_file, str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["level"] = 2
    raw["exp"] = 200
    raw["exp_to_level"] = 999
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.level == 3
    assert loaded.exp == 15
    assert loaded.exp_to_level == 225
    assert raw["version"] == engine.SAVE_VERSION == 12


def test_low_level_enemy_experience_decay_thresholds_and_floor():
    assert combat.experience_decay_multiplier(5, 3) == 1.0
    assert combat.experience_decay_multiplier(6, 3) == 0.70
    assert combat.experience_decay_multiplier(8, 3) == 0.45
    assert combat.experience_decay_multiplier(10, 3) == 0.25
    assert combat.experience_decay_multiplier(13, 3) == 0.10

    p = Player("经验衰减回归", "散人")
    p.level = 8
    rewards = {"exp": 100, "gold": 10}
    adjusted = combat.apply_experience_decay(rewards, p, {"level": 3})
    assert adjusted["exp"] == 45
    assert adjusted["gold"] == 10
    assert rewards["exp"] == 100
    assert combat.apply_experience_decay({"exp": 1}, p, {"level": 3})["exp"] == 1


def test_boss_values_and_guaranteed_drops_match_growth_revision():
    expected = {
        "山贼二当家": (423, 38, 264, 110),
        "山贼大当家": (545, 49, 390, 240),
        "黑风寨守关首领": (710, 56, 438, 160),
        "黑市头目": (725, 61, 489, 160),
    }
    for name, (hp, atk, exp, gold) in expected.items():
        enemy = engine.ENEMIES[name]
        assert (enemy["hp"], enemy["atk"], enemy["exp"], enemy["gold"]) == (hp, atk, exp, gold)

    with patch("combat.random.random", return_value=0.99):
        second = combat.resolve_enemy_rewards(engine.ENEMIES["山贼二当家"])
        guard = combat.resolve_enemy_rewards(engine.ENEMIES["黑风寨守关首领"])
        black_market = combat.resolve_enemy_rewards(engine.ENEMIES["黑市头目"])
    assert any(drop["item"] == "金创药" and drop["quantity"] == 1 for drop in second["drops"])
    assert not any(drop["item"] == "铁矿石" for drop in second["drops"])
    assert [(drop["item"], drop["quantity"]) for drop in guard["drops"]] == [("黑风寨军械残片", 1)]
    assert isinstance(black_market["drops"], list)


def test_new_quest_requires_level_and_two_prerequisites():
    p = Player("药囊接取验收", "散人")
    p.location = "medicine_shop"
    p.completed_quests.extend(["村道回暖·药铺复业", "新手采药·认识资源"])
    p.level = 1
    blocked = capture(handle_quest, p, "jiequ", [NEW_QUEST])
    assert "接取失败" in blocked
    assert "2" in blocked
    assert NEW_QUEST not in p.active_quests

    p.level = 2
    accepted = capture(handle_quest, p, "jiequ", [NEW_QUEST])
    assert "已接取任务" in accepted
    assert p.active_quests[NEW_QUEST] == 0


def test_new_quest_collect_delivery_and_wrong_npc_rejection(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    p = Player("药囊交付验收", "散人")
    p.level = 2
    p.location = "medicine_shop"
    p.completed_quests.extend(["村道回暖·药铺复业", "新手采药·认识资源"])
    assert "已接取任务" in capture(handle_quest, p, "jiequ", [NEW_QUEST])

    p.update_quest_progress("草药", event_type="collect")
    p.update_quest_progress("草药", event_type="collect")
    assert p.active_quests[NEW_QUEST] == 2
    p.inventory.extend(["草药", "草药"])
    before_herbs = p.inventory.count("草药")

    wrong = capture(handle_quest, p, "jiaofu", [NEW_QUEST])
    assert "请回到【采药人阿芷】处交付任务" in wrong
    assert NEW_QUEST in p.active_quests

    p.location = "mistwood_trail"
    completed = capture(handle_quest, p, "jiaofu", [NEW_QUEST])
    assert "奖励已结算" in completed
    assert NEW_QUEST in p.completed_quests
    assert p.inventory.count("草药") == before_herbs - 2

    gold_before = p.gold
    duplicate = capture(handle_quest, p, "jiaofu", [NEW_QUEST])
    assert "已经完成" in duplicate or "不能重复" in duplicate or "未接取" in duplicate
    assert p.gold == gold_before


def test_new_quest_active_progress_survives_v12_round_trip(tmp_path):
    p = Player("药囊存档验收", "散人")
    p.level = 2
    p.location = "medicine_shop"
    p.completed_quests.extend(["村道回暖·药铺复业", "新手采药·认识资源"])
    assert "已接取任务" in capture(handle_quest, p, "jiequ", [NEW_QUEST])
    p.update_quest_progress("草药", event_type="collect")

    path = tmp_path / "new_quest_active.json"
    capture(p.save_to_file, str(path))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION == 12

    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.active_quests[NEW_QUEST] == 1
    assert NEW_QUEST not in loaded.completed_quests


def test_difficulty_distribution_and_notice_filter_follow_approved_plan():
    quests = json.loads((BASE / "data" / "quests.json").read_text(encoding="utf-8"))
    counts = {}
    for info in quests.values():
        tier = info.get("difficulty")
        assert tier in {"入门", "普通", "进阶", "高难", "重大"}, info.get("title")
        counts[tier] = counts.get(tier, 0) + 1
    assert counts == {"入门": 8, "普通": 13, "进阶": 18, "高难": 18, "重大": 3}

    notice = quests[NEW_QUEST]["notice"]
    low = Player("公告过滤低等级", "散人")
    assert notice not in _quest_notice_clues(low)

    ready = Player("公告过滤已满足", "散人")
    ready.level = 2
    ready.completed_quests.extend(["村道回暖·药铺复业", "新手采药·认识资源"])
    assert notice in _quest_notice_clues(ready)
