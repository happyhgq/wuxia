"""Alpha276：忙碌只作状态描述；任务显示名与旧名别名的统一验收。"""
import contextlib
import io

from actions import (
    _resolve_npc_quest_name,
    handle_quest,
    handle_talk_and_ask,
    handle_trading,
    look,
)
from player import Player


HERB_QUEST = "新手采药·认识资源"
HERB_TITLE = "初入江湖·采药识草"
RESTOCK_QUEST = "百草备货·补齐药材"


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return stream.getvalue(), result


def make_busy_herbalist(reason="正在坐堂配药"):
    player = Player("忙碌交互验收", "散人")
    player.location = "medicine_shop"
    player.set_npc_state("药铺老板", "busy", duration=20, reason=reason)
    return player


def prepare_deliverable(player, quest_name=HERB_QUEST, count=2):
    player.active_quests[quest_name] = count
    player.quest_states[quest_name] = {"stage": 0, "progress": count}
    player.inventory.extend(["草药"] * count)


def test_busy_npc_remains_listed_and_enters_normal_dialogue():
    player = make_busy_herbalist()
    before = player.get_npc_location("药铺老板", refresh=False)
    assert "药铺老板" in player.get_npcs_in_room("medicine_shop")

    scene, _ = capture(look, player)
    assert "百草堂主" in scene.split("【人物】", 1)[1]

    output, result = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])
    assert result is None
    assert "状态：" not in output
    assert "【可接取委托】" in output
    assert "无暇交谈" not in output
    assert player.get_npc_location("药铺老板", refresh=False) == before


def test_busy_trader_still_opens_shop():
    player = make_busy_herbalist()
    output, result = capture(handle_trading, player, "shop", [])
    assert result is True
    assert "店铺货架" in output
    assert "无暇经营" not in output


def test_busy_npc_accepts_quest_and_completes_delivery(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = make_busy_herbalist()

    accepted, _ = capture(handle_talk_and_ask, player, ["药铺老板", "接受委托", HERB_TITLE])
    assert "已接取任务" in accepted
    assert HERB_QUEST in player.active_quests

    prepare_deliverable(player)
    delivered, _ = capture(handle_talk_and_ask, player, ["药铺老板", "交付委托", HERB_TITLE])
    assert "恭喜完成任务" in delivered
    assert HERB_QUEST not in player.active_quests
    assert HERB_QUEST in player.completed_quests


def test_away_remains_the_explicit_non_interaction_state():
    player = Player("暂离状态验收", "散人")
    player.location = "medicine_shop"
    player.set_npc_state("药铺老板", "away", duration=5, reason="出门采买")

    output, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "暂时不在状态" in output
    assert "【可接取委托】" not in output

    trade, _ = capture(handle_trading, player, "shop", [])
    assert "店铺货架" not in trade
    assert "暂时离开了" in trade or "没有可以交易" in trade


def test_task_list_and_detail_use_public_title_only():
    player = Player("任务显示名验收", "散人")
    player.active_quests[HERB_QUEST] = 0
    player.quest_states[HERB_QUEST] = {"stage": 0, "progress": 0}

    listing, _ = capture(handle_quest, player, "quests", [])
    assert HERB_TITLE in listing
    assert HERB_QUEST not in listing

    for requested_name in (HERB_QUEST, HERB_TITLE, "初入江湖采药识草"):
        detail, _ = capture(handle_quest, player, "quests", [requested_name])
        assert f"任务详情：{HERB_TITLE}" in detail
        assert HERB_QUEST not in detail


def test_direct_accept_matches_internal_key_and_public_title():
    for requested_name in (HERB_QUEST, HERB_TITLE):
        player = Player(f"直接接取-{requested_name}", "散人")
        player.location = "medicine_shop"
        output, _ = capture(handle_quest, player, "jiequ", [requested_name])
        assert "已接取任务" in output
        assert HERB_QUEST in player.active_quests


def test_direct_delivery_matches_internal_key_and_public_title(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    for requested_name in (HERB_QUEST, HERB_TITLE):
        player = Player(f"直接交付-{requested_name}", "散人")
        player.location = "medicine_shop"
        prepare_deliverable(player)
        output, _ = capture(handle_quest, player, "jiaofu", [requested_name])
        assert "恭喜完成任务" in output
        assert HERB_QUEST in player.completed_quests


def test_delivery_prompt_and_task_list_share_the_same_name():
    player = Player("多委托交付名称", "散人")
    player.location = "medicine_shop"
    prepare_deliverable(player, HERB_QUEST, 2)
    prepare_deliverable(player, RESTOCK_QUEST, 3)

    prompt, _ = capture(handle_talk_and_ask, player, ["药铺老板", "交付委托"])
    assert "你有以下可交付委托" in prompt
    assert f"1 {HERB_TITLE}" in prompt
    assert f"2 {RESTOCK_QUEST}" in prompt
    assert HERB_QUEST not in prompt


def test_dialogue_layers_deliverable_before_locked_offers():
    player = Player("委托分层优先", "散人")
    player.location = "village_head_house"
    player.active_quests["新手狩猎·野外除害"] = 1
    player.quest_states["新手狩猎·野外除害"] = {"stage": 0, "progress": 1}

    output, _ = capture(handle_talk_and_ask, player, ["村长", "委托"])
    assert "【可交付委托】" in output
    assert "【当前不可接取】" in output
    assert output.index("【可交付委托】") < output.index("【当前不可接取】")
    assert "初入江湖·野外除害" in output
    assert "村道巡查·清理残匪" in output


def test_busy_quest_giver_offer_text_uses_title_not_internal_key():
    player = make_busy_herbalist()
    output, _ = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])
    assert HERB_TITLE in output
    assert HERB_QUEST not in output
    assert "【可接取委托】" in output
    assert "【当前不可接取】" in output


def test_quest_name_resolver_accepts_key_title_and_normalized_title():
    assert _resolve_npc_quest_name(HERB_QUEST, [HERB_QUEST]) == ("matched", [HERB_QUEST])
    assert _resolve_npc_quest_name(HERB_TITLE, [HERB_QUEST]) == ("matched", [HERB_QUEST])
    assert _resolve_npc_quest_name("初入江湖，采药识草", [HERB_QUEST]) == ("matched", [HERB_QUEST])
