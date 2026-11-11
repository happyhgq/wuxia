"""Alpha148：华山正式拜师流程与演武场传功入口。"""
import contextlib
import io

import engine
from actions import handle_sect, handle_skills, handle_talk_and_ask
from main import parse_command
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_baishi_command_routes_to_sect_join_without_breaking_legacy_parser():
    assert parse_command("拜师 华山") == ("sect_join", ["华山"])
    assert parse_command("sect join 少林") == ("sect", ["join 少林"])


def test_huashan_join_requires_guest_hall_and_registered_interview():
    p = Player("入门流程测试", "散人")
    p.location = "village_gate"
    output = capture(handle_sect, p, ["join", "华山"])
    assert "迎客厅" in output
    assert p.get_sect() == "散人"

    p.location = "huashan_guest_hall"
    p.level = 10
    output = capture(handle_sect, p, ["join", "华山"])
    assert "接引执事" in output
    assert p.get_sect() == "散人"

    output = capture(handle_talk_and_ask, p, ["华山接引执事", "拜师"])
    assert "正式拜入【华山】" in output
    assert p.get_sect() == "华山"
    assert p.get_flag("sect:huashan:joined") is True
    assert p.get_flag("sect:huashan:entry_interview") is False
    assert "正式拜入" in output


def test_huashan_join_is_available_through_intuitive_baishi_command():
    p = Player("拜师命令测试", "散人")
    p.level = 10
    p.location = "huashan_guest_hall"
    capture(handle_talk_and_ask, p, ["华山接引执事", "拜师"])
    command, args = parse_command("拜师 华山")
    assert command == "sect_join"
    output = capture(handle_sect, p, ["join"] + args)
    assert "华山" in output
    assert p.get_sect() == "华山"


def test_legacy_multword_sect_command_is_recovered_by_handler():
    p = Player("旧命令兼容测试", "散人")
    p.location = "shaolin_guest_hall"
    p.level = 10
    output = capture(handle_sect, p, ["join 少林"])
    assert "接引僧" in output
    assert p.get_sect() == "散人"
    output = capture(handle_talk_and_ask, p, ["少林接引僧", "拜师"])
    assert "正式拜入【少林】" in output
    assert p.get_sect() == "少林"


def test_huashan_skills_require_training_ground_and_instructor_for_command_learning():
    p = Player("传功地点测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("华山")[0]
    p.location = "huashan_guest_hall"
    output = capture(handle_skills, p, ["学习", "夺命连环三仙剑"])
    assert "华山演武场" in output
    assert not p.get_skill_progress("夺命连环三仙剑")["learned"]

    p.location = "huashan_training_ground"
    assert "华山传功师兄" in p.get_npcs_in_room(p.location)
    output = capture(handle_skills, p, ["学习", "夺命连环三仙剑"])
    # The instructor requirement is satisfied; remaining level/reputation/rank rules still apply.
    assert "等级不足" in output or "声望不足" in output or "身份不足" in output or "学会" in output


def test_new_sect_npcs_are_attached_to_existing_huashan_rooms():
    assert "华山接引执事" in engine.ROOMS["huashan_guest_hall"]["npcs"]
    assert "华山传功师兄" in engine.ROOMS["huashan_training_ground"]["npcs"]
    assert engine.NPCS["华山接引执事"]["daily_schedule"][0]["location"] == "huashan_guest_hall"
    assert engine.NPCS["华山传功师兄"]["daily_schedule"][0]["location"] == "huashan_training_ground"
