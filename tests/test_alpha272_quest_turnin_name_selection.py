"""Alpha272：任务交付名称容错与多候选序号选择。"""
from contextlib import redirect_stdout
from io import StringIO

from actions import handle_talk_and_ask
from player import Player


QUESTS = ["新手伐木·备料", "新手采矿·寻铁"]


def capture(fn, *args):
    out = StringIO()
    with redirect_stdout(out):
        fn(*args)
    return out.getvalue()


def ready_blacksmith_player():
    player = Player("交付选择验收", "散人")
    player.location = "blacksmith"
    for quest in QUESTS:
        player.active_quests[quest] = 2
        player.quest_states[quest] = {"stage": 0, "progress": 2}
    player.inventory.extend(["木材", "木材", "铁矿石", "铁矿石"])
    return player


def test_delivery_accepts_title_without_middle_dot(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = ready_blacksmith_player()

    out = capture(handle_talk_and_ask, player, ["铁匠", "交付委托", "初入江湖备些木料"])

    assert "恭喜完成任务" in out
    assert QUESTS[0] in player.completed_quests
    assert QUESTS[1] in player.active_quests


def test_ambiguous_short_name_lists_numbered_candidates(monkeypatch):
    player = ready_blacksmith_player()

    out = capture(handle_talk_and_ask, player, ["铁匠", "交付委托", "初入江湖"])

    assert "对应多项委托" in out
    assert "1 初入江湖·备些木料" in out
    assert "2 初入江湖·寻找铁矿" in out
    assert "交谈 王铁匠 交付委托 任务名称" in out


def test_delivery_can_be_selected_by_number_in_command_or_followup(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = ready_blacksmith_player()

    # 指令内序号。
    out = capture(handle_talk_and_ask, player, ["铁匠", "交付委托", "2"])
    assert "恭喜完成任务" in out
    assert QUESTS[1] in player.completed_quests

    # 提示后的独立数字输入。
    player = ready_blacksmith_player()
    capture(handle_talk_and_ask, player, ["铁匠", "交付委托"])
    out = capture(handle_talk_and_ask, player, ["铁匠", "1"])
    assert "恭喜完成任务" in out
    assert QUESTS[0] in player.completed_quests


def test_missing_delivery_name_shows_valid_candidates():
    player = ready_blacksmith_player()

    out = capture(handle_talk_and_ask, player, ["铁匠", "交付委托", "完全不存在的委托"])

    assert "未找到委托" in out
    assert "1 初入江湖·备些木料" in out
    assert "2 初入江湖·寻找铁矿" in out
