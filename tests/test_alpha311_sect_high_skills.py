# -*- coding: utf-8 -*-
"""Alpha311：少林/武当/华山 L8–L12 高阶武学补齐与反震状态。"""
import contextlib
import io
import json
from copy import deepcopy
from pathlib import Path

import pytest

import combat
import engine
from actions import handle_skills
from player import Player

ROOT = Path(__file__).resolve().parents[1]

NEW_SKILLS = {
    "少林": {
        "金刚不坏身": {"level": 8, "rep": 50, "rank": 2, "power": 1.95},
        "韦陀降魔印": {"level": 12, "rep": 50, "rank": 2, "power": 2.7},
    },
    "武当": {
        "紫霄绵劲": {"level": 8, "rep": 50, "rank": 2, "power": 2.05},
        "真武玄剑": {"level": 12, "rep": 50, "rank": 2, "power": 2.6},
    },
    "华山": {
        "白虹贯日": {"level": 8, "rep": 50, "rank": 2, "power": 2.5},
        "天绅倒悬剑": {"level": 12, "rep": 50, "rank": 2, "power": 2.68},
    },
}

TRAINING_ROOMS = {
    "少林": "shaolin_training_ground",
    "武当": "wudang_training_ground",
    "华山": "huashan_training_ground",
}


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        fn(*args)
    return stream.getvalue()


def _skill(sect, name):
    return next(row for row in engine.SKILLS[sect] if row["name"] == name)


def _promote(player, sect, rank_index):
    player._sect_progress_state().setdefault(sect, {})["official_rank_index"] = rank_index


def test_new_skills_are_wired_into_sect_data_and_teachers():
    sects = _data("sects.json")
    for sect, rows in NEW_SKILLS.items():
        cfg = sects[sect]
        room_npcs = engine.ROOMS[TRAINING_ROOMS[sect]]["npcs"]
        for name, expected in rows.items():
            skill = _skill(sect, name)
            assert skill["level"] == expected["level"]
            assert skill["learn_min_reputation"] == expected["rep"]
            assert skill["learn_min_rank"] == expected["rank"]
            assert skill["power"] == expected["power"]
            assert name in cfg["exclusive_skills"]
            teacher = cfg["skill_teachers"][name]
            assert teacher in room_npcs, (sect, name, teacher, room_npcs)


def test_new_skills_keep_peer_sect_power_spread():
    tops = {sect: max(float(row["power"]) for row in engine.SKILLS[sect])
            for sect in ("少林", "武当", "华山", "铁衣门")}
    assert tops == {"少林": 2.75, "武当": 2.6, "华山": 2.7, "铁衣门": 2.65}
    assert max(tops.values()) - min(tops.values()) <= 0.35
    for sect, rows in NEW_SKILLS.items():
        for name, expected in rows.items():
            assert _skill(sect, name)["power"] <= tops[sect]


def test_high_skill_rank_gates():
    for sect, rows in NEW_SKILLS.items():
        for name, expected in rows.items():
            player = Player(f"Alpha311-门槛-{sect}-{name}", sect)
            player.level = 12
            player.change_sect_reputation(sect, 120)
            if player.get_skill_progress(name)["learned"]:
                player.forget_skill(name)
            _promote(player, sect, expected["rank"] - 1)
            ok, reason = player.can_learn_skill(name)
            assert not ok and "身份不足" in reason, (sect, name, reason)

            _promote(player, sect, expected["rank"])
            assert player.can_learn_skill(name)[0], (sect, name)


def test_l8_lessons_require_training_ground_and_present_teacher():
    player = Player("Alpha311-授课地点", "少林")
    player.level = 12
    player.change_sect_reputation("少林", 120)
    if player.get_skill_progress("金刚不坏身")["learned"]:
        player.forget_skill("金刚不坏身")
    _promote(player, "少林", 2)

    player.location = "village_square"
    blocked = _capture(handle_skills, player, ["学习", "金刚不坏身"])
    assert "须前往" in blocked and "少林罗汉场" in blocked
    assert not player.get_skill_progress("金刚不坏身")["learned"]

    player.location = "shaolin_training_ground"
    original_get_npcs = player.get_npcs_in_room
    try:
        player.get_npcs_in_room = lambda target=None: [
            name for name in original_get_npcs(target) if name != "少林传功师父"
        ]
        missing = _capture(handle_skills, player, ["学习", "金刚不坏身"])
        assert "暂时无法传授" in missing
    finally:
        player.get_npcs_in_room = original_get_npcs

    learned = _capture(handle_skills, player, ["学习", "金刚不坏身"])
    assert "已学会【金刚不坏身】" in learned
    assert player.get_skill_progress("金刚不坏身")["learned"]


def test_skill_detail_shows_new_gates_and_rank_label():
    player = Player("Alpha311-武学详情", "少林")
    output = _capture(handle_skills, player, ["详情", "韦陀降魔印"])
    assert "学习条件：角色等级 12 / 门派声望 50 / 正式职位：僧人" in output
    assert "反震" in _skill("少林", "韦陀降魔印")["combat_hint"]


def test_thorns_reflects_capped_percentage():
    assert engine.apply_thorns({}, 40) == 0
    assert engine.apply_thorns({"thorns": {"turns": 2, "value": 25}}, 40) == 10
    assert engine.apply_thorns({"thorns": {"turns": 2, "value": 25}}, 0) == 0
    # 配置异常也不会把反震放大成致命伤害。
    assert engine.apply_thorns({"thorns": {"turns": 2, "value": 200}}, 100) == 35
    assert engine.STATUS_EFFECTS["thorns"]["name"] == "反震"


