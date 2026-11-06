"""Alpha277：目标完成≠已交付、交付指引、禁止自动结算与闲聊隔离。"""
import contextlib
import io

import engine
from actions import _quest_npc_status, handle_quest, handle_talk_and_ask
from player import Player


ROAD_QUEST = "村道回暖·药铺复业"
RESTOCK_QUEST = "百草备货·补齐药材"
HERB_QUEST = "新手采药·认识资源"
ROAD_FLAG = "world:main:herb_trade_resumed"


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return stream.getvalue(), result


def prepare_ready_road_quest(location="village_head_house"):
    player = Player("交付状态验收", "散人")
    player.location = location
    player.active_quests[ROAD_QUEST] = 1
    player.quest_states[ROAD_QUEST] = {"stage": 0, "progress": 1}
    return player


def prepare_ready_herb_quest():
    player = Player("采药交付验收", "散人")
    player.location = "medicine_shop"
    player.active_quests[HERB_QUEST] = 2
    player.quest_states[HERB_QUEST] = {"stage": 0, "progress": 2}
    player.inventory.extend(["草药", "草药"])
    return player


def test_target_achieved_message_includes_original_npc_location_and_command():
    player = Player("目标达成指引", "散人")
    player.location = "medicine_shop"
    player.active_quests[ROAD_QUEST] = 0
    player.quest_states[ROAD_QUEST] = {"stage": 0, "progress": 0}

    output, _ = capture(handle_talk_and_ask, player, ["药铺老板"])

    assert "[任务目标达成]" in output
    assert "可以交付" in output
    assert "交付指引" in output and "【村长宅院】" in output and "【村长】" in output
    assert "交谈 村长 交付委托 村道回暖·药铺复业" in output
    assert ROAD_QUEST in player.active_quests
    assert ROAD_QUEST not in player.completed_quests
    assert player.get_flag(f"quest_completed:{ROAD_QUEST}") is False
    assert player.get_flag(ROAD_FLAG) is False


def test_goal_complete_prerequisite_says_deliver_first_without_contradiction():
    player = prepare_ready_road_quest("medicine_shop")

    output, _ = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])

    assert "接取条件未满足：需先交付【村道回暖·药铺复业】" in output
    assert "需要先完成" not in output
    assert "可以交付" not in output
    assert "【当前不可接取】" in output


def test_delivery_without_name_lists_options_and_never_auto_settles(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = prepare_ready_road_quest()

    output, _ = capture(handle_talk_and_ask, player, ["村长", "交付委托"])

    assert "你有以下可交付委托" in output
    assert "村道回暖·药铺复业" in output
    assert "前往【村长宅院】找【村长】" in output
    assert "交谈 村长 交付委托 村道回暖·药铺复业" in output
    assert ROAD_QUEST in player.active_quests
    assert ROAD_QUEST not in player.completed_quests
    assert player.get_flag(f"quest_completed:{ROAD_QUEST}") is False
    assert player.get_flag(ROAD_FLAG) is False


def test_explicit_numbered_delivery_completes_and_unlocks_followup(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = prepare_ready_road_quest()

    output, _ = capture(handle_talk_and_ask, player, ["村长", "交付委托", "1"])

    assert "恭喜完成任务" in output
    assert ROAD_QUEST not in player.active_quests
    assert ROAD_QUEST in player.completed_quests
    assert player.get_flag(f"quest_completed:{ROAD_QUEST}") is True
    assert player.get_flag(ROAD_FLAG) is True
    assert _quest_npc_status(player, RESTOCK_QUEST)[0] == "未领取"


def test_status_distinguishes_goal_complete_from_delivered():
    player = prepare_ready_road_quest()
    state, detail = _quest_npc_status(player, ROAD_QUEST)
    assert state == "待交付"
    assert "等待你当面交付" in detail

    player.active_quests.pop(ROAD_QUEST)
    player.quest_states.pop(ROAD_QUEST, None)
    player.completed_quests.append(ROAD_QUEST)
    player.set_flag(f"quest_completed:{ROAD_QUEST}", True)

    state, detail = _quest_npc_status(player, ROAD_QUEST)
    assert state == "已交付"
    assert "已经交付完毕" in detail


def test_task_list_and_detail_mark_pending_delivery_and_keep_quest_active():
    player = prepare_ready_road_quest()

    listing, _ = capture(handle_quest, player, "quests", [])
    assert "【待交付】" in listing
    assert "目标已完成但奖励未结算" in listing

    detail, _ = capture(handle_quest, player, "quests", [ROAD_QUEST])
    assert "当前状态：待交付" in detail
    assert "必须回到委托人处主动交付" in detail
    assert "交谈 村长 交付委托 村道回暖·药铺复业" in detail
    assert ROAD_QUEST in player.active_quests
    assert ROAD_QUEST not in player.completed_quests

    player.active_quests.pop(ROAD_QUEST)
    player.completed_quests.append(ROAD_QUEST)
    delivered_detail, _ = capture(handle_quest, player, "quests", [ROAD_QUEST])
    assert "当前状态：已交付" in delivered_detail
    assert "当前状态：待交付" not in delivered_detail


def test_single_deliverable_offer_shows_full_delivery_method():
    player = prepare_ready_herb_quest()

    output, _ = capture(handle_talk_and_ask, player, ["药铺老板"])

    assert "【可交付委托】" in output
    assert "初入江湖·采药识草" in output
    assert "等待你当面交付" in output
    assert "前往【百草堂】找【药铺老板】" in output
    assert "交谈 药铺老板 交付委托 初入江湖·采药识草" in output
    assert HERB_QUEST in player.active_quests


def test_small_talk_is_not_mixed_into_default_or_quest_interaction():
    player = Player("闲聊隔离验收", "散人")
    player.location = "medicine_shop"
    player.economy_state = {
        "events": {
            "world_activity": [
                {"actor": "药铺老板", "action": "整理", "amount": 3, "item": "草药", "room_id": "medicine_shop"}
            ]
        }
    }

    plain, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "你提起近来" not in plain
    assert "你问起眼下" not in plain

    quest_ask, _ = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])
    assert "你提起近来" not in quest_ask
    assert "你问起眼下" not in quest_ask


