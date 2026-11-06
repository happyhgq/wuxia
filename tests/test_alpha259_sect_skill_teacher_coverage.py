"""Alpha259：门派传承武学必须能在配置的授课地点找到对应师长。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_skills
from player import Player

ROOT = Path(__file__).resolve().parents[1]


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_every_sect_skill_has_a_real_configured_teacher_and_room():
    sects = json.loads((ROOT / "data" / "sects.json").read_text(encoding="utf-8"))
    for sect, skills in engine.SKILLS.items():
        if sect not in sects or sect == "散人":
            continue
        config = sects[sect]
        teacher_map = config.get("skill_teachers", {})
        training = config.get("training", {})
        room_id = training.get("room_id")
        assert room_id in engine.ROOMS, f"{sect}: missing training room {room_id}"
        room_npcs = engine.ROOMS[room_id].get("npcs", [])
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            name = skill.get("name")
            assert name in teacher_map, f"{sect}: {name} has no configured skill teacher"
            assert teacher_map[name] in room_npcs, f"{sect}: {name} teacher absent from {room_id}"


def test_tieyi_skills_are_blocked_outside_training_ground_and_learnable_inside():
    player = Player("铁衣门授课检查", "铁衣门")
    player.level = 20
    player.change_sect_reputation("铁衣门", 100)
    player._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 2

    player.location = "tieyi_council_hall"
    blocked = capture(handle_skills, player, ["学习", "铁衣功"])
    assert "须前往铁衣门演武场" in blocked
    assert not player.get_skill_progress("铁衣功")["learned"]

    player.location = "tieyi_training_ground"
    learned = capture(handle_skills, player, ["学习", "铁衣功"])
    assert "已学会【铁衣功】" in learned
    assert player.get_skill_progress("铁衣功")["learned"]


def test_tieyi_advanced_skill_uses_same_teacher_location_gate():
    player = Player("铁衣门高阶授课检查", "铁衣门")
    player.level = 20
    player.change_sect_reputation("铁衣门", 100)
    player._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 2
    player.location = "tieyi_council_hall"
    blocked = capture(handle_skills, player, ["学习", "破阵刀"])
    assert "须前往铁衣门演武场" in blocked
    assert not player.get_skill_progress("破阵刀")["learned"]

    player.location = "tieyi_training_ground"
    learned = capture(handle_skills, player, ["学习", "破阵刀"])
    assert "已学会【破阵刀】" in learned
    assert player.get_skill_progress("破阵刀")["learned"]
