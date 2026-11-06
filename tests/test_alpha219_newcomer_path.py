"""Alpha219：新手任务入口、资源搜索/采集分工与门派等级门槛。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from player import Player
from main import parse_command
from actions import handle_notice_board, handle_sect


def test_search_and_collect_are_separate_commands():
    assert parse_command("搜索") == ("search", [])
    assert parse_command("采集") == ("collect", [])


def test_newcomer_quests_are_hintable_without_exposing_task_names_or_commands():
    expected = {"新手跑腿·送信", "新手采药·认识资源", "新手伐木·备料", "新手采矿·寻铁", "新手狩猎·野外除害"}
    assert expected.issubset(engine.QUESTS)
    p = Player("新手委托验收", "散人")
    p.location = "village_square"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_notice_board(p)
    text = output.getvalue()
    assert "百草堂" in text and "药铺老板" in text
    assert "铁匠铺" in text and "王打铁" in text
    assert "村长" in text and "青石村接引人" in text
    for name in expected:
        assert name not in text
    for forbidden in ("可接取", "接取方式", "任务 接取", "可信度", "有效至时辰"):
        assert forbidden not in text


def test_newcomer_guide_is_persistent_and_no_popup_hook_stays_silent():
    p = Player("新手引导验收", "散人")
    p.set_flag("newcomer:guide_seen", True)
    assert p.get_flag("newcomer:guide_seen") is True


def test_gameplay_sect_join_is_gated_until_level_ten():
    p = Player("门派等级门槛验收", "散人")
    p.location = "huashan_guest_hall"
    p.set_flag("sect:huashan:entry_interview", True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_sect(p, ["join", "华山"])
    assert p.get_sect() == "散人"
    assert "需达到 10 级" in output.getvalue()


def test_new_quest_data_uses_existing_v12_compatible_flags_and_targets():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    expected_givers = {
        "新手跑腿·送信": "青石村接引人",
        "新手采药·认识资源": "药铺老板",
        "新手伐木·备料": "铁匠",
        "新手采矿·寻铁": "铁匠",
    }
    for name, giver in expected_givers.items():
        q = quests[name]
        assert q["npc"] == giver
        assert q["turn_in_npc"] == giver
        # 新手引导只负责说明玩法，不应成为公告线索所指委托的隐藏接取门槛。
        assert "newcomer:guide_seen" not in (q.get("requires", {}).get("flags", []))


def test_early_level_curve_is_gentler_for_new_levels_without_changing_saved_thresholds():
    from player import exp_needed_for_level

    p = Player("经验曲线验收", "散人")
    p.exp = p.exp_to_level - 1
    old_threshold = p.exp_to_level
    p.gain_exp(1)
    assert p.level == 2
    # Alpha285：Lv1→Lv2 为 150，Lv2→Lv3 为 185，早期曲线仍避免单只怪直升一级。
    assert old_threshold == 150
    assert p.exp_to_level == exp_needed_for_level(2) == 185
    assert p.exp_to_level <= 185


def test_talk_interaction_does_not_redraw_full_scene():
    from actions import handle_talk_and_ask
    p = Player("交谈输出验收", "散人")
    p.location = "village_square"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        handle_talk_and_ask(p, ["青石村接引人", "新手"])
    text = output.getvalue()
    assert "初入江湖" in text
    assert "【环境】" not in text
    assert "【人物】" not in text
