"""Alpha183：退出门派后清理有效身份，避免旧师承和仪式状态污染转投流程。"""
from player import Player

SECTS = {
    "少林": ("shaolin", ("ordination:novice", "ordination:full")),
    "武当": ("wudang", ()),
    "华山": ("huashan", ()),
}


def test_leaving_sect_clears_active_rank_mentorship_and_admission_flags():
    mentors = {"少林": "少林传功师父", "武当": "武当传功师父", "华山": "华山授业师父"}
    for sect, (prefix, rites) in SECTS.items():
        p = Player(f"退门验收-{sect}", "散人")
        p.level = max(p.level, 3)
        assert p.join_sect(sect)[0]
        p._sect_progress_state()[sect]["official_rank_index"] = 3
        p._sect_progress_state()[sect]["mentorship"] = {"mentor": mentors[sect], "bond": 20, "lessons": 4}
        for suffix in ("joined", "entry_interview", *rites):
            p.set_flag(f"sect:{prefix}:{suffix}", True)
        assert p.leave_sect()[0]
        assert p.get_sect() == "散人"
        assert p.get_sect_official_rank_index(sect) == 0
        assert not p.get_sect_mentorship(sect).get("mentor")
        for suffix in ("joined", "entry_interview", *rites):
            assert not p.get_flag(f"sect:{prefix}:{suffix}", False)


def test_switching_sects_does_not_transfer_old_rank_or_mentorship():
    p = Player("转投门派验收", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("华山")[0]
    p._sect_progress_state()["华山"]["official_rank_index"] = 4
    p._sect_progress_state()["华山"]["mentorship"] = {"mentor": "华山授业师父", "bond": 80}
    assert p.leave_sect()[0]
    p.level = max(p.level, 3)
    assert p.join_sect("武当")[0]
    assert p.get_sect() == "武当"
    assert p.get_sect_official_rank_index("武当") == 0
    assert not p.get_sect_mentorship("武当").get("mentor")
    assert p.get_sect_official_rank_index("华山") == 0
    assert not p.get_sect_mentorship("华山").get("mentor")


def test_v12_world_state_shape_is_preserved_after_leaving_sect():
    p = Player("旧存档结构验收", "散人")
    p.level = max(p.level, 3)
    assert p.join_sect("少林")[0]
    assert p.leave_sect()[0]
    assert p.world_state["variables"]["sect_state"]["current_sect"] == "散人"
    assert "sect_state" in p.world_state["variables"]
    assert p.world_state["variables"]["sect_state"]["reputation"].get("少林") is not None
