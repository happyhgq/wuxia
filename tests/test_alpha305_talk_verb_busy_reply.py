"""Alpha305：固定 NPC 对话动词与忙碌短应答。"""
import contextlib
import io
import re

import actor_display
import engine
from actions import handle_talk_and_ask
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return _ANSI_RE.sub("", stream.getvalue()), result


def player_at_shop(tick=0):
    player = Player("对话措辞验收")
    player.location = "medicine_shop"
    player.set_var("quest_clock", tick)
    return player


def make_busy_owner(reason="正在坐堂配药", source=""):
    player = player_at_shop()
    player.set_npc_state("药铺老板", "busy", duration=5, reason=reason, source=source)
    return player


def test_all_fixed_npcs_define_verbal_talk_verb():
    assert len(engine.NPCS) == 81
    for npc_name, info in engine.NPCS.items():
        verb = info.get("talk_verb")
        assert isinstance(verb, str) and verb.strip(), npc_name
        assert re.fullmatch(r"[\u4e00-\u9fff]{2,12}", verb), (npc_name, verb)
        assert verb.endswith("道"), (npc_name, verb)
        assert actor_display.npc_talk_verb(npc_name) == verb


def test_dialogue_line_uses_npc_specific_talk_verb():
    player = player_at_shop()
    value, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "百草堂主 含笑应道：“" in value
    assert "药铺老板 说道：“" not in value
    assert actor_display.npc_talk_verb("铁匠") == "头也不抬道"


def test_talk_verb_falls_back_to_default_for_unknown_npc():
    assert actor_display.npc_talk_verb("查无此人") == "说道"


def test_busy_idle_talk_keeps_short_reply_but_still_lists_quests():
    player = make_busy_owner()
    relation_before = player.get_relation("药铺老板")
    clock_before = player.get_quest_clock()
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert result is False
    assert "百草堂主正在坐堂配药，只匆匆应了一声：“稍等，忙完这阵再细说。”" in value
    # 忙碌只省寒暄；委托入口不能被吞掉，否则忙碌时段无法接取或交付。
    assert "【可接取委托】" in value
    for text in ("说道", "关系变化", "可选对话", "状态："):
        assert text not in value, text
    assert player.get_relation("药铺老板") == relation_before
    assert player.get_quest_clock() == clock_before
    assert player.get_npc_state("药铺老板") == "busy"


def test_busy_idle_npc_without_quests_still_gives_one_short_reply():
    player = Player("忙碌无委托验收")
    player.location = "village_gate"
    player.set_npc_location("守卫", "village_gate")
    player.set_npc_state("守卫", "busy", duration=5, reason="正在巡查门禁")
    value, result = capture(handle_talk_and_ask, player, ["守卫"])
    assert result is False
    assert "正在巡查门禁，只匆匆应了一声：“稍等，忙完这阵再细说。”" in value
    for text in ("【可接取委托】", "【可交付委托】", "【进行中委托】"):
        assert text not in value, text


def test_busy_idle_faction_conflict_uses_generic_reply_but_keeps_quests():
    player = make_busy_owner(
        reason="青石村与黑市局势升级至对峙",
        source="faction_conflict:青石村:黑市",
    )
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert result is False
    assert "对峙" not in value
    assert "只匆匆应了你一声，似乎一时脱不开身。" in value
    assert "【可接取委托】" in value
    for text in ("说道", "关系变化"):
        assert text not in value, text


def test_busy_idle_repeated_talk_keeps_npc_present_and_clock_still():
    player = make_busy_owner()
    clock_before = player.get_quest_clock()
    for _ in range(3):
        value, result = capture(handle_talk_and_ask, player, ["药铺老板"])
        assert result is False
        assert "只匆匆应了一声" in value
        assert "药铺老板" in player.get_npcs_in_room("medicine_shop")
    assert player.get_quest_clock() == clock_before
    assert player.get_relation("药铺老板") == 0


def test_busy_faction_affected_quest_giver_accepts_and_delivers(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = Player("忙碌委托验收", "散人")
    player.location = "village_head_house"
    player.set_npc_location("村长", "village_head_house")
    player.set_npc_state(
        "村长", "busy", duration=4,
        reason="青石村与黑风寨局势升级至escalation",
        source="faction_conflict:青石村:黑风寨",
    )

    offered, result = capture(handle_talk_and_ask, player, ["村长"])
    assert result is False
    assert "【可接取委托】" in offered
    assert "初入江湖·野外除害" in offered

    accepted, _ = capture(handle_talk_and_ask, player, ["村长", "接受委托", "初入江湖·野外除害"])
    assert "已接取任务" in accepted
    quest = "新手狩猎·野外除害"
    assert quest in player.active_quests

    player.active_quests[quest] = 1
    player.quest_states[quest] = {"stage": 0, "progress": 1}
    pending, _ = capture(handle_talk_and_ask, player, ["村长"])
    assert "【可交付委托】" in pending

    delivered, _ = capture(handle_talk_and_ask, player, ["村长", "交付", "初入江湖·野外除害"])
    assert "恭喜完成任务" in delivered
    assert quest in player.completed_quests


def test_busy_talk_with_topic_still_reaches_quests():
    player = make_busy_owner()
    value, result = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])
    assert result is None
    assert "【可接取委托】" in value
    assert "只匆匆应了一声" not in value
    assert "无暇交谈" not in value


def test_busy_guide_still_shows_tutorial_instead_of_short_reply():
    player = Player("忙碌接引人引导")
    player.location = "village_square"
    player.set_npc_state("青石村接引人", "busy", duration=5, reason="接待其他来客")
    value, result = capture(handle_talk_and_ask, player, ["青石村接引人"])
    assert result is False
    assert "初入江湖" in value
    assert "接待其他来客" in value
    assert "只匆匆应了一声" not in value
    assert player.get_flag("newcomer:guide_seen")
