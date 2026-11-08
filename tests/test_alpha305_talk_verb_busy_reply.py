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
    assert len(engine.NPCS) == 77
    for npc_name, info in engine.NPCS.items():
        verb = info.get("talk_verb")
        assert isinstance(verb, str) and verb.strip(), npc_name
        assert re.fullmatch(r"[\u4e00-\u9fff]{2,12}", verb), (npc_name, verb)
        assert verb.endswith("道"), (npc_name, verb)
        assert actor_display.npc_talk_verb(npc_name) == verb


def test_dialogue_line_uses_npc_specific_talk_verb():
    player = player_at_shop()
    value, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "药铺老板 含笑应道：“" in value
    assert "药铺老板 说道：“" not in value
    assert actor_display.npc_talk_verb("铁匠") == "头也不抬道"


def test_talk_verb_falls_back_to_default_for_unknown_npc():
    assert actor_display.npc_talk_verb("查无此人") == "说道"


def test_busy_idle_talk_is_one_short_reply():
    player = make_busy_owner()
    relation_before = player.get_relation("药铺老板")
    clock_before = player.get_quest_clock()
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert result is False
    assert "药铺老板正在坐堂配药，只匆匆应了一声：“稍等，忙完这阵再细说。”" in value
    for text in ("说道", "关系变化", "【可接取委托】", "可选对话", "状态："):
        assert text not in value, text
    assert player.get_relation("药铺老板") == relation_before
    assert player.get_quest_clock() == clock_before
    assert player.get_npc_state("药铺老板") == "busy"


def test_busy_idle_faction_conflict_uses_generic_reply():
    player = make_busy_owner(
        reason="青石村与黑市局势升级至对峙",
        source="faction_conflict:青石村:黑市",
    )
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert result is False
    assert "对峙" not in value
    assert "只匆匆应了你一声，似乎一时脱不开身。" in value
    for text in ("说道", "关系变化", "【可接取委托】"):
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
