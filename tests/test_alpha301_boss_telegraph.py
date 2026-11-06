# -*- coding: utf-8 -*-
"""Alpha301：Boss 招牌技能一回合预警。"""
import json
from copy import deepcopy
from pathlib import Path

import pytest

import combat
import engine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _force_colors_on():
    import ui_output
    previous = ui_output.get_color_mode()
    ui_output.set_color_mode("on")
    yield
    ui_output.set_color_mode(previous)


BOSS_SKILLS = {
    "山贼大当家": ("困兽狂斩", "bandit_chief_feral_slash"),
    "黑市头目": ("黑市绝命掌", "black_market_fatal_palm"),
    "黑风寨守关首领": ("困兽回斩", "blackwind_pass_feral_counter"),
    "断魂堡主": ("断魂绝刀", "duanhun_fortress_soul_sever"),
}


class _FakePlayer:
    def __init__(self):
        self.name = "预警测试侠客"
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

    def record_skill_use(self, name, success):
        return {"mastery": 1, "mastery_max": 10, "level": 1}

    def update_quest_progress(self, name):
        return None

    def save_to_file(self, *args, **kwargs):
        self.saved = True


def _telegraph_enemy(skill):
    return {
        "name": "试炼傀儡",
        "hp": 1000,
        "atk": 100,
        "defense": 0,
        "level": 1,
        "tier": "boss",
        "tier_label": "首领",
        "skills": [skill],
        "phases": [],
        "exp": 0,
        "gold": 0,
        "drops": [],
    }


def _install_stubs(monkeypatch, inputs, enemy, stub_resolve=True):
    monkeypatch.setattr(combat, "get_enemy_profile", lambda *a, **k: deepcopy(enemy))
    monkeypatch.setattr(combat, "apply_world_combat_pressure", lambda *a, **k: 0)
    monkeypatch.setattr(combat, "_player_combat_stats", lambda *a, **k: (1.0, 0.0, 0.0))
    monkeypatch.setattr(combat, "_enemy_combat_stats", lambda *a, **k: (1.0, 0.0, 0.0))
    if stub_resolve:
        monkeypatch.setattr(combat, "resolve_attack", lambda *a, **k: (25, "hit"))
    monkeypatch.setattr(combat, "apply_weapon_combat_effect", lambda *a, **k: [])
    monkeypatch.setattr(combat, "apply_skill_effect", lambda *a, **k: [])
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


def test_four_boss_signature_skills_are_marked_with_stable_ids():
    data = json.loads((ROOT / "data" / "enemies.json").read_text(encoding="utf8"))
    seen_ids = set()
    for boss, (skill_name, skill_id) in BOSS_SKILLS.items():
        skill = next(sk for sk in data[boss]["skills"] if sk.get("name") == skill_name)
        assert skill.get("telegraph") is True, (boss, skill_name)
        assert skill.get("id") == skill_id, (boss, skill_name)
        assert skill_id not in seen_ids
        seen_ids.add(skill_id)


def test_telegraph_helper_only_accepts_explicit_skill_flag():
    assert combat.is_telegraph_skill({"name": "断魂绝刀", "telegraph": True})
    assert not combat.is_telegraph_skill({"name": "断魂斩"})
    assert not combat.is_telegraph_skill(None)
    assert combat.telegraph_warning("断魂堡主", {"name": "断魂绝刀"}) == (
        "【预警】断魂堡主正在蓄力「断魂绝刀」，下一回合将发动！"
    )


def test_warning_turn_deals_no_damage_and_next_turn_casts_original_skill(monkeypatch, capsys):
    skill = {"name": "困兽狂斩", "power": 2.0, "telegraph": True, "id": "test"}
    enemy = _telegraph_enemy(skill)
    monkeypatch.setattr(combat, "choose_enemy_action",
                        lambda *a, **k: {"action": "skill", "skill": skill})
    _install_stubs(monkeypatch, ["1", "1", "4"], enemy, stub_resolve=False)
    player = _FakePlayer()

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    warning = "【预警】试炼傀儡正在蓄力「困兽狂斩」，下一回合将发动！"
    cast = "施展出技能"
    flee = "你拔腿施展轻功，成功摆脱敌人！"
    assert output.count("【预警】") == 1
    assert warning in output
    assert output.index(warning) < output.index(cast) < output.index(flee)
    assert "【困兽狂斩】" in output
    # 预警回合不掉血，下一回合按原技能数值结算一次：100 × 2.0 × 100 / 100 = 200。
    assert player.hp == 300
    assert engine.Color.YELLOW in output and engine.Color.RESET in output


def test_telegraph_damage_still_uses_reduction_and_shield(monkeypatch, capsys):
    skill = {"name": "困兽狂斩", "power": 2.0, "telegraph": True, "id": "test"}
    enemy = _telegraph_enemy(skill)
    monkeypatch.setattr(combat, "choose_enemy_action",
                        lambda *a, **k: {"action": "skill", "skill": skill})
    calls = []

    def reduce_damage(statuses, damage):
        calls.append(damage)
        return max(0, damage - 50)

    monkeypatch.setattr(combat, "apply_damage_reduction", reduce_damage)
    _install_stubs(monkeypatch, ["1", "1", "4"], enemy, stub_resolve=False)
    player = _FakePlayer()

    combat.combat(player, "试炼傀儡")
    capsys.readouterr()

    assert 200 in calls
    assert calls[-1] == 200
    assert player.hp == 350


def test_telegraph_does_not_leak_into_next_battle(monkeypatch, capsys):
    skill = {"name": "困兽狂斩", "power": 2.0, "telegraph": True, "id": "test"}
    enemy = _telegraph_enemy(skill)
    monkeypatch.setattr(combat, "choose_enemy_action",
                        lambda *a, **k: {"action": "skill", "skill": skill})
    # 第一场在预警出现后立即逃跑，第二场改为普通攻击，不应继承旧预警。
    _install_stubs(monkeypatch, ["1", "4", "1", "4"], enemy)
    player = _FakePlayer()

    combat.combat(player, "试炼傀儡")
    first = capsys.readouterr().out
    assert "【预警】" in first
    monkeypatch.setattr(combat, "choose_enemy_action", lambda *a, **k: {"action": "basic"})
    combat.combat(player, "试炼傀儡")
    second = capsys.readouterr().out
    assert "【预警】" not in second