def test_explicit_small_talk_prints_context_without_quest_dump():
    player = Player("闲聊指令验收", "散人")
    player.location = "medicine_shop"
    player.economy_state = {
        "events": {
            "world_activity": [
                {"actor": "药铺老板", "action": "整理", "amount": 3, "item": "草药", "room_id": "medicine_shop"}
            ]
        }
    }

    output, _ = capture(handle_talk_and_ask, player, ["药铺老板", "闲聊"])

    assert "【闲谈】" in output
    assert "你提起近来" in output
    assert "【可接取委托】" not in output
    assert "【当前不可接取】" not in output


def test_delivered_records_in_list_or_flag_satisfy_prerequisite_consistently():
    requires = engine.QUESTS[RESTOCK_QUEST]["requires"]

    list_only = Player("完成列表前置", "散人")
    list_only.completed_quests.append(ROAD_QUEST)
    list_only.set_flag(ROAD_FLAG, True)
    assert engine.check_conditions(requires, list_only.world_state, list_only.completed_quests, list_only)
    assert engine.explain_condition_failures(requires, list_only.world_state, list_only.completed_quests, list_only) == []

    flag_only = Player("完成旗标前置", "散人")
    flag_only.set_flag(f"quest_completed:{ROAD_QUEST}", True)
    flag_only.set_flag(ROAD_FLAG, True)
    assert engine.check_conditions(requires, flag_only.world_state, [], flag_only)
    assert engine.explain_condition_failures(requires, flag_only.world_state, [], flag_only) == []

    pending = prepare_ready_road_quest("medicine_shop")
    assert not engine.check_conditions(requires, pending.world_state, pending.completed_quests, pending)
    reasons = engine.explain_condition_failures(requires, pending.world_state, pending.completed_quests, pending)
    assert any("需先交付【村道回暖·药铺复业】" in reason for reason in reasons)


def test_default_talk_hides_locked_and_delivered_but_explicit_inquiry_layers_them():
    player = Player("任务分层验收", "散人")
    player.location = "medicine_shop"
    player.completed_quests.append(HERB_QUEST)
    player.set_flag(f"quest_completed:{HERB_QUEST}", True)

    compact, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "【当前不可接取】" not in compact
    assert "【已完成委托】" not in compact

    detailed, _ = capture(handle_talk_and_ask, player, ["药铺老板", "委托"])
    assert "【当前不可接取】" in detailed
    assert "【已完成委托】" in detailed
    assert "已交付：初入江湖·采药识草" in detailed
    assert "需先完成并交付【村道回暖·药铺复业】" in detailed
    assert detailed.index("【当前不可接取】") < detailed.index("【已完成委托】")
