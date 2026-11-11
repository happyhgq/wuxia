"""Alpha187：跨门派查看历史武学时，不得修改或清除历史记录。"""
from actions import handle_skills
from player import Player


def test_foreign_sect_skill_cannot_be_forgotten_after_switching_sects():
    player = Player("跨门派历史记录", "少林")
    before = player.get_skill_progress("罗汉拳")
    assert before["learned"]
    assert player.leave_sect()[0]
    player.level = max(player.level, 3)
    assert player.join_sect("武当")[0]

    ok, message = player.forget_skill("罗汉拳")

    assert not ok
    assert "其他门派" in message
    after = player.get_skill_progress("罗汉拳")
    assert after["learned"] == before["learned"]
    assert after["mastery"] == before["mastery"]


def test_foreign_sect_forget_command_explains_history_is_preserved(capsys):
    player = Player("跨门派遗忘指令", "少林")
    assert player.leave_sect()[0]
    player.level = max(player.level, 3)
    assert player.join_sect("武当")[0]

    handle_skills(player, ["遗忘", "罗汉拳"])
    output = capsys.readouterr().out

    assert "其他门派" in output
    assert "不能遗忘或修改这段历史修习记录" in output
    assert player.get_skill_progress("罗汉拳")["learned"]


def test_current_sect_skill_can_still_be_forgotten():
    player = Player("本门遗忘武学", "武当")
    assert player.get_skill_progress("太极剑")["learned"]

    ok, _ = player.forget_skill("太极剑")

    assert ok
    assert not player.get_skill_progress("太极剑")["learned"]
