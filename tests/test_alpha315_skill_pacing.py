# -*- coding: utf-8 -*-
"""Alpha315：少林/武当/华山武学成长节奏修复。

本文件同时校验武学门槛数据与实际游戏流程：
角色必须通过正式授阶、前往对应演武场并请对应师长授课，才能真正学会武学。
"""
import contextlib
import io
import json
from pathlib import Path

import pytest

import engine
from actions import handle_skills
from player import Player

ROOT = Path(__file__).resolve().parents[1]

# (武学, 角色等级, 正式职位阶数, 门派声望)
GATES = {
    "少林": [
        ("罗汉拳", 1, 0, 0),
        ("般若掌", 3, 1, 20),
        ("金刚伏魔拳", 5, 3, 80),
        ("金刚护体拳", 6, 2, 50),
        ("金刚不坏身", 8, 2, 50),
        ("韦陀降魔印", 12, 2, 50),
    ],
    "武当": [
        ("太极剑", 1, 0, 0),
        ("绵掌", 3, 1, 20),
        ("两仪剑诀", 5, 3, 80),
        ("绕指柔剑", 6, 2, 50),
        ("紫霄绵劲", 8, 2, 50),
        ("真武玄剑", 12, 2, 50),
    ],
    "华山": [
        ("华山剑法", 1, 0, 0),
        ("夺命连环三仙剑", 3, 1, 20),
        ("破玉剑式", 5, 3, 80),
        ("苍松迎客剑", 6, 2, 50),
        ("白虹贯日", 8, 2, 50),
        ("天绅倒悬剑", 12, 2, 50),
    ],
}

UNCHANGED_GATES = {
    "铁衣门": [
        ("铁衣功", 3, 0, 0),
        ("破阵刀", 4, 1, 35),
        ("横练铁布衫", 8, 2, 50),
        ("裂石断岳刀", 12, 3, 100),
    ],
    "散人": [
        ("基础吐纳", 1, 0, 0),
        ("江湖散手", 3, 0, 0),
        ("流云步", 4, 0, 0),
        ("回风刺", 5, 0, 0),
        ("破势掌", 6, 0, 0),
        ("凝息诀", 6, 0, 0),
        ("行云流水掌", 4, 0, 0),
    ],
}

TRAINING = {
    "少林": {
        "room": "shaolin_training_ground",
        "place": "少林罗汉场",
        "basic": "罗汉拳",
        "trial": "少林历练·黑风除恶",
    },
    "武当": {
        "room": "wudang_training_ground",
        "place": "太和演武场",
        "basic": "太极剑",
        "trial": "武当历练·以静制动",
    },
    "华山": {
        "room": "huashan_training_ground",
        "place": "华山演武场",
        "basic": "华山剑法",
        "trial": "华山历练·磨剑黑风",
    },
}

PROMOTION_FLAGS = {
    "少林": {1: ["sect:shaolin:ordination:novice"], 2: ["sect:shaolin:ordination:full"]},
    "武当": {1: ["sect:wudang:sword_principle"], 2: ["sect:wudang:questline:inner_breath_done"]},
    "华山": {1: ["sect:huashan:sword_principle"], 2: ["sect:huashan:questline:patrol_done"]},
}

