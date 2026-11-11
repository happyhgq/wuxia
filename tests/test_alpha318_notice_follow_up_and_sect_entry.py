"""Alpha318：公告栏可行动线索与入门/授阶/师承等级。"""
import contextlib
import io

import engine
from actions import (
    _board_section_for,
    _public_information_records,
    _sect_entry_level,
    handle_notice_board,
    handle_sect,
    handle_skills,
)
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def joined_sect(sect, level=10):
    p = Player(f"Alpha318{sect}测试", "散人")
    p.level = level
    assert p.join_sect(sect)[0]
    return p


def test_every_npc_information_entry_has_actionable_follow_up():
    total = 0
    for npc_name, data in engine.NPCS.items():
        for entry in data.get("information") or []:
            total += 1
            follow_up = entry.get("follow_up") or {}
            assert follow_up.get("npc") or follow_up.get("room"), (
                f"{npc_name}/{entry.get('topic')} 缺少可找的人物或可去的房间"
            )
    assert total >= 9


def test_notice_board_only_renders_messages_with_actionable_follow_up():
    p = Player("公告栏可行动测试", "散人")
    p.location = "guiyun_central_square"
    p.learn_player_information(
        "guard_patrol_alert", "村口近日加强了盘查。", "测试", 80,
        follow_up={"npc": "守卫", "room": "village_gate", "hint": "可问清盘查缘由"},
    )
    p.learn_player_information("village_background", "这只是没有下文的背景话。", "测试", 80)

    actionable = _public_information_records(p, require_follow_up=True)
    texts = [record["text"] for record in actionable]
    assert "村口近日加强了盘查。" in texts
    assert "这只是没有下文的背景话。" not in texts

    out = capture(handle_notice_board, p)
    assert "村口近日加强了盘查。" in out
    assert "——可去【青石村口】找【青石村守卫】（交谈 青石村守卫，可问清盘查缘由）" in out
    assert "这只是没有下文的背景话。" not in out
    assert "暂无后续" not in out
    assert "势力摘要" not in out
    assert "可信度" not in out
    assert "guard_patrol_alert" not in out


def test_notice_board_groups_rumors_and_local_news_separately():
    assert _board_section_for("new_wulin_rumor", "江湖传闻") == "江湖见闻"
    assert _board_section_for("guard_patrol_alert", "官府消息") == "地方消息"
    assert _board_section_for("faction:官府:黑市", "势力消息") == "地方消息"


def test_sect_entry_level_is_data_driven(monkeypatch):
    for sect in ("少林", "武当", "华山", "铁衣门"):
        assert _sect_entry_level(sect) == engine.SECTS[sect]["entry_level"] == 3
    assert _sect_entry_level("散人") == 1

    p = Player("入门等级数据驱动测试", "散人")
    p.level = 2
    ok, message = p.can_join_sect("华山")
    assert not ok and "需达到 3 级" in message

    # 修改数据即改变门槛，证明代码没有写死 10 级或 3 级。
    monkeypatch.setitem(engine.SECTS["华山"], "entry_level", 7)
    p.level = 5
    ok, message = p.can_join_sect("华山")
    assert not ok and "需达到 7 级" in message
    p.level = 7
    assert p.can_join_sect("华山")[0]


def test_first_two_promotions_require_level_five_and_ten():
    for sect in ("少林", "武当", "华山", "铁衣门"):
        p = joined_sect(sect, level=3)
        assert p.get_sect_promotion_requirements(sect)["required_level"] == 5
        p._sect_progress_state()[sect]["official_rank_index"] = 1
        assert p.get_sect_promotion_requirements(sect)["required_level"] == 10


def test_wanderer_learns_basic_skill_from_jianghu_teacher_at_village_square_only():
    p = Player("散人武师传授测试", "散人")
    p.level = 3
    p.location = "village_gate"
    out = capture(handle_skills, p, ["学习", "江湖散手"])
    assert "学习本门武学须前往村中广场" in out
    assert not p.get_skill_progress("江湖散手")["learned"]

    p.location = "village_square"
    assert "江湖武师" in p.get_npcs_in_room(p.location)
    out = capture(handle_skills, p, ["学习", "江湖散手"])
    assert "你已学会【江湖散手】" in out
    assert p.get_skill_progress("江湖散手")["learned"]


def test_mentorship_entry_available_for_all_four_sects_at_inner_rank():
    sects = {
        "少林": "shaolin_training_ground",
        "武当": "wudang_training_ground",
        "华山": "huashan_training_ground",
        "铁衣门": "tieyi_training_ground",
    }
    for sect, room_id in sects.items():
        p = joined_sect(sect, level=10)
        p._sect_progress_state()[sect]["official_rank_index"] = 2
        p.location = room_id
        out = capture(handle_sect, p, ["师徒", "拜师"])
        assert "正式建立师承关系" in out, f"{sect} 拜师失败：{out}"
        assert p.get_sect_mentorship(sect).get("mentor")


def test_mentorship_entry_blocked_below_inner_rank_or_level():
    p = joined_sect("华山", level=10)
    p._sect_progress_state()["华山"]["official_rank_index"] = 1
    p.location = "huashan_training_ground"
    out = capture(handle_sect, p, ["师徒", "拜师"])
    assert "拜师须先成为【华山】内门弟子" in out
    assert not p.get_sect_mentorship("华山")

    p._sect_progress_state()["华山"]["official_rank_index"] = 2
    p.level = 9
    out = capture(handle_sect, p, ["师徒", "拜师"])
    assert "人物等级需达到 10 级" in out
    assert not p.get_sect_mentorship("华山")


def test_wanderer_has_no_sect_mentorship_entry():
    p = Player("散人师承入口测试", "散人")
    p.location = "village_square"
    out = capture(handle_sect, p, ["师徒", "拜师"])
    assert "师承事务目前仅在少林、武当、华山与铁衣门开放" in out


def test_legacy_save_without_official_rank_record_keeps_reputation_rank():
    p = Player("Alpha318旧存档身份测试", "华山")
    p.change_sect_reputation("华山", 50)
    p._sect_progress_state().pop("华山", None)
    assert p.get_sect_official_rank_index("华山") == 2
    assert p.get_sect_official_rank("华山") == "内门弟子"
    # 旧角色不会被降阶；后续晋升按新数据从当前身份继续。
    assert p.get_sect_promotion_requirements("华山")["required_level"] == 15
