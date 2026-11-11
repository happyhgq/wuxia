"""Alpha153：人物面板统一展示门派职位与师承，精简重复查询入口。"""
import contextlib
import io

from actions import handle_sect
from main import show_status
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def huashan_disciple():
    p = Player("面板测试", "散人")
    p.level = 10
    assert p.join_sect("华山")[0]
    p._sect_progress_state().setdefault("华山", {})["official_rank_index"] = 2
    p.location = "huashan_training_ground"
    return p


def test_character_panel_shows_sect_rank_and_no_mentorship_before_apprenticeship():
    p = huashan_disciple()
    out = capture(show_status, p, "sect")
    assert "门派：" in out and "华山" in out
    assert "门派职位：" in out
    assert "师承：" in out and "暂无师承" in out
    assert "师徒关系：" not in out


def test_character_panel_shows_formal_mentor_after_apprenticeship():
    p = huashan_disciple()
    assert p.establish_sect_mentorship()[0]
    out = capture(show_status, p, "sect")
    assert "师承：" in out and "华山授业师父" in out
    assert "师门默契" not in out and "累计请教" not in out


def test_mentorship_query_redirects_to_character_panel_but_actions_remain():
    p = huashan_disciple()
    out = capture(handle_sect, p, ["师徒", "查看"])
    assert "人物面板" in out
    assert "师门默契" not in out
    assert "师父：" not in out
    out = capture(handle_sect, p, ["师徒", "拜师"])
    assert "正式建立师承关系" in out
    out = capture(handle_sect, p, ["师徒", "请教"])
    assert "师门默契提升至" in out


def test_rank_query_redirects_to_character_panel_and_promotion_remains_available():
    p = huashan_disciple()
    out = capture(handle_sect, p, ["身份"])
    assert "人物面板" in out
    assert "正式身份：" not in out
    out = capture(handle_sect, p, ["晋升"])
    assert "晋升" in out or "声望" in out or "基础武学" in out


def test_general_sect_command_no_longer_duplicates_rank_from_character_panel():
    p = huashan_disciple()
    out = capture(handle_sect, p, [])
    assert "门派声望：" in out
    assert "正式身份：" not in out
    assert "声望对应身份：" not in out
