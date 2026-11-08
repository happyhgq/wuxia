# -*- coding: utf-8 -*-
"""Alpha280：颜色常量一致性、未知颜色兜底与战斗分支冒烟测试。"""
import re
from copy import deepcopy
from pathlib import Path

import pytest

import engine
import combat
import actions


ROOT = Path(__file__).resolve().parents[1]
COLOR_REF_RE = re.compile(r"\bColor\.([A-Za-z_][A-Za-z0-9_]*)")
SKIPPED_DIRS = {"__pycache__", ".pytest_cache", ".git", ".venv", "venv", "build", "dist"}


@pytest.fixture(autouse=True)
def _force_colors_on():
    """本文件验证颜色输出本身，固定为开启以抵消非交互终端自动关闭。"""
    import ui_output
    previous = ui_output.get_color_mode()
    ui_output.set_color_mode("on")
    yield
    ui_output.set_color_mode(previous)


def _iter_source_files():
    for path in ROOT.rglob("*.py"):
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        yield path


def test_every_color_reference_is_defined():
    defined = {name for name in vars(engine.Color) if name.isupper()}
    missing = {}
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in COLOR_REF_RE.finditer(line):
                name = match.group(1)
                if name not in defined:
                    missing.setdefault(name, []).append(f"{path.relative_to(ROOT).as_posix()}:{lineno}")
    assert missing == {}


def test_bright_magenta_is_a_real_standard_ansi_color():
    assert engine.Color.BRIGHT_MAGENTA == "\033[95m"
    assert "BRIGHT_MAGENTA" in vars(engine.Color)
    assert "BRIGHT_PURPLE" not in vars(engine.Color)


def test_color_text_wraps_known_color_and_resets():
    output = engine.color_text("阶段提示", "BRIGHT_MAGENTA")
    assert output == f"\033[95m阶段提示{engine.Color.RESET}"


def test_color_text_unknown_name_warns_and_falls_back_to_reset():
    with pytest.warns(RuntimeWarning, match="回退"):
        output = engine.color_text("提示", "ALPHA280_MISSING_COLOR")
    assert output == f"{engine.Color.RESET}提示{engine.Color.RESET}"


def test_unknown_class_color_warns_and_falls_back_to_reset():
    with pytest.warns(RuntimeWarning, match="ALPHA280_MISSING_COLOR"):
        value = getattr(engine.Color, "ALPHA280_MISSING_COLOR")
    assert value == engine.Color.RESET


def test_unknown_class_color_raises_in_strict_mode(monkeypatch):
    monkeypatch.setenv("WUXIA_STRICT_COLORS", "1")
    with pytest.warns(RuntimeWarning):
        with pytest.raises(AttributeError, match="ALPHA280_MISSING_COLOR"):
            getattr(engine.Color, "ALPHA280_MISSING_COLOR")


class _FakePlayer:
    def __init__(self, inventory=None):
        self.name = "测试侠客"
        self.hp = 500
        self.max_hp = 500
        self.mp = 100
        self.max_mp = 100
        self.location = "test_room"
        self.inventory = list(inventory or [])
        self.saved = False

    def get_total_atk(self):
        return 50

    def get_total_defense(self):
        return 0

    def get_available_skills(self):
        return [{
            "name": "测试剑法",
            "mp_cost": 5,
            "power": 1.2,
            "combat_hint": "",
            "crit_bonus": 0.0,
        }]

    def record_skill_use(self, name, success):
        return {"mastery": 1, "mastery_max": 10, "level": 1}

    def update_quest_progress(self, name):
        return None

    def save_to_file(self, *args, **kwargs):
        self.saved = True


def _enemy(hp=1000, phases=None):
    return {
        "name": "试炼傀儡",
        "hp": hp,
        "atk": 0,
        "defense": 0,
        "level": 1,
        "tier": "normal",
        "tier_label": "普通",
        "skills": [],
        "phases": phases or [],
        "exp": 0,
        "gold": 0,
        "drops": [],
    }


