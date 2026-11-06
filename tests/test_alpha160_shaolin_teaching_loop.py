"""Alpha160：少林武学传授与历练任务入口联动。"""
import contextlib
import io

import engine
from actions import handle_skills, handle_quest
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def joined_shaolin():
    p = Player("少林传授测试", "散人")
    assert p.join_sect("少林")[0]
    # 入门时可能自动授予基础拳法；这里重置该技能以测试“重新学习”的命令入口。
    if p.get_skill_progress("罗汉拳")["learned"]:
        p.forget_skill("罗汉拳")
    return p


def test_shaolin_skill_learning_requires_rohan_court():
    p = joined_shaolin()
    p.location = "shaolin_guest_hall"
    output = capture(handle_skills, p, ["学习", "罗汉拳"])
    assert "少林罗汉场" in output
    assert not p.get_skill_progress("罗汉拳")["learned"]


def test_shaolin_basic_skill_requires_the_teaching_master_present():
    p = joined_shaolin()
    p.location = "shaolin_training_ground"
    original = engine.ROOMS[p.location]["npcs"][:]
    try:
        engine.ROOMS[p.location]["npcs"] = [n for n in original if n != "少林传功师父"]
        output = capture(handle_skills, p, ["学习", "罗汉拳"])
        assert "传功师父" in output
        assert not p.get_skill_progress("罗汉拳")["learned"]
    finally:
        engine.ROOMS[p.location]["npcs"] = original


def test_shaolin_basic_skill_can_be_learned_from_master_in_training_ground():
    p = joined_shaolin()
    p.location = "shaolin_training_ground"
    output = capture(handle_skills, p, ["学习", "罗汉拳"])
    assert "学会【罗汉拳】" in output
    assert p.get_skill_progress("罗汉拳")["learned"]


def test_shaolin_advanced_skills_are_taught_by_senior_disciple_and_keep_rank_gates():
    p = joined_shaolin()
    p.location = "shaolin_training_ground"
    output = capture(handle_skills, p, ["学习", "般若掌"])
    assert "身份不足" in output or "声望不足" in output or "等级不足" in output
    assert not p.get_skill_progress("般若掌")["learned"]
    assert "少林传功师兄" in engine.ROOMS[p.location]["npcs"]


def test_shaolin_trial_must_be_accepted_from_the_quest_giver():
    p = joined_shaolin()
    q = "少林历练·黑风除恶"
    p.location = "shaolin_guest_hall"
    output = capture(handle_quest, p, "jiequ", [q])
    assert "少林传功师兄" in output
    assert q not in p.active_quests
    p.location = "shaolin_training_ground"
    output = capture(handle_quest, p, "jiequ", [q])
    assert "已接取任务" in output
    assert q in p.active_quests


def test_shaolin_trial_data_points_to_real_instructor_and_room():
    q = engine.QUESTS["少林历练·黑风除恶"]
    assert q["npc"] == "少林传功师兄"
    assert "少林传功师兄" in engine.ROOMS["shaolin_training_ground"]["npcs"]
    assert "少林历练·黑风除恶" in engine.NPCS["少林传功师兄"].get("quests", [])
