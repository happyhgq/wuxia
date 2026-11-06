"""Alpha151：华山师承登记、请教与 V12 状态持久化。"""
import contextlib
import io

import engine
from actions import handle_sect
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def disciple():
    p = Player("师承测试", "散人")
    assert p.join_sect("华山")[0]
    p.location = "huashan_training_ground"
    return p


def test_huashan_master_is_existing_training_ground_npc():
    assert "华山授业师父" in engine.NPCS
    assert "华山授业师父" in engine.ROOMS["huashan_training_ground"]["npcs"]


def test_mentorship_must_be_registered_at_training_ground():
    p = disciple()
    p.location = "huashan_guest_hall"
    out = capture(handle_sect, p, ["师徒", "拜师"])
    assert "演武场" in out
    assert not p.get_sect_mentorship("华山").get("mentor")


def test_formal_mentorship_and_lesson_progress_are_recorded():
    p = disciple()
    out = capture(handle_sect, p, ["师徒", "拜师"])
    assert "正式建立师承关系" in out
    assert p.get_sect_mentorship("华山")["mentor"] == "华山授业师父"
    out = capture(handle_sect, p, ["师徒", "请教"])
    assert "师门默契提升至 5" in out
    record = p.get_sect_mentorship("华山")
    assert record["lessons"] == 1 and record["bond"] == 5
    assert p.get_sect_reputation("华山") == 1


def test_duplicate_mentorship_does_not_reset_progress():
    p = disciple()
    p.establish_sect_mentorship()
    p.record_mentorship_lesson()
    ok, message = p.establish_sect_mentorship()
    assert not ok and "无需重复" in message
    assert p.get_sect_mentorship("华山")["lessons"] == 1


def test_mentorship_uses_existing_world_state_and_does_not_change_save_version():
    p = disciple()
    p.establish_sect_mentorship()
    assert p.world_state["variables"]["sect_state"]["progress"]["华山"]["mentorship"]["mentor"] == "华山授业师父"
    assert getattr(p, "SAVE_VERSION", 12) == 12


def test_mentorship_query_redirects_to_character_panel():
    p = disciple()
    p.establish_sect_mentorship()
    out = capture(handle_sect, p, ["师徒", "查看"])
    assert "人物面板" in out
    assert "师门默契" not in out


def test_mentorship_lesson_cannot_be_spammed_without_world_time():
    p = disciple()
    p.establish_sect_mentorship()
    assert p.record_mentorship_lesson()[0]
    before_rep = p.get_sect_reputation("华山")
    ok, message = p.record_mentorship_lesson()
    assert not ok and "自行练习" in message
    assert p.get_sect_mentorship("华山")["lessons"] == 1
    assert p.get_sect_mentorship("华山")["bond"] == 5
    assert p.get_sect_reputation("华山") == before_rep


def test_mentorship_lesson_cooldown_expires_after_three_world_ticks():
    p = disciple()
    p.establish_sect_mentorship()
    assert p.record_mentorship_lesson()[0]
    p.tick_quest_clock(3)
    ok, _ = p.record_mentorship_lesson()
    assert ok
    assert p.get_sect_mentorship("华山")["lessons"] == 2
    assert p.get_sect_mentorship("华山")["bond"] == 10


def test_mentorship_guidance_changes_with_actual_skill_learning():
    p = disciple()
    p.establish_sect_mentorship()
    p._skill_state()["华山剑法"] = {"learned": False, "mastery": 0}
    ok, beginner_message = p.record_mentorship_lesson()
    assert ok and "尚未真正掌握本门武学" in beginner_message
    p.tick_quest_clock(3)
    p.record_skill_use("华山剑法")
    p._skill_state()["华山剑法"]["learned"] = True
    ok, practiced_message = p.record_mentorship_lesson()
    assert ok and "华山剑法" in practiced_message
    assert "尚未真正掌握本门武学" not in practiced_message
    assert p.get_sect_mentorship("华山")["last_lesson_skill"] == "华山剑法"
