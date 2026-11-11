"""Alpha157：武学面板以正式职位名称展示学习门槛。"""
from actions import handle_skills
from player import Player


def joined(sect):
    player = Player("武学提示测试", "散人")
    player.level = max(player.level, 3)
    assert player.join_sect(sect)[0]
    return player


def test_skill_list_uses_rank_names_instead_of_numeric_stage_for_shaolin(capsys):
    player = joined("少林")
    handle_skills(player, [])
    output = capsys.readouterr().out
    assert "职位 僧人" in output
    assert "身份第 3 阶" not in output


def test_skill_detail_uses_rank_name_for_wudang(capsys):
    player = joined("武当")
    handle_skills(player, ["详情", "绵掌"])
    output = capsys.readouterr().out
    assert "正式职位：外门弟子" in output
    assert "身份第 3 阶" not in output


def test_skill_detail_uses_rank_name_for_huashan(capsys):
    player = joined("华山")
    handle_skills(player, ["详情", "夺命连环三仙剑"])
    output = capsys.readouterr().out
    assert "正式职位：外门弟子" in output
    assert "身份第 3 阶" not in output
