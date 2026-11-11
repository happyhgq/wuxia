"""Alpha226：公告栏只给线索，任务由 NPC 对话接取并在原 NPC 处交付。"""
import contextlib
import io

from actions import handle_notice_board, handle_talk_and_ask, handle_quest
from main import _is_direct_quest_accept_command, parse_command
from player import Player


def capture(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def test_notice_board_groups_and_sanitizes_public_messages():
    p = Player("公告线索验收", "散人")
    p.location = "village_square"
    p.learn_player_information("faction_conflict:官府:黑市", "官府与黑市冲突升级。（可信度 85/100｜有效至时辰 87）", "", 85)
    p.learn_player_information("faction_conflict:官府:黑风寨", "官府与黑风寨冲突升级。（可信度 85/100｜有效至时辰 86）", "", 85)
    p.learn_player_information("region:main", "主世界局势变为升级，安全度约为59。", "", 80)
    out = capture(handle_notice_board, p)
    assert "【委托线索】" in out
    # 没有 follow_up 的势力/区域状态不再占公告栏的位置。
    assert "【势力摘要】" not in out
    assert "百草堂主" in out and "打铁铺" in out and "村长" in out
    assert "新手采药·认识资源" not in out
    assert "可信度" not in out and "有效至时辰" not in out and "安全度约为" not in out
    assert "官府与黑市冲突升级" not in out
    assert "官府、黑市、黑风寨" not in out
    # 每条公告都必须给出可去之处与可找之人。
    bullets = [line for line in out.splitlines() if line.startswith("- ")]
    assert bullets and all("——可去【" in line and "】找【" in line for line in bullets)


def test_npc_conversation_accepts_only_that_npcs_quest():
    p = Player("NPC领取验收", "散人")
    p.location = "medicine_shop"
    p.set_flag("newcomer:guide_seen", True)
    out = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托 初入江湖·采药识草"])
    q = "新手采药·认识资源"
    assert "已接取任务" in out and "已加入你的任务列表" in out
    assert q in p.active_quests
    assert "新手伐木·备料" not in p.active_quests


def test_npc_dialogue_reports_progress_and_turn_in_required(monkeypatch):
    p = Player("NPC状态验收", "散人")
    p.location = "medicine_shop"
    p.set_flag("newcomer:guide_seen", True)
    p.active_quests["新手采药·认识资源"] = 2
    p.quest_states["新手采药·认识资源"] = {"stage": 0, "progress": 2}
    p.inventory.extend(["草药", "草药"])
    out = capture(handle_talk_and_ask, p, ["药铺老板", "委托"])
    assert "目标已经办妥" in out
    # 完成目标不自动结算；必须执行交付流程，且原委托 NPC 要在场。
    assert "新手采药·认识资源" in p.active_quests
    p.location = "village_square"
    turn_in = capture(handle_quest, p, "jiaofu", ["新手采药·认识资源"])
    assert "请回到【百草堂主】处交付任务" in turn_in
    assert "新手采药·认识资源" in p.active_quests

    # 正常交付应通过原委托 NPC 的交谈选项完成，并结算一次奖励。
    p.location = "medicine_shop"
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    delivered = capture(handle_talk_and_ask, p, ["药铺老板", "交付委托 初入江湖·采药识草"])
    assert "恭喜完成任务" in delivered
    assert "新手采药·认识资源" not in p.active_quests
    assert "新手采药·认识资源" in p.completed_quests


def test_direct_task_accept_commands_are_blocked_in_game_loop():
    assert _is_direct_quest_accept_command(*parse_command("接取 新手采药·认识资源"))
    assert _is_direct_quest_accept_command(*parse_command("任务 接取 新手采药·认识资源"))
    assert not _is_direct_quest_accept_command(*parse_command("任务"))
    assert not _is_direct_quest_accept_command(*parse_command("交谈 药铺老板 接受委托"))