# 本次只调整学习门槛，战斗数值与效果必须保持原状。
COMBAT_SNAPSHOT = {
    ("少林", "般若掌"): (2.4, 25, {"type": "status", "status": "armor_break", "chance": 0.65, "turns": 2, "value": 4}),
    ("少林", "金刚护体拳"): (2.35, 28, {"type": "self_status", "status": "shield", "chance": 1.0, "turns": 2, "value": 32}),
    ("少林", "韦陀降魔印"): (2.7, 30, [{"type": "self_status", "status": "thorns", "chance": 1.0, "turns": 2, "value": 25}]),
    ("武当", "绵掌"): (2.2, 22, {"type": "self_status", "status": "shield", "chance": 1.0, "turns": 2, "value": 30}),
    ("武当", "绕指柔剑"): (2.3, 28, {"type": "self_status", "status": "damage_reduction", "chance": 1.0, "turns": 2, "value": 24}),
    ("武当", "真武玄剑"): (2.6, 30, [{"type": "self_status", "status": "damage_reduction", "chance": 1.0, "turns": 2, "value": 35}, {"type": "mp_restore", "amount": 15}]),
    ("华山", "夺命连环三仙剑"): (2.5, 26, {"type": "combo", "chance": 0.65, "hits": 2, "damage_ratio": 0.75}),
    ("华山", "苍松迎客剑"): (2.45, 30, {"type": "combo", "chance": 0.55, "hits": 2, "damage_ratio": 0.65}),
    ("华山", "天绅倒悬剑"): (2.68, 30, [{"type": "status", "status": "armor_break", "chance": 0.55, "turns": 2, "value": 5}, {"type": "combo", "chance": 0.55, "hits": 2, "damage_ratio": 0.65}]),
}


def _capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        fn(*args)
    return stream.getvalue()


def _skill(sect, name):
    return next(row for row in engine.SKILLS[sect] if row["name"] == name)


def _set_rank(player, sect, index):
    player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = index


def _use_basic(player, basic, times):
    for _ in range(times):
        player.record_skill_use(basic)


def test_alpha315_gate_table_matches_intended_pacing():
    for sect, rows in GATES.items():
        actual = {
            row["name"]: (row["level"], row["learn_min_rank"], row["learn_min_reputation"])
            for row in engine.SKILLS[sect]
        }
        assert actual == {name: (level, rank, rep) for name, level, rank, rep in rows}, sect
        for name, level, rank, rep in rows:
            assert level <= 15
            assert rank <= 3


def test_alpha315_skill_combat_values_are_untouched():
    for (sect, name), (power, mp_cost, effect) in COMBAT_SNAPSHOT.items():
        skill = _skill(sect, name)
        assert float(skill["power"]) == power
        assert int(skill["mp_cost"]) == mp_cost
        assert skill.get("effect") == effect or skill.get("effects") == effect


def test_alpha315_iron_and_wanderer_gates_stay_unchanged():
    for sect, rows in UNCHANGED_GATES.items():
        actual = {
            row["name"]: (row["level"], row["learn_min_rank"], row["learn_min_reputation"])
            for row in engine.SKILLS[sect]
        }
        assert actual == {name: (level, rank, rep) for name, level, rank, rep in rows}, sect


def test_alpha315_strength_skills_stay_at_rank_three_capstone():
    for sect, capstone in (("少林", "金刚伏魔拳"), ("武当", "两仪剑诀"), ("华山", "破玉剑式")):
        skill = _skill(sect, capstone)
        assert skill["level"] == 5
        assert skill["learn_min_rank"] == 3
        assert skill["learn_min_reputation"] == 80


def test_alpha315_l3_skill_is_reachable_at_rank_one():
    for sect, cfg in TRAINING.items():
        player = Player(f"Alpha315-三阶-{sect}", sect)
        player.level = 3
        player.change_sect_reputation(sect, 20)
        _set_rank(player, sect, 1)
        player.location = cfg["room"]

        name = GATES[sect][1][0]
        output = _capture(handle_skills, player, ["学习", name])
        assert "已学会" in output, (sect, name, output)
        assert player.get_skill_progress(name)["learned"]


def test_alpha315_l6_l8_and_l12_skills_are_reachable_before_l15():
    for sect, cfg in TRAINING.items():
        player = Player(f"Alpha315-中段-{sect}", sect)
        player.level = 8
        player.change_sect_reputation(sect, 50)
        _set_rank(player, sect, 2)
        player.location = cfg["room"]

        for name in (GATES[sect][3][0], GATES[sect][4][0]):
            output = _capture(handle_skills, player, ["学习", name])
            assert "已学会" in output, (sect, name, output)

        player.level = 11
        l12_name = GATES[sect][5][0]
        blocked = _capture(handle_skills, player, ["学习", l12_name])
        assert "等级不足" in blocked, (sect, l12_name, blocked)
        assert not player.get_skill_progress(l12_name)["learned"]

        player.level = 12
        learned = _capture(handle_skills, player, ["学习", l12_name])
        assert "已学会" in learned, (sect, l12_name, learned)


