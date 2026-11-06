"""Alpha199：跨门派历史武学记录、实战权限与 V12 存读档一致性。"""
from player import Player


def test_foreign_historical_skill_keeps_mastery_but_cannot_gain_more():
    player = Player("跨门派历史记录", "少林")
    before = player.get_skill_progress("罗汉拳")
    assert before["learned"]
    player.record_skill_use("罗汉拳", True)
    progressed = player.get_skill_progress("罗汉拳")
    assert progressed["mastery"] >= before["mastery"]

    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]
    locked_before = player.get_skill_progress("罗汉拳")
    player.record_skill_use("罗汉拳", True)
    locked_after = player.get_skill_progress("罗汉拳")

    assert locked_after["learned"]
    assert locked_after["mastery"] == locked_before["mastery"]
    assert "罗汉拳" not in [skill["name"] for skill in player.get_available_skills()]


def test_cross_sect_skill_history_survives_v12_save_load(tmp_path, capsys):
    player = Player("跨门派存读档", "少林")
    player.record_skill_use("罗汉拳", True)
    expected = player.get_skill_progress("罗汉拳")
    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]
    path = tmp_path / "skill_lifecycle_v12.json"

    assert player.save_to_file(str(path))
    loaded = Player.load_from_file(str(path))
    capsys.readouterr()

    assert loaded is not None
    assert loaded.get_sect() == "武当"
    actual = loaded.get_skill_progress("罗汉拳")
    assert actual["learned"] == expected["learned"]
    assert actual["mastery"] == expected["mastery"]
    assert "罗汉拳" not in [skill["name"] for skill in loaded.get_available_skills()]


def test_rejoining_original_sect_does_not_restore_departed_official_rank():
    player = Player("重新拜入身份重置", "少林")
    player._sect_progress_state().setdefault("少林", {})["official_rank_index"] = 3
    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]
    assert player.leave_sect()[0]
    assert player.join_sect("少林")[0]
    assert player.get_sect_official_rank_index("少林") == 0