def _install_combat_stubs(monkeypatch, inputs, enemy, player, status_effects=None):
    monkeypatch.setattr(combat, "get_enemy_profile", lambda *args, **kwargs: deepcopy(enemy))
    monkeypatch.setattr(combat, "apply_world_combat_pressure", lambda *args, **kwargs: 0)
    monkeypatch.setattr(combat, "_player_combat_stats", lambda *args, **kwargs: (1.0, 0.0, 0.0))
    monkeypatch.setattr(combat, "resolve_attack", lambda *args, **kwargs: (25, "hit"))
    monkeypatch.setattr(combat, "choose_enemy_action", lambda *args, **kwargs: {"action": "attack"})
    monkeypatch.setattr(combat, "apply_weapon_combat_effect", lambda *args, **kwargs: [])
    monkeypatch.setattr(combat, "apply_skill_effect", lambda *args, **kwargs: ["剑气激荡，敌人身形一滞。"])
    monkeypatch.setattr(combat, "battle_pause", lambda *args, **kwargs: None)
    monkeypatch.setattr(combat.random, "random", lambda: 0.0)
    monkeypatch.setattr("world_lifecycle.entity_state", lambda *args, **kwargs: ("alive", None))
    if status_effects is not None:
        monkeypatch.setattr(combat, "process_status_effects", status_effects)

    feed = iter(inputs)

    def fake_input(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise AssertionError(f"战斗请求了预期之外的输入：{prompt}")

    monkeypatch.setattr("builtins.input", fake_input)


def test_normal_attack_announces_boss_phase_and_continues(monkeypatch, capsys):
    player = _FakePlayer()
    enemy = _enemy(hp=100, phases=[{
        "threshold": 0.9,
        "message": "【试炼傀儡】气势一变，进入第二阶段！",
        "heal_percent": 0,
    }])
    _install_combat_stubs(monkeypatch, ["1", "4"], enemy, player)

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    assert "你挥舞兵刃发起攻击，造成 25 点伤害！" in output
    assert "【试炼傀儡】气势一变，进入第二阶段！" in output
    assert "\033[95m" in output
    # 普通战斗日志恢复中性正文，不再整句黄色。
    assert "\033[93m" not in output
    assert "试炼傀儡 发起攻击，对你造成 25 点伤害！" in output
    assert "你拔腿施展轻功，成功摆脱敌人！" in output


def test_martial_skill_branch_outputs_and_consumes_mp(monkeypatch, capsys):
    player = _FakePlayer()
    _install_combat_stubs(monkeypatch, ["2", "1", "4"], _enemy(), player)

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    assert "你一式【测试剑法】轰出，造成 25 点伤害！" in output
    assert "剑气激荡，敌人身形一滞。" in output
    assert "熟练度：1/10（武学等级 1）" in output
    assert "试炼傀儡 发起攻击，对你造成 25 点伤害！" in output
    assert player.mp == 95


def test_item_branch_uses_consumable_and_keeps_round(monkeypatch, capsys):
    player = _FakePlayer(inventory=["疗伤药"])
    _install_combat_stubs(monkeypatch, ["3", "1", "4"], _enemy(), player)
    calls = []

    def fake_consumable(actor, item_name, context):
        calls.append((actor, item_name, dict(context)))
        print(f"你服下【{item_name}】，气血渐渐平复。")
        context["enemy_hp"] = max(0, int(context["enemy_hp"]) - 10)
        return True

    monkeypatch.setattr(actions, "apply_consumable", fake_consumable)

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    assert len(calls) == 1
    assert calls[0][1] == "疗伤药"
    assert "你服下【疗伤药】，气血渐渐平复。" in output
    assert "试炼傀儡 发起攻击，对你造成 25 点伤害！" in output
    assert "你拔腿施展轻功，成功摆脱敌人！" in output


def test_flee_branch_succeeds_and_saves(monkeypatch, capsys):
    player = _FakePlayer()
    _install_combat_stubs(monkeypatch, ["4"], _enemy(), player)

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    assert "你拔腿施展轻功，成功摆脱敌人！" in output
    assert player.saved is True


def test_status_messages_and_enemy_action_are_printed(monkeypatch, capsys):
    player = _FakePlayer()

    def fake_status_effects(statuses):
        if statuses is engine.p_statuses_global:
            return -5, False, ["旧伤隐隐作痛，损失 5 点气血。"]
        return 0, False, ["敌人屏息凝神，气息渐沉。"]

    _install_combat_stubs(monkeypatch, ["1", "4"], _enemy(), player, fake_status_effects)

    combat.combat(player, "试炼傀儡")
    output = capsys.readouterr().out

    assert "你：旧伤隐隐作痛，损失 5 点气血。" in output
    assert "试炼傀儡：敌人屏息凝神，气息渐沉。" in output
    assert "试炼傀儡 发起攻击，对你造成 25 点伤害！" in output
