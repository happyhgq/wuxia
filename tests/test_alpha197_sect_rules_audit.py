"""Alpha197：门派规则数据一致性与铁衣门职位称谓回归。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_sect
from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]


def test_sect_and_world_faction_relations_are_consistent_and_reciprocal():
    factions = json.loads((ROOT / "data" / "factions.json").read_text(encoding="utf-8"))
    for sect, info in engine.SECTS.items():
        if sect == "散人":
            continue
        assert sect in factions
        for other, relation in (info.get("relations", {}) or {}).items():
            assert other in engine.SECTS
            assert factions[sect]["relations"].get(other) == relation
            assert factions[other]["relations"].get(sect) == relation


def test_all_sect_skill_gates_and_room_rank_gates_reference_valid_ranks():
    for sect, info in engine.SECTS.items():
        ranks = info.get("ranks", []) or []
        for skill in engine.SKILLS.get(sect, []) or []:
            assert 0 <= int(skill.get("learn_min_rank", 0)) < len(ranks), (sect, skill.get("name"))
            assert int(skill.get("learn_min_reputation", 0)) >= 0
        for room_id, room in engine.ROOMS.items():
            access = room.get("access") or {}
            if access.get("sect") == sect and access.get("min_rank_index") is not None:
                assert 0 <= int(access["min_rank_index"]) < len(ranks), (room_id, sect)


def test_soloist_skill_gate_is_reachable_without_nonexistent_sect_ranks():
    p = Player("散人武学门槛验收", "散人")
    p.level = 3
    p.change_sect_reputation("散人", 50)
    ok, reason = p.can_learn_skill("江湖散手")
    assert ok, reason
    assert p.learn_skill("江湖散手")[0]


def test_iron_gate_and_training_ground_show_correct_access_and_teacher_wording():
    p = Player("铁衣门称谓验收", "散人")
    p.level = 3
    assert "铁衣门门人开放" in room_access_denial(p, engine.ROOMS["tieyi_training_ground"])
    assert p.join_sect("铁衣门")[0]
    p.location = "tieyi_guest_hall"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_sect(p, ["晋升"])
    assert "铁衣门演武场" in output.getvalue()
    assert "铁衣门传功师父" in output.getvalue()
    assert "传功师兄" not in output.getvalue()


def test_iron_promotion_success_uses_sect_specific_teacher_title():
    p = Player("铁衣门晋升称谓验收", "散人")
    p.level = 3
    assert p.join_sect("铁衣门")[0]
    p.level = 10
    p.change_sect_reputation("铁衣门", 20)
    p._skill_state()["铁衣功"] = {"learned": True, "mastery": 10}
    p.set_flag("sect:tieyi:trade_route", True)
    ok, message = p.promote_sect_rank()
    assert ok, message
    assert "传功师父考核" in message
    assert "传功师兄" not in message
