"""Alpha243：新玩家第一次找任务 NPC 时，不会被隐藏的新手引导前置卡住。"""
import contextlib
import io

from actions import handle_talk_and_ask, handle_quest
from player import Player


def capture(fn, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def test_fresh_player_can_accept_guide_quest_without_extra_hidden_step():
    player = Player("新手委托流程", "散人")
    player.location = "village_square"
    assert not player.get_flag("newcomer:guide_seen")

    # 玩家按公告线索直接询问/接受委托，不必先额外输入一次无话题交谈。
    out = capture(handle_talk_and_ask, player, ["青石村接引人", "接受委托", "初入江湖·替村民送信"])
    assert "已接取任务" in out
    assert "已加入你的任务列表" in out
    assert player.get_flag("newcomer:guide_seen")
    assert "新手跑腿·送信" in player.active_quests

    task_list = capture(handle_quest, player, "quests", [])
    assert "初入江湖·替村民送信" in task_list
    assert "新手跑腿·送信" not in task_list


def test_fresh_player_can_ask_guide_for_quests_then_accept_without_second_tutorial():
    player = Player("新手先问委托", "散人")
    player.location = "village_square"

    offer = capture(handle_talk_and_ask, player, ["青石村接引人", "委托"])
    assert player.get_flag("newcomer:guide_seen")
    assert "初入江湖·替村民送信" in offer
    assert "接受委托" in offer

    accepted = capture(handle_talk_and_ask, player, ["青石村接引人", "接受委托", "初入江湖·替村民送信"])
    assert "已接取任务" in accepted
    assert "新手跑腿·送信" in player.active_quests


def test_busy_guide_can_accept_quest_and_complete_tutorial_prerequisite():
    player = Player("忙碌接引人", "散人")
    player.location = "village_square"
    player.set_npc_state("青石村接引人", "busy", duration=20, reason="接待其他来客")

    out = capture(handle_talk_and_ask, player, ["青石村接引人", "接受委托", "初入江湖·替村民送信"])
    assert "状态：" not in out
    assert "已接取任务" in out
    assert player.get_flag("newcomer:guide_seen")
    assert "新手跑腿·送信" in player.active_quests


def test_new_player_can_accept_progress_fail_wrong_turn_in_then_deliver_once(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("完整新手流程", "散人")
    player.location = "village_square"
    qid = "新手跑腿·送信"

    accepted = capture(handle_talk_and_ask, player, ["青石村接引人", "接受委托", "初入江湖·替村民送信"])
    assert "已接取任务" in accepted and qid in player.active_quests

    # 任务目标：去村长处传话。真实交谈必须推进目标，而不是只显示 NPC 对话。
    player.location = "village_head_house"
    progress = capture(handle_talk_and_ask, player, ["村长"])
    assert "任务更新" in progress
    assert player.active_quests[qid] == 1
    task_list = capture(handle_quest, player, "quests", [])
    assert "初入江湖·替村民送信" in task_list and "1/1" in task_list

    # 找错 NPC 交付时不得结算奖励，也不能移除活动任务。
    before_gold = player.gold
    player.location = "medicine_shop"
    wrong = capture(handle_talk_and_ask, player, ["药铺老板", "交付委托", "初入江湖·替村民送信"])
    assert "原委托人" in wrong and "青石村接引人" in wrong
    assert qid in player.active_quests and player.gold == before_gold

    # 回原委托人处交付，任务状态完成并发奖；再次交付不能重复发奖。
    player.location = "village_square"
    delivered = capture(handle_talk_and_ask, player, ["青石村接引人", "交付委托", "初入江湖·替村民送信"])
    assert "恭喜完成任务" in delivered
    assert qid not in player.active_quests and qid in player.completed_quests
    assert player.gold == before_gold + 20
    after_delivery_gold = player.gold
    again = capture(handle_talk_and_ask, player, ["青石村接引人", "交付委托", "初入江湖·替村民送信"])
    assert player.gold == after_delivery_gold
    assert "这件事已经办妥" in again


def test_all_five_starter_quests_are_acceptible_without_first_visiting_the_guide():
    starter_quests = [
        ("新手跑腿·送信", "青石村接引人", "village_square", "初入江湖·替村民送信"),
        ("新手采药·认识资源", "药铺老板", "medicine_shop", "初入江湖·采药识草"),
        ("新手伐木·备料", "铁匠", "blacksmith", "初入江湖·备些木料"),
        ("新手采矿·寻铁", "铁匠", "blacksmith", "初入江湖·寻找铁矿"),
        ("新手狩猎·野外除害", "村长", "village_head_house", "初入江湖·野外除害"),
    ]
    for qid, npc, location, public_title in starter_quests:
        player = Player(f"直接领取-{qid}", "散人")
        player.location = location
        assert not player.get_flag("newcomer:guide_seen")
        out = capture(handle_talk_and_ask, player, [npc, "接受委托", public_title])
        assert "已接取任务" in out, (qid, out)
        assert qid in player.active_quests, qid
        task_list = capture(handle_quest, player, "quests", [])
        assert public_title in task_list, (qid, task_list)
        assert qid not in task_list, (qid, task_list)
