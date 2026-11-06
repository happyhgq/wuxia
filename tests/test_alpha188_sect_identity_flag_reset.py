"""Alpha188：退门后清除与当前门派身份绑定的阶段许可。"""
from player import Player


def test_leaving_shaolin_clears_identity_bound_ordination_and_scripture_flags():
    player = Player("少林阶段许可", "少林")
    flags = [
        "sect:shaolin:joined",
        "sect:shaolin:entry_interview",
        "sect:shaolin:ordination:novice",
        "sect:shaolin:ordination:full",
        "sect:shaolin:scripture_catalogue_reviewed",
    ]
    for flag in flags:
        player.set_flag(flag, True)

    ok, _ = player.leave_sect()

    assert ok
    assert player.get_sect() == "散人"
    assert all(not player.get_flag(flag, False) for flag in flags)


def test_leaving_one_sect_does_not_clear_another_sects_flags():
    player = Player("跨门派许可隔离", "少林")
    player.set_flag("sect:shaolin:scripture_catalogue_reviewed", True)
    player.set_flag("sect:wudang:joined", True)

    assert player.leave_sect()[0]

    assert not player.get_flag("sect:shaolin:scripture_catalogue_reviewed", False)
    assert player.get_flag("sect:wudang:joined", False)


def test_rejoining_shaolin_requires_reviewing_scripture_rules_again():
    player = Player("重新拜入少林", "少林")
    player.set_flag("sect:shaolin:scripture_catalogue_reviewed", True)
    assert player.leave_sect()[0]
    assert player.join_sect("少林")[0]

    assert not player.get_flag("sect:shaolin:scripture_catalogue_reviewed", False)
    assert player.get_sect() == "少林"
    assert player.get_sect_official_rank_index("少林") == 0
