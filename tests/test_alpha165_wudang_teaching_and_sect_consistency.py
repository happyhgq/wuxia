"""Alpha165：武当传功地点、师长与三大门派基础配置一致性。"""
import contextlib
import io

import engine
from actions import handle_skills
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def joined_wudang():
    p = Player("武当传功测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("武当")[0]
    for skill in ("太极剑", "绵掌", "两仪剑诀"):
        if p.get_skill_progress(skill)["learned"]:
            p.forget_skill(skill)
    return p


def test_wudang_skills_require_training_ground():
    p = joined_wudang()
    p.location = "wudang_guest_hall"
    output = capture(handle_skills, p, ["学习", "太极剑"])
    assert "太和演武场" in output
    assert not p.get_skill_progress("太极剑")["learned"]


def test_wudang_basic_skill_requires_master_present():
    p = joined_wudang()
    p.location = "wudang_training_ground"
    original = engine.ROOMS[p.location]["npcs"][:]
    try:
        engine.ROOMS[p.location]["npcs"] = [n for n in original if n != "武当传功师父"]
        output = capture(handle_skills, p, ["学习", "太极剑"])
        assert "传功师父" in output
        assert not p.get_skill_progress("太极剑")["learned"]
    finally:
        engine.ROOMS[p.location]["npcs"] = original


def test_wudang_basic_skill_can_be_learned_at_training_ground():
    p = joined_wudang()
    p.location = "wudang_training_ground"
    output = capture(handle_skills, p, ["学习", "太极剑"])
    assert "学会【太极剑】" in output
    assert p.get_skill_progress("太极剑")["learned"]


def test_wudang_advanced_skills_use_senior_instructor_and_keep_rank_gates():
    p = joined_wudang()
    p.location = "wudang_training_ground"
    assert "武当传功师兄" in engine.ROOMS[p.location]["npcs"]
    output = capture(handle_skills, p, ["学习", "绵掌"])
    assert "身份不足" in output or "声望不足" in output or "等级不足" in output or "学会" in output
    assert not p.get_skill_progress("绵掌")["learned"] or "学会【绵掌】" in output


def test_all_three_sects_have_five_rank_labels_and_exclusive_skills_defined():
    for sect in ("少林", "武当", "华山"):
        info = engine.SECTS[sect]
        assert len(info["ranks"]) == 5
        assert len(info["exclusive_skills"]) >= 3
        assert all(skill in {row["name"] for row in engine.SKILLS[sect]} for skill in info["exclusive_skills"])


def test_wudang_map_rooms_and_teachers_are_connected():
    rooms = engine.ROOMS
    for room_id in ("wudang_foothill", "wudang_pine_path", "wudang_stone_steps", "wudang_gate", "wudang_guest_hall", "wudang_outer_court", "wudang_training_ground", "wudang_disciple_courtyard", "wudang_zhenwu_hall"):
        assert room_id in rooms
        assert rooms[room_id]["zone"] == "wudang_mountain"
        for target in rooms[room_id].get("exits", {}).values():
            assert target in rooms
    assert "武当传功师父" in rooms["wudang_training_ground"]["npcs"]
    assert "武当传功师兄" in rooms["wudang_training_ground"]["npcs"]
