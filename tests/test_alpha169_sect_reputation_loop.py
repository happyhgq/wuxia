"""Alpha169：确保三大门派均有可持续、受冷却约束的声望成长途径。"""
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


def test_each_sect_has_a_repeatable_teacher_led_reputation_path():
    cases = [
        ("少林", "shaolin_training_ground", "少林传功师父", "罗汉拳"),
        ("武当", "wudang_training_ground", "武当传功师父", "太极剑"),
        ("华山", "huashan_training_ground", "华山授业师父", "华山剑法"),
    ]
    for sect, room, teacher, skill in cases:
        p = Player(f"{sect}修习闭环测试", "散人")
        p.level = max(p.level, 3)
        assert p.join_sect(sect)[0]
        p.location = room
        before = p.get_sect_reputation(sect)
        out = capture(handle_sect, p, ["修习"])
        assert skill in out and "声望提升 5" in out
        assert p.get_sect_reputation(sect) == before + 5


def test_sect_reputation_lesson_requires_correct_location_and_teacher():
    p = Player("门派修习条件测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("武当")[0]
    before = p.get_sect_reputation("武当")
    p.location = "wudang_guest_hall"
    out = capture(handle_sect, p, ["修习"])
    assert "太和演武场" in out
    assert p.get_sect_reputation("武当") == before
    p.location = "wudang_training_ground"
    original = engine.ROOMS[p.location]["npcs"][:]
    try:
        engine.ROOMS[p.location]["npcs"] = [n for n in original if n != "武当传功师父"]
        out = capture(handle_sect, p, ["修习"])
        assert "不在场" in out
        assert p.get_sect_reputation("武当") == before
    finally:
        engine.ROOMS[p.location]["npcs"] = original


def test_sect_reputation_lesson_cannot_be_repeated_before_four_ticks():
    p = Player("门派修习冷却测试", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("少林")[0]
    p.location = "shaolin_training_ground"
    before = p.get_sect_reputation("少林")
    first = capture(handle_sect, p, ["修习"])
    second = capture(handle_sect, p, ["修习"])
    assert "声望提升 5" in first
    assert "再历练 4 个世界时刻" in second
    assert p.get_sect_reputation("少林") == before + 5
    p.set_var("quest_clock", 4)
    third = capture(handle_sect, p, ["修习"])
    assert "声望提升 5" in third
    assert p.get_sect_reputation("少林") == before + 10


def test_sect_help_mentions_repeatable_study_command():
    p = Player("门派修习帮助测试", "散人")
    out = capture(handle_sect, p, [])
    assert "门派 修习" in out