class _StubPlayer:
    def __init__(self, skills):
        self.name = "Alpha311测试侠客"
        self.hp = 500
        self.max_hp = 500
        self.mp = 100
        self.max_mp = 100
        self.location = "test_room"
        self.inventory = []
        self._skills = skills
        self.saved = False

    def get_total_atk(self):
        return 50

    def get_total_defense(self):
        return 0

    def get_available_skills(self):
        return self._skills

    def record_skill_use(self, name, success):
        return {"mastery": 1, "mastery_max": 10, "level": 1}

    def update_quest_progress(self, name):
        return None

    def save_to_file(self, *args, **kwargs):
        self.saved = True


def _enemy(skills=None):
    return {
        "name": "试炼傀儡",
        "hp": 1000,
        "atk": 100,
        "defense": 0,
        "level": 1,
        "tier": "normal",
        "tier_label": "普通",
        "skills": skills or [],
        "phases": [],
        "exp": 0,
        "gold": 0,
        "drops": [],
    }


def _install_stubs(monkeypatch, inputs, enemy):
    monkeypatch.setattr(combat, "get_enemy_profile", lambda *a, **k: deepcopy(enemy))
    monkeypatch.setattr(combat, "apply_world_combat_pressure", lambda *a, **k: 0)
    monkeypatch.setattr(combat, "_player_combat_stats", lambda *a, **k: (1.0, 0.0, 0.0))
    monkeypatch.setattr(combat, "_enemy_combat_stats", lambda *a, **k: (1.0, 0.0, 0.0))
    monkeypatch.setattr(combat, "resolve_attack", lambda *a, **k: (25, "hit"))
    monkeypatch.setattr(combat, "apply_weapon_combat_effect", lambda *a, **k: [])
    monkeypatch.setattr(combat, "battle_pause", lambda *a, **k: None)
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    monkeypatch.setattr("world_lifecycle.entity_state", lambda *a, **k: ("alive", None))
    feed = iter(inputs)

    def fake_input(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise AssertionError(f"战斗请求了预期之外的输入：{prompt}")

    monkeypatch.setattr("builtins.input", fake_input)


@pytest.mark.parametrize("enemy_action", ["basic", "skill"])
def test_shaolin_l12_thorns_reflects_damage_back(monkeypatch, capsys, enemy_action):
    skill = _skill("少林", "韦陀降魔印")
    enemy = _enemy([{"name": "试炼斩", "power": 2.0}])
    if enemy_action == "basic":
        monkeypatch.setattr(combat, "choose_enemy_action", lambda *a, **k: {"action": "basic"})
    else:
        monkeypatch.setattr(combat, "choose_enemy_action",
                            lambda *a, **k: {"action": "skill", "skill": {"name": "试炼斩", "power": 2.0}})
    _install_stubs(monkeypatch, ["2", "1", "4"], enemy)
    player = _StubPlayer([skill])

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    # 敌人一击 25 点，反震 25% 计 6 点，正好回敬给对手。
    assert "【反震】护体真劲将 6 点劲力震回试炼傀儡身上！" in output
    assert player.hp == 475


def test_wudang_mp_restore_skill_still_attacks_and_reduces_damage(monkeypatch, capsys):
    skill = _skill("武当", "紫霄绵劲")
    monkeypatch.setattr(combat, "choose_enemy_action", lambda *a, **k: {"action": "basic"})
    _install_stubs(monkeypatch, ["2", "1", "4"], _enemy())
    player = _StubPlayer([skill])

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    # 带回气的高阶招式仍要出招，而不是被当成纯调息招式跳过伤害。
    assert "造成 25 点伤害" in output
    assert "恢复 12 点内力" in output
    assert player.mp == 88
    # 卸力 30%：25 → 17，说明护体效果真的生效。
    assert player.hp == 483


def test_wudang_and_huashan_high_skills_apply_declared_effects(monkeypatch):
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    wudang = _skill("武当", "真武玄剑")
    statuses = {}
    engine.clear_statuses()
    player = _StubPlayer([wudang])
    combat.apply_skill_effect(wudang, player, statuses)
    assert player.mp == 100
    assert engine.p_statuses_global["damage_reduction"]["value"] == 35
    assert engine.apply_damage_reduction(engine.p_statuses_global, 200) == 130
    engine.clear_statuses()

    huashan = _skill("华山", "天绅倒悬剑")
    enemy_statuses = {}
    combat.apply_skill_effect(huashan, player, enemy_statuses)
    assert enemy_statuses["armor_break"]["value"] == 5
    assert combat.has_skill_effect(huashan, "combo")
    extra = combat._combo_damage(100, huashan, 1.0, 0.0, 0.0)
    assert len(extra) == 1


def test_new_skill_progress_survives_v12_roundtrip(tmp_path):
    player = Player("Alpha311-存档", "华山")
    player.level = 12
    player.change_sect_reputation("华山", 120)
    if player.get_skill_progress("白虹贯日")["learned"]:
        player.forget_skill("白虹贯日")
    _promote(player, "华山", 2)
    player.location = "huashan_training_ground"
    _capture(handle_skills, player, ["学习", "白虹贯日"])
    player.record_skill_use("白虹贯日", True)

    path = tmp_path / "alpha311_save.json"
    assert player.save_to_file(str(path)) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION == 12

    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    progress = loaded.get_skill_progress("白虹贯日")
    assert progress["learned"] is True
    assert progress["mastery"] == 11
    assert loaded.get_skill_progress("天绅倒悬剑")["learned"] is False
