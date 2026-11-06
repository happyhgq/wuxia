# -*- coding: utf-8 -*-
"""Alpha292：散人门派武学显示补全与铁衣门中高阶武学补齐。"""
import contextlib
import io
import json
import re
import unicodedata
from pathlib import Path

import engine
from actions import handle_sect, handle_skills
from player import Player

ROOT = Path(__file__).resolve().parents[1]

SANREN_SKILLS = ["基础吐纳", "江湖散手", "流云步", "行云流水掌", "回风刺", "破势掌", "凝息诀"]

TIEYI_SKILLS = {
    "横练铁布衫": {
        "mp_cost": 22,
        "power": 1.7,
        "level": 8,
        "learn_min_reputation": 50,
        "learn_min_rank": 2,
        "effect": {"type": "self_status", "status": "shield", "chance": 1.0, "turns": 2, "value": 26},
    },
    "裂石断岳刀": {
        "mp_cost": 30,
        "power": 2.65,
        "level": 12,
        "learn_min_reputation": 100,
        "learn_min_rank": 3,
        "effect": {"type": "status", "status": "armor_break", "chance": 0.6, "turns": 2, "value": 4},
    },
}


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        fn(*args)
    return stream.getvalue()


def _display_width(text):
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def test_sanren_exclusive_skills_cover_every_learnable_move():
    sects = _data("sects.json")
    skills = _data("skills.json")
    assert sects["散人"]["exclusive_skills"] == SANREN_SKILLS
    assert set(SANREN_SKILLS) == {row["name"] for row in skills["散人"]}


def test_sanren_sect_panel_lists_all_seven_moves():
    player = Player("Alpha292-散人面板", "散人")
    summary = _capture(handle_sect, player, [])
    info = _capture(handle_sect, player, ["查看", "散人"])
    for name in SANREN_SKILLS:
        assert name in summary, name
        assert name in info, name
    skill_line = next(line for line in summary.splitlines() if line.startswith("门派武学："))
    assert _display_width(skill_line) <= 80
    assert set(SANREN_SKILLS) == {row["name"] for row in player.get_skill_summary()}


def test_sanren_can_learn_all_seven_without_sect_teacher_gate():
    player = Player("Alpha292-散人学习", "散人")
    player.level = 10
    player.change_sect_reputation("散人", 100)
    assert player.get_skill_progress("基础吐纳")["learned"]
    for name in SANREN_SKILLS[1:]:
        ok, reason = player.can_learn_skill(name)
        assert ok, (name, reason)


def test_tieyi_skill_data_and_teacher_coverage_are_complete():
    sects = _data("sects.json")
    skills = {row["name"]: row for row in _data("skills.json")["铁衣门"]}
    assert sects["铁衣门"]["exclusive_skills"] == ["铁衣功", "破阵刀", "横练铁布衫", "裂石断岳刀"]
    teachers = sects["铁衣门"]["skill_teachers"]
    assert set(teachers) == set(sects["铁衣门"]["exclusive_skills"])
    assert set(TIEYI_SKILLS) <= set(skills)
    for name, expected in TIEYI_SKILLS.items():
        skill = skills[name]
        for key, value in expected.items():
            assert skill[key] == value, (name, key, skill[key], value)
        teacher = teachers[name]
        assert teacher in engine.NPCS
        assert teacher in engine.ROOMS[sects["铁衣门"]["training"]["room_id"]]["npcs"]


def test_tieyi_new_skills_require_training_ground_and_rank():
    player = Player("Alpha292-铁衣门授课", "铁衣门")
    player.level = 20
    player.change_sect_reputation("铁衣门", 100)
    player._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 2

    player.location = "tieyi_council_hall"
    blocked = _capture(handle_skills, player, ["学习", "横练铁布衫"])
    assert "须前往铁衣门演武场" in blocked
    assert not player.get_skill_progress("横练铁布衫")["learned"]

    player.location = "tieyi_training_ground"
    learned = _capture(handle_skills, player, ["学习", "横练铁布衫"])
    assert "已学会【横练铁布衫】" in learned
    assert player.get_skill_progress("横练铁布衫")["learned"]

    rank_blocked = _capture(handle_skills, player, ["学习", "裂石断岳刀"])
    assert "门派身份不足" in rank_blocked
    assert not player.get_skill_progress("裂石断岳刀")["learned"]

    player._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 3
    player.change_sect_reputation("铁衣门", -50)
    rep_blocked = _capture(handle_skills, player, ["学习", "裂石断岳刀"])
    assert "门派声望不足" in rep_blocked
    assert not player.get_skill_progress("裂石断岳刀")["learned"]

    player.change_sect_reputation("铁衣门", 50)
    learned = _capture(handle_skills, player, ["学习", "裂石断岳刀"])
    assert "已学会【裂石断岳刀】" in learned
    assert player.get_skill_progress("裂石断岳刀")["learned"]


def test_tieyi_top_power_matches_peer_sect_spread():
    data = _data("skills.json")
    top = {sect: max(float(row["power"]) for row in data[sect])
           for sect in ("少林", "武当", "华山", "铁衣门")}
    assert top["铁衣门"] == 2.65
    assert max(top.values()) - min(top.values()) <= 0.35
    assert top["铁衣门"] < top["少林"]


def test_v12_roundtrip_preserves_new_tieyi_skill_progress(tmp_path):
    player = Player("Alpha292-存档", "铁衣门")
    player.level = 20
    player.change_sect_reputation("铁衣门", 100)
    player._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 3
    player.location = "tieyi_training_ground"
    _capture(handle_skills, player, ["学习", "裂石断岳刀"])
    player.record_skill_use("裂石断岳刀", True)

    path = tmp_path / "alpha292_save.json"
    assert player.save_to_file(str(path)) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == engine.SAVE_VERSION == 12

    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.get_sect() == "铁衣门"
    progress = loaded.get_skill_progress("裂石断岳刀")
    assert progress["learned"] is True
    assert progress["mastery"] == 9
    assert loaded.get_skill_progress("横练铁布衫")["learned"] is False
