"""Alpha166：门派入门、晋升考核与地图说明一致性回归。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_sect, handle_talk_and_ask
from player import Player
from travel_system import room_access_denial

ROOT = Path(__file__).resolve().parents[1]


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_wudang_join_requires_guest_hall_interview_and_records_success():
    p = Player("武当入门回归", "散人")
    p.location = "wudang_gate"
    output = capture(handle_sect, p, ["拜师", "武当"])
    assert "武当迎客厅" in output
    assert p.get_sect() == "散人"

    p.location = "wudang_guest_hall"
    p.level = 10
    output = capture(handle_sect, p, ["拜师", "武当"])
    assert "尚未登记" in output
    assert p.get_sect() == "散人"

    output = capture(handle_talk_and_ask, p, ["武当接引道人", "拜师"])
    assert "正式拜入【武当】" in output
    assert p.get_sect() == "武当"
    assert p.get_flag("sect:wudang:joined", False)
    assert not p.get_flag("sect:wudang:entry_interview", False)


def test_wudang_promotion_requires_training_ground_and_teacher():
    p = Player("武当晋升回归", "散人")
    assert p.join_sect("武当")[0]
    p.location = "wudang_guest_hall"
    output = capture(handle_sect, p, ["晋升"])
    assert "太和演武场" in output

    p.location = "wudang_training_ground"
    original = engine.ROOMS[p.location]["npcs"][:]
    try:
        engine.ROOMS[p.location]["npcs"] = [n for n in original if n != "武当传功师兄"]
        output = capture(handle_sect, p, ["晋升"])
        assert "传功师兄" in output and "不在场" in output
    finally:
        engine.ROOMS[p.location]["npcs"] = original


def test_wudang_internal_access_and_core_rank_gate_are_enforced():
    p = Player("武当地图门禁回归", "散人")
    assert "正式拜师后再入院修习" in room_access_denial(p, engine.ROOMS["wudang_outer_court"])
    assert p.join_sect("武当")[0]
    assert "内门弟子" in room_access_denial(p, engine.ROOMS["wudang_zhenwu_hall"])
    record = p._sect_progress_state().setdefault("武当", {})
    record["official_rank_index"] = 2
    assert room_access_denial(p, engine.ROOMS["wudang_zhenwu_hall"]) == ""


def test_each_sect_promotion_trial_and_teaching_location_are_defined():
    quests = json.loads((ROOT / "data" / "quests.json").read_text(encoding="utf-8"))
    rooms = engine.ROOMS
    npcs = engine.NPCS
    expected = {
        "少林": ("少林历练·黑风除恶", "shaolin_training_ground", "少林传功师父"),
        "武当": ("武当历练·以静制动", "wudang_training_ground", "武当传功师父"),
        "华山": ("华山历练·磨剑黑风", "huashan_training_ground", "华山传功师兄"),
    }
    for sect, (quest, room_id, teacher) in expected.items():
        assert quest in quests
        assert room_id in rooms
        assert teacher in rooms[room_id].get("npcs", [])
        assert teacher in npcs


def test_wudang_room_descriptions_match_actual_exit_directions():
    rooms = engine.ROOMS
    assert rooms["wudang_outer_court"]["exits"]["西"] == "wudang_zhenwu_hall"
    assert "西面通往真武殿" in rooms["wudang_outer_court"]["desc"]
    assert rooms["wudang_zhenwu_hall"]["exits"]["东"] == "wudang_outer_court"
    assert "东面返回武当外院" in rooms["wudang_zhenwu_hall"]["desc"]
