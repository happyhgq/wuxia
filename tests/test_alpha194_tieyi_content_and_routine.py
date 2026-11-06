"""Alpha194：铁衣门文案归属、门派指引与守门巡值闭环。"""
import engine
from player import Player


def test_tieyi_npc_guidance_does_not_send_player_to_another_sect():
    reception = engine.NPCS["铁衣门接引执事"]
    teacher = engine.NPCS["铁衣门传功师父"]
    officer = engine.NPCS["铁衣门护运执事"]
    assert "拜师 铁衣门" in reception["behavior_hint"]
    assert "华山" not in reception["behavior_hint"]
    assert "铁衣门武学" in teacher["behavior_hint"]
    assert "华山武学" not in teacher["behavior_hint"]
    assert all("华山" not in str(choice) for choice in teacher["dialogue_choices"])
    assert all("加入华山" not in str(choice) for choice in officer["dialogue_choices"])
    assert all(choice["id"].startswith("tieyi_") for choice in teacher["dialogue_choices"] + officer["dialogue_choices"])


def test_tieyi_guard_information_is_attributed_to_tieyi():
    guard = engine.NPCS["铁衣门守门弟子"]
    assert all(item.get("source") != "华山守门弟子" for item in guard.get("information", []))
    assert all(item.get("topic") != "huashan_gate_rules" for item in guard.get("information", []))
    assert guard["faction"] == "铁衣门"


def test_tieyi_guard_daily_schedule_moves_between_connected_gate_and_foothill():
    guard = engine.NPCS["铁衣门守门弟子"]
    schedule = guard["daily_schedule"]
    assert any(row["location"] == "tieyi_gate" for row in schedule)
    assert any(row["location"] == "tieyi_foothill" for row in schedule)
    assert all(row["location"] in engine.ROOMS for row in schedule)
    assert engine.ROOMS["tieyi_gate"]["exits"].get("南") == "tieyi_foothill"
    assert engine.ROOMS["tieyi_foothill"]["exits"].get("北") == "tieyi_gate"

    player = Player("铁衣门巡值测试", "散人")
    # 日程按真实钟点编排；tick 0 为卯时 06:00，因此 08:00/14:00/20:00 对应 tick 2/8/14。
    player.world_state.setdefault("variables", {})["quest_clock"] = 2
    assert player.get_npc_location("铁衣门守门弟子") == "tieyi_gate"
    player.world_state["variables"]["quest_clock"] = 8
    player.refresh_npc_schedules()
    assert player.get_npc_location("铁衣门守门弟子") == "tieyi_foothill"
    player.world_state["variables"]["quest_clock"] = 14
    assert player.get_npc_location("铁衣门守门弟子") == "tieyi_gate"


def test_tieyi_promotion_trial_is_real_and_rank_requirements_are_reachable():
    player = Player("铁衣门晋升验收", "散人")
    player.level = 3
    assert player.join_sect("铁衣门")[0]
    player.change_sect_reputation("铁衣门", 100)
    player.level = 15
    player._sect_progress_state().setdefault("铁衣门", {})["official_rank_index"] = 2
    req = player.get_sect_promotion_requirements("铁衣门")
    assert req["required_quests"] == ["铁衣门历练·护路除匪"]
    quest = engine.QUESTS[req["required_quests"][0]]
    assert quest["npc"] in engine.NPCS
    assert quest["turn_in_npc"] in engine.NPCS
    assert quest["requires"]["sect"] == "铁衣门"