def test_alpha315_rank_two_blocks_capstone_until_formal_rank_three():
    for sect, cfg in TRAINING.items():
        player = Player(f"Alpha315-绝学-{sect}", sect)
        player.level = 15
        player.change_sect_reputation(sect, 100)
        _set_rank(player, sect, 2)
        player.location = cfg["room"]
        capstone = GATES[sect][2][0]

        blocked = _capture(handle_skills, player, ["学习", capstone])
        assert "身份不足" in blocked, (sect, capstone, blocked)
        assert not player.get_skill_progress(capstone)["learned"]


@pytest.mark.parametrize("sect", ["少林", "武当", "华山"])
def test_alpha315_full_learning_timeline_uses_real_promotion_and_teachers(sect):
    cfg = TRAINING[sect]
    player = Player(f"Alpha315-成长线-{sect}", sect)
    player.location = cfg["room"]
    basic = cfg["basic"]
    # 新入门弟子从最低身份起步，必须逐阶办理正式授阶。
    _set_rank(player, sect, 0)

    # L5：完成入门条件并正式授阶为外门身份，解锁本门 L3 武学。
    player.level = 5
    player.change_sect_reputation(sect, 20)
    _use_basic(player, basic, 10)
    for flag in PROMOTION_FLAGS[sect][1]:
        player.set_flag(flag, True)
    ok, message = player.promote_sect_rank()
    assert ok, (sect, message)
    assert player.get_sect_official_rank_index() == 1
    l3_name = GATES[sect][1][0]
    assert "已学会" in _capture(handle_skills, player, ["学习", l3_name])

    # L10：熟练度达到 30 后晋升内门身份，解锁 L6 与 L8 武学。
    player.level = 10
    player.change_sect_reputation(sect, 30)
    _use_basic(player, basic, 19)
    for flag in PROMOTION_FLAGS[sect][2]:
        player.set_flag(flag, True)
    ok, message = player.promote_sect_rank()
    assert ok, (sect, message)
    assert player.get_sect_official_rank_index() == 2
    for name in (GATES[sect][3][0], GATES[sect][4][0]):
        assert "已学会" in _capture(handle_skills, player, ["学习", name]), (sect, name)

    # L12：等级达标即可学习本门 L12 武学。
    player.level = 12
    l12_name = GATES[sect][5][0]
    assert "已学会" in _capture(handle_skills, player, ["学习", l12_name])

    # L15：完成本门历练并达到熟练度 50，晋升四阶身份后学习 L5 绝学。
    player.level = 15
    player.change_sect_reputation(sect, 50)
    _use_basic(player, basic, 20)
    player.completed_quests.append(cfg["trial"])
    if sect == "华山":
        assert player.establish_sect_mentorship("华山授业师父")[0]
        player.get_sect_mentorship()["bond"] = 15
    ok, message = player.promote_sect_rank()
    assert ok, (sect, message)
    assert player.get_sect_official_rank_index() == 3
    capstone = GATES[sect][2][0]
    assert "已学会" in _capture(handle_skills, player, ["学习", capstone])

    learned = {row["name"] for row in player.get_available_skills()}
    assert {name for name, *_ in GATES[sect]} <= learned


def test_alpha315_teacher_and_training_ground_are_still_required():
    player = Player("Alpha315-授课校验", "华山")
    player.level = 3
    player.change_sect_reputation("华山", 20)
    _set_rank(player, "华山", 1)

    player.location = "huashan_guest_hall"
    blocked = _capture(handle_skills, player, ["学习", "夺命连环三仙剑"])
    assert "华山演武场" in blocked
    assert not player.get_skill_progress("夺命连环三仙剑")["learned"]

    player.location = "huashan_training_ground"
    original_get_npcs = player.get_npcs_in_room
    try:
        player.get_npcs_in_room = lambda target=None: [
            n for n in original_get_npcs(target) if n != "华山传功师兄"
        ]
        missing = _capture(handle_skills, player, ["学习", "夺命连环三仙剑"])
        assert "暂时无法传授" in missing
    finally:
        player.get_npcs_in_room = original_get_npcs

    assert "已学会" in _capture(handle_skills, player, ["学习", "夺命连环三仙剑"])


