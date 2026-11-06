"""Alpha254：门派授课、修习与晋升地点改为数据驱动。"""
import contextlib
import copy
import io
import json
from pathlib import Path

import engine
from actions import handle_sect, handle_skills
from player import Player

ROOT = Path(__file__).resolve().parents[1]


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_real_sects_define_training_and_skill_teacher_data():
    data = json.loads((ROOT / "data" / "sects.json").read_text(encoding="utf-8"))
    for sect in ("少林", "武当", "华山", "铁衣门"):
        row = data[sect]
        training = row["training"]
        assert training["room_id"] in engine.ROOMS
        assert training["lesson_teacher"]
        assert training["promotion_teacher"]
        assert training["place"]
        for skill_name, teacher in row.get("skill_teachers", {}).items():
            assert skill_name in row["exclusive_skills"]
            assert teacher in engine.NPCS


def test_skill_teacher_requirement_follows_sect_data():
    original = copy.deepcopy(engine.SECTS["武当"])
    try:
        p = Player("配置授课测试", "散人")
        p.level = 10
        assert p.join_sect("武当")[0]
        if p.get_skill_progress("太极剑")["learned"]:
            p.forget_skill("太极剑")
        p.location = "wudang_training_ground"
        engine.SECTS["武当"]["skill_teachers"]["太极剑"] = "测试传功师"
        out = capture(handle_skills, p, ["学习", "太极剑"])
        assert "暂时无法传授" in out
        assert not p.get_skill_progress("太极剑")["learned"]
    finally:
        engine.SECTS["武当"] = original


def test_lesson_and_promotion_use_configured_training_location():
    original = copy.deepcopy(engine.SECTS["武当"])
    try:
        p = Player("配置地点测试", "散人")
        p.level = 10
        assert p.join_sect("武当")[0]
        engine.SECTS["武当"]["training"]["room_id"] = "wudang_guest_hall"
        engine.SECTS["武当"]["training"]["place"] = "测试传功堂"
        p.location = "wudang_training_ground"
        out = capture(handle_sect, p, ["修习"])
        assert "测试传功堂" in out
        assert "须亲自前往" in out
    finally:
        engine.SECTS["武当"] = original


def test_promotion_result_uses_configured_examiner():
    original = copy.deepcopy(engine.SECTS["武当"])
    try:
        p = Player("配置考核者测试", "散人")
        p.level = 30
        assert p.join_sect("武当")[0]
        p.change_sect_reputation("武当", 500)
        p._sect_progress_state().setdefault("武当", {})["official_rank_index"] = 0
        p._skill_state()["太极剑"] = {"learned": True, "mastery": 100}
        # Alpha282：武当外门晋升需要先完成剑理历练。
        p.set_flag("sect:wudang:sword_principle", True)
        engine.SECTS["武当"]["training"]["promotion_teacher"] = "玄真真人"
        ok, message = p.promote_sect_rank("武当")
        assert ok
        assert "玄真真人" in message
        assert "传功师兄考核" in message
        assert "外门弟子" in message
    finally:
        engine.SECTS["武当"] = original
