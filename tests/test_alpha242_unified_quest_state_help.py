"""Alpha242：全任务状态机、交谈/ask、帮助和公告栏统一验收。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_notice_board, handle_talk_and_ask, _quest_npc_status
from main import parse_command, show_help
from player import Player


def capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def test_all_quest_definitions_have_valid_giver_and_turn_in_locations():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    rooms = json.loads(Path("data/rooms.json").read_text(encoding="utf-8"))
    assert len(quests) == 82
    for qid, info in quests.items():
        giver = info.get("npc")
        turn_in = info.get("turn_in_npc") or giver
        assert giver in engine.NPCS, (qid, giver)
        assert turn_in in engine.NPCS, (qid, turn_in)
        assert any(giver in room.get("npcs", []) for room in rooms.values()), (qid, giver)
        assert any(turn_in in room.get("npcs", []) for room in rooms.values()), (qid, turn_in)


def test_gated_quest_shows_specific_prerequisite_without_objective_or_activation():
    p = Player("条件不足验收", "散人")
    p.location = "village_head_house"
    qid = "村道巡查·清理残匪"
    state, detail = _quest_npc_status(p, qid)
    assert state == "未开放"
    assert "初入江湖·野外除害" in detail
    out = capture(handle_talk_and_ask, p, ["村长", "接受委托", qid])
    assert "需先完成并交付【初入江湖·野外除害】" in out
    assert "击退两名山贼" not in out
    assert qid not in p.active_quests
    assert qid not in p.completed_quests


def test_successful_acceptance_is_visible_in_task_list_and_duplicate_is_blocked():
    p = Player("任务列表验收", "散人")
    p.location = "medicine_shop"
    p.set_flag("newcomer:guide_seen", True)
    qid = "新手采药·认识资源"
    first = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托", qid])
    assert "已接取任务" in first and "已加入你的任务列表" in first
    assert qid in p.active_quests
    second = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托", qid])
    assert "已经接取" in second or "事情还没办完" in second
    assert list(p.active_quests).count(qid) == 1


def test_ask_and_chinese_talk_share_same_command_mapping():
    assert parse_command("交谈 药铺老板 委托") == parse_command("ask 药铺老板 委托")


def test_busy_npc_accepts_quest_without_objective_leak():
    p = Player("忙碌状态验收", "散人")
    p.location = "village_head_house"
    p.set_flag("quest_completed:新手狩猎·野外除害", True)
    p.set_npc_state("村长", "busy", duration=20, reason="处理村务")
    out = capture(handle_talk_and_ask, p, ["村长", "接受委托", "村道巡查·清理残匪"])
    assert "状态：" not in out
    assert "已接取任务" in out
    assert "击退两名山贼" not in out
    assert "村道巡查·清理残匪" in p.active_quests


def test_task_help_explains_two_step_flow_status_and_no_pipe_syntax():
    out = capture(show_help, "任务")
    for phrase in ("交谈与 ask", "先了解委托", "接受委托", "未领取", "已领取未完成", "可交付", "已交付", "原委托人", "公告栏只提供线索", "任务 选择 任务名称 分支名称"):
        assert phrase in out, phrase
    assert "不需要竖线" in out


def test_notice_board_has_total_cap_and_no_internal_telemetry():
    p = Player("公告条数验收", "散人")
    p.location = "village_square"
    for i in range(15):
        p.learn_player_information(
            f"new_wulin_rumor:{i}",
            f"江湖见闻 {i}。（可信度 80/100｜有效至时辰 {i+10}）",
            "", 80, follow_up={"npc": "说书先生", "room": "guiyun_tea_room", "hint": "可打听江湖传闻"},
        )
    out = capture(handle_notice_board, p)
    assert "可信度" not in out and "有效至时辰" not in out and "安全度约为" not in out
    # Count bullet items only; headings and the final guidance are not message rows.
    assert sum(1 for line in out.splitlines() if line.startswith("- ")) <= 7


def test_delivery_to_wrong_npc_explains_original_turn_in_person():
    p = Player("找错交付人验收", "散人")
    p.location = "medicine_shop"
    qid = "入城引路"
    p.active_quests[qid] = 1
    p.quest_states[qid] = {"stage": 0, "progress": 1}
    out = capture(handle_talk_and_ask, p, ["药铺老板", "交付委托", qid])
    assert "不是" in out and "原委托人" in out and "归云城守门校尉" in out
    assert qid in p.active_quests