def test_alpha315_skill_detail_reports_new_rank_and_reputation_gates():
    cases = [
        ("少林", "韦陀降魔印", "学习条件：角色等级 12 / 门派声望 50 / 正式职位：僧人"),
        ("武当", "绵掌", "学习条件：角色等级 3 / 门派声望 20 / 正式职位：外门弟子"),
        ("华山", "夺命连环三仙剑", "学习条件：角色等级 3 / 门派声望 20 / 正式职位：外门弟子"),
    ]
    for sect, name, expected in cases:
        player = Player(f"Alpha315-详情-{sect}", sect)
        output = _capture(handle_skills, player, ["详情", name])
        assert expected in output, (sect, name, output)


def test_alpha315_old_v12_character_keeps_reputation_derived_rank():
    player = Player("Alpha315-旧档身份", "少林")
    player.level = 12
    player.change_sect_reputation("少林", 50)
    assert player.get_sect_official_rank_index() == 2
    ok, reason = player.can_learn_skill("韦陀降魔印")
    assert ok, reason


def test_alpha315_learned_skill_survives_v12_roundtrip(tmp_path):
    player = Player("Alpha315-存档", "武当")
    player.level = 12
    player.change_sect_reputation("武当", 50)
    _set_rank(player, "武当", 2)
    player.location = "wudang_training_ground"
    assert "已学会" in _capture(handle_skills, player, ["学习", "真武玄剑"])
    player.record_skill_use("真武玄剑", True)

    path = tmp_path / "alpha315_save.json"
    assert player.save_to_file(str(path)) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION == 12

    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    progress = loaded.get_skill_progress("真武玄剑")
    assert progress["learned"] is True
    assert progress["mastery"] == 9


def test_alpha315_cross_sect_skill_stays_blocked():
    player = Player("Alpha315-跨门", "少林")
    player.level = 12
    player.change_sect_reputation("少林", 100)
    _set_rank(player, "少林", 2)
    ok, reason = player.can_learn_skill("绵掌")
    assert not ok
    assert "并非你当前门派可学武学" in reason


def test_alpha315_npc_skill_hints_match_new_rank_gates():
    npcs = json.loads((ROOT / "data" / "npcs.json").read_text(encoding="utf-8"))
    responses = {}
    for npc in npcs.values():
        for choice in npc.get("dialogue_choices", []) or []:
            if isinstance(choice, dict) and choice.get("id"):
                responses[choice["id"]] = choice.get("response", "")
    cases = [
        ("huashan_pine_sword_advanced", "内门弟子", "真传弟子"),
        ("shaolin_vajra_advanced", "僧人", "传法弟子"),
        ("wudang_soft_sword_advanced", "内门弟子", "真传弟子"),
    ]
    for choice_id, expected, stale in cases:
        response = responses.get(choice_id, "")
        assert expected in response, (choice_id, response)
        assert stale not in response, (choice_id, response)
    assert "少林僧人方可修习" in _skill("少林", "韦陀降魔印")["desc"]


def test_alpha315_skill_names_and_teachers_are_complete():
    seen = set()
    for sect, rows in engine.SKILLS.items():
        for row in rows:
            name = row["name"]
            assert name not in seen, name
            seen.add(name)
    for sect, cfg in TRAINING.items():
        sects_data = json.loads((ROOT / "data" / "sects.json").read_text(encoding="utf-8"))
        info = sects_data[sect]
        room_npcs = engine.ROOMS[cfg["room"]]["npcs"]
        for name, *_ in GATES[sect]:
            assert name in info["exclusive_skills"], (sect, name)
            assert info["skill_teachers"][name] in room_npcs, (sect, name)
