"""Alpha186：门派武学面板与实战可用范围保持一致。"""
from actions import handle_skills
from player import Player


def test_foreign_sect_skill_detail_marks_historical_record_as_unusable(capsys):
    player = Player("跨门派武学查看", "少林")
    before = player.get_skill_progress("罗汉拳")
    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]

    handle_skills(player, ["详情", "罗汉拳"])
    output = capsys.readouterr().out

    assert "属于【少林】门派传承武学" in output
    assert "不能在当前身份下修习或施展" in output
    assert "不代表当前可用" in output
    assert "罗汉拳" not in [skill["name"] for skill in player.get_available_skills()]
    assert player.get_skill_progress("罗汉拳")["mastery"] == before["mastery"]


def test_current_sect_skill_detail_keeps_normal_mastery_display(capsys):
    player = Player("本门武学查看", "武当")
    handle_skills(player, ["详情", "太极剑"])
    output = capsys.readouterr().out
    assert "熟练度" in output
    assert "不能在当前身份下修习或施展" not in output


def test_switching_back_to_original_sect_restores_only_that_sects_available_skills():
    player = Player("往返门派武学", "少林")
    assert player.leave_sect()[0]
    assert player.join_sect("武当")[0]
    assert "罗汉拳" not in [skill["name"] for skill in player.get_available_skills()]
    assert player.leave_sect()[0]
    assert player.join_sect("少林")[0]
    available = [skill["name"] for skill in player.get_available_skills()]
    assert "罗汉拳" in available
    assert "太极剑" not in available
