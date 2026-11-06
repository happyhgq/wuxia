"""Alpha198：历史已学武学不能绕过当前正式门派职位限制。"""
from actions import handle_skills
from player import Player


def _promote_to(p, rank_index):
    p._sect_progress_state().setdefault(p.get_sect(), {})["official_rank_index"] = rank_index


def test_high_rank_skill_becomes_unavailable_after_leave_and_rejoin():
    p = Player("高阶武学身份门槛", "少林")
    p.level = 20
    p.change_sect_reputation("少林", 100)
    _promote_to(p, 3)
    assert p.learn_skill("金刚伏魔拳")[0]
    assert "金刚伏魔拳" in [x["name"] for x in p.get_available_skills()]

    assert p.leave_sect()[0]
    assert p.join_sect("少林")[0]
    assert p.get_skill_progress("金刚伏魔拳")["learned"]  # 历史修习保留
    assert "金刚伏魔拳" not in [x["name"] for x in p.get_available_skills()]
    summary = {x["name"]: x for x in p.get_skill_summary()}
    assert summary["金刚伏魔拳"]["learned"]
    assert not summary["金刚伏魔拳"]["usable"]


def test_high_rank_skill_returns_when_official_rank_is_restored():
    p = Player("恢复职位后重开武学", "少林")
    p.level = 20
    p.change_sect_reputation("少林", 100)
    _promote_to(p, 3)
    assert p.learn_skill("金刚伏魔拳")[0]
    assert p.leave_sect()[0]
    assert p.join_sect("少林")[0]
    _promote_to(p, 3)
    assert "金刚伏魔拳" in [x["name"] for x in p.get_available_skills()]


def test_skill_panel_explains_learned_but_rank_locked_skill(capsys):
    p = Player("武学面板身份提示", "少林")
    p.level = 20
    p.change_sect_reputation("少林", 100)
    _promote_to(p, 3)
    assert p.learn_skill("金刚伏魔拳")[0]
    assert p.leave_sect()[0]
    assert p.join_sect("少林")[0]
    handle_skills(p)
    assert "当前职位不足，暂不可施展" in capsys.readouterr().out
