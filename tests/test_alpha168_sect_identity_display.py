"""Alpha168：统一门派正式身份展示，并保护旧 V12 声望兼容行为。"""
from player import Player


def test_newly_joined_sect_summary_shows_formal_rank_not_reputation_rank():
    for sect, expected_start, reputation_rank in [
        ("少林", "俗家弟子", "僧人"),
        ("武当", "记名弟子", "内门弟子"),
        ("华山", "记名弟子", "内门弟子"),
    ]:
        player = Player(f"{sect}身份显示测试", "散人")
        assert player.join_sect(sect)[0]
        player.change_sect_reputation(sect, 50)
        summary = player.get_sect_summary(sect)
        assert summary["rank"] == expected_start
        assert player.get_sect_official_rank(sect) == expected_start
        # 旧接口仍保留按声望推算的行为，避免破坏既有调用与旧测试。
        assert player.get_sect_rank(sect) == reputation_rank


def test_legacy_save_without_official_rank_record_keeps_reputation_based_rank():
    for sect, expected in [("少林", "僧人"), ("武当", "内门弟子"), ("华山", "内门弟子")]:
        player = Player(f"旧存档{sect}身份测试", sect)
        player.change_sect_reputation(sect, 50)
        progress = player._sect_progress_state()
        progress.pop(sect, None)
        assert player.get_sect_official_rank(sect) == expected
        assert player.get_sect_summary(sect)["rank"] == expected


def test_official_rank_summary_updates_after_formal_promotion():
    player = Player("正式晋升身份显示测试", "散人")
    player.level = 3
    assert player.join_sect("武当")[0]
    player.location = "wudang_training_ground"
    player.change_sect_reputation("武当", 20)
    for _ in range(10):
        player.record_skill_use("太极剑")
    # Alpha282：晋升外门弟子前须完成武当剑理历练。
    player.set_flag("sect:wudang:sword_principle", True)
    assert player.promote_sect_rank("武当")[0]
    assert player.get_sect_summary("武当")["rank"] == "外门弟子"
