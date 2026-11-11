"""Alpha317：玩家可见 NPC 称谓与场景【人物】标签一致。"""
import contextlib
import io

import actor_display
import engine
from actions import (
    handle_information,
    handle_npc_actions,
    handle_quest,
    handle_relations,
    handle_talk_and_ask,
    handle_trading,
)
from player import Player


def capture(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args)
    return buf.getvalue(), result


def player_at(room="medicine_shop", tick=0):
    player = Player("称谓一致性验收", "散人")
    player.location = room
    player.set_var("quest_clock", tick)
    return player


def test_prose_name_upgrades_only_exact_mismatches():
    assert actor_display.prose_name("药铺老板") == "百草堂主"
    assert actor_display.prose_name("店小二") == "客栈小二"
    assert actor_display.prose_name("被绑村民") == "受难村民"
    # 标签只是加前缀时保留简短键名，避免叙述变得冗长。
    assert actor_display.prose_name("守卫") == "守卫"
    assert actor_display.prose_name("村长") == "村长"
    assert actor_display.prose_name("小翠") == "小翠"


def test_quest_and_room_prose_use_room_labels():
    newcomer = engine.QUESTS["新手采药·认识资源"]
    assert "百草堂主" in newcomer["notice"] and "药铺老板" not in newcomer["notice"]
    assert "百草堂主" in newcomer["desc"] and "药铺老板" not in newcomer["desc"]
    assert "店小二" not in engine.ROOMS["inn"]["desc"]
    assert "杂货铺老板" not in engine.ROOMS["general_shop"]["desc"]
    assert "受难村民" in engine.NPCS["村长"]["info"]["山贼"]


def test_talk_accepts_room_label_and_answers_in_kind():
    player = player_at()
    out, _ = capture(handle_talk_and_ask, player, ["百草堂主"])
    assert "百草堂主" in out
    assert "药铺老板" not in out


def test_talk_title_and_partial_label_resolve_to_same_npc():
    player = player_at()
    out, _ = capture(handle_talk_and_ask, player, ["堂主"])
    assert "百草堂主" in out
    assert "药铺老板" not in out


def test_talk_quest_offer_points_to_room_label():
    player = player_at(tick=2)
    player.set_flag("newcomer:guide_seen", True)
    out, _ = capture(handle_talk_and_ask, player, ["百草堂主"])
    assert "交谈 百草堂主 接受委托" in out
    assert "交谈 药铺老板" not in out


def test_delivery_guide_and_publisher_message_use_room_label():
    player = player_at()
    player.active_quests["新手采药·认识资源"] = 2
    player.quest_states["新手采药·认识资源"] = {"stage": 0, "progress": 2}
    guide = player.get_quest_delivery_guide("新手采药·认识资源")
    assert guide["npc"] == "百草堂主"
    assert "百草堂主" in guide["command"]

    far = player_at("village_square")
    out, _ = capture(handle_quest, far, "jiequ", ["新手采药·认识资源"])
    assert "任务发布人【百草堂主】" in out
    assert "药铺老板" not in out


def test_quest_detail_stage_target_uses_room_label():
    player = player_at(tick=2)
    quest = "村道回暖·药铺复业"
    player.active_quests[quest] = 0
    player.quest_states[quest] = {"stage": 0, "progress": 0}
    out, _ = capture(handle_quest, player, "quests", [quest])
    assert "阶段目标：交谈 / 百草堂主" in out
    assert "药铺老板" not in out


def test_shop_panel_uses_room_label():
    player = player_at(tick=2)
    out, _ = capture(handle_trading, player, "list", [])
    assert "百草堂主 的店铺货架" in out
    assert "药铺老板" not in out


def test_memory_and_npc_action_logs_use_room_label():
    player = player_at()
    player.remember_npc_about_player("药铺老板", "helped", "帮他整理过药柜。", "positive", 60)
    memory_out, _ = capture(handle_information, player, ["记忆"])
    assert "百草堂主：帮他整理过药柜。" in memory_out
    assert "药铺老板" not in memory_out

    player._record_npc_action("药铺老板", "patrol", "查看药柜", None, "medicine_shop", "medicine_shop")
    log_out, _ = capture(handle_npc_actions, player, [5])
    assert "百草堂主【巡行】" in log_out
    assert "药铺老板" not in log_out


def test_relation_list_uses_room_label():
    player = player_at()
    player.change_relation("药铺老板", 2)
    out, _ = capture(handle_relations, player)
    assert "- 百草堂主：" in out
    assert "药铺老板" not in out


def test_movement_broadcast_uses_room_label_for_exact_mismatch():
    player = Player("移动称谓验收", "散人")
    home = player.get_npc_location("药铺老板")
    player.location = home
    player.drain_npc_movement_messages()
    assert player.set_npc_location("药铺老板", "village_square", "return")
    messages = player.drain_npc_movement_messages()
    assert messages == ["百草堂主转身回了村中广场。"]


def test_economy_activity_uses_room_label_and_keeps_caravans():
    import actions

    sentence = actions._business_activity_sentence(
        {"actor": "采药人阿芷", "kind": "采集", "action": "采集", "item": "草药", "amount": 2}
    )
    assert sentence == "采药人阿芷近日从附近采得2份草药。"
    caravan = actions._business_activity_sentence(
        {"actor": "北路商队", "kind": "交易", "action": "售予城镇", "item": "草药", "amount": 3}
    )
    assert caravan == "北路商队近日在镇上卖出了3份草药。"


def test_inn_overnight_text_uses_room_label():
    from actions import handle_inn_service

    player = player_at("inn", tick=18)
    player.gold = 20
    out, _ = capture(handle_inn_service, player, "住店", [])
    assert "客栈小二引你上楼" in out
    assert "店小二引你上楼" not in out


def test_ambience_and_traffic_text_use_room_label():
    import world_ambience

    text = repr(world_ambience.__dict__)
    assert "店小二" not in text
    assert "客栈小二" in text
