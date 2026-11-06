"""Alpha270：公告栏只展示当前真正可接取的 NPC 委托线索。"""
from actions import handle_notice_board
from player import Player
import contextlib
import io

FOLLOW_UP = "村道回暖·药铺复业"
RESTOCK = "百草备货·补齐药材"


def capture(player):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handle_notice_board(player)
    return out.getvalue()


def test_locked_herb_restock_clue_is_hidden_until_all_prerequisites_are_met():
    player = Player("公告前置过滤", "散人")
    player.location = "village_square"
    before = capture(player)
    assert "常用药材仍有缺口" not in before
    player.completed_quests.append("新手采药·认识资源")
    player.set_flag("quest_completed:新手采药·认识资源", True)
    player.set_flag("quest_completed:" + FOLLOW_UP, True)
    after_one = capture(player)
    assert "常用药材仍有缺口" not in after_one
    player.set_flag("world:main:herb_trade_resumed", True)
    after_all = capture(player)
    assert "常用药材仍有缺口" in after_all
    assert RESTOCK not in after_all
    assert "接受委托" not in after_all


def test_accepted_and_delivered_quest_clues_are_removed_from_board():
    player = Player("公告任务状态", "散人")
    player.location = "village_square"
    player.completed_quests.append("新手采药·认识资源")
    player.set_flag("quest_completed:新手采药·认识资源", True)
    player.set_flag("quest_completed:" + FOLLOW_UP, True)
    player.set_flag("world:main:herb_trade_resumed", True)
    assert "常用药材仍有缺口" in capture(player)
    player.active_quests[RESTOCK] = 0
    assert "常用药材仍有缺口" not in capture(player)
    player.active_quests.pop(RESTOCK)
    player.completed_quests.append(RESTOCK)
    assert "常用药材仍有缺口" not in capture(player)


def test_busy_quest_giver_still_publishes_available_clue():
    player = Player("公告忙碌不拦截", "散人")
    player.location = "village_square"
    player.set_npc_state("村长", "busy", duration=10, reason="处理村中事务")
    out = capture(player)
    # 忙碌只是状态描述，不改变公告线索的接取资格；未开放的后续委托仍不应提前公布。
    assert "村外野猪近日滋扰村民" in out
    assert "村长正在寻找能清理残匪的人手" not in out


def test_only_one_currently_available_clue_per_giver_is_published():
    player = Player("公告同人去重", "散人")
    player.location = "village_square"
    out = capture(player)
    # 村长名下存在多条分阶段委托，但起始阶段只展示当前可接的一条。
    assert out.count("村长") <= 2  # 一条线索及可能的自然语言正文，不泄漏多条委托清单
    assert "黑风山道仍有山贼拦路" not in out
