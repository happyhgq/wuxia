"""Alpha184：退门/转投后，师承指点必须绑定当前门派及本门授业师长。"""
from player import Player

MENTORS = {
    "少林": "少林传功师父",
    "武当": "武当传功师父",
    "华山": "华山授业师父",
}


def test_non_current_sect_cannot_receive_mentorship_lesson():
    player = Player("跨门派指点校验", "散人")
    assert player.join_sect("少林")[0]
    assert player.establish_sect_mentorship()[0]
    before = dict(player.get_sect_mentorship("少林"))
    ok, message = player.record_mentorship_lesson("少林")
    assert ok
    assert player.get_sect_mentorship("少林")["lessons"] == before.get("lessons", 0) + 1
    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]
    ok, message = player.record_mentorship_lesson("少林")
    assert not ok
    assert "当前门派" in message
    assert player.get_sect_mentorship("少林").get("mentor") is None


def test_stale_foreign_mentor_record_cannot_gain_bond_or_lessons():
    player = Player("旧师承记录校验", "散人")
    assert player.join_sect("华山")[0]
    record = player._sect_progress_state().setdefault("华山", {})
    record["mentorship"] = {"mentor": MENTORS["武当"], "bond": 10, "lessons": 2}
    ok, message = player.record_mentorship_lesson()
    assert not ok
    assert "不一致" in message
    assert record["mentorship"]["bond"] == 10
    assert record["mentorship"]["lessons"] == 2


def test_current_sect_mentorship_lesson_still_works_for_all_three_sects():
    for sect, mentor in MENTORS.items():
        player = Player(f"正常指点-{sect}", "散人")
        assert player.join_sect(sect)[0]
        assert player.establish_sect_mentorship(mentor)[0]
        ok, _ = player.record_mentorship_lesson()
        assert ok
        mentorship = player.get_sect_mentorship(sect)
        assert mentorship["lessons"] == 1
        assert mentorship["bond"] == 5
