"""Alpha181：少林、武当、华山师承必须与正式门派身份一致。"""
import engine
from player import Player


SECT_MENTORS = {
    "少林": "少林传功师父",
    "武当": "武当传功师父",
    "华山": "华山授业师父",
}


def disciple(sect):
    player = Player(f"师承校验-{sect}", "散人")
    player.level = max(player.level, 3)
    assert player.join_sect(sect)[0]
    return player


def test_default_mentor_is_selected_from_current_sect():
    for sect, mentor in SECT_MENTORS.items():
        player = disciple(sect)
        ok, message = player.establish_sect_mentorship()
        assert ok, f"{sect}: {message}"
        assert player.get_sect_mentorship(sect)["mentor"] == mentor


def test_foreign_sect_mentor_cannot_be_registered():
    for sect, expected_mentor in SECT_MENTORS.items():
        player = disciple(sect)
        foreign_mentor = next(name for other, name in SECT_MENTORS.items() if other != sect)
        ok, message = player.establish_sect_mentorship(foreign_mentor)
        assert not ok
        assert expected_mentor in message
        assert not player.get_sect_mentorship(sect).get("mentor")


def test_mentor_mapping_points_to_existing_npcs():
    assert all(mentor in engine.NPCS for mentor in SECT_MENTORS.values())


def test_huashan_explicit_mentor_remains_compatible():
    player = disciple("华山")
    ok, _ = player.establish_sect_mentorship("华山授业师父")
    assert ok
    assert player.get_sect_mentorship("华山")["mentor"] == "华山授业师父"
