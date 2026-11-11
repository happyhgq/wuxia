# -*- coding: utf-8 -*-
"""Alpha316：断魂堡主微调与感知反应后继续正常交谈。"""

import contextlib
import io

import engine
from actions import handle_talk_and_ask
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return _ANSI_RE.sub("", stream.getvalue()), result


def make_player(name, location, clock):
    player = Player(name)
    player.location = location
    player.set_var("quest_clock", clock)
    player.refresh_npc_schedules()
    return player


def main_security(player):
    return player.world_state["variables"].get("region_activity", {}).get("main", {}).get("security", 0)


def test_alpha316_duanhun_boss_micro_adjustment_keeps_rewards_and_phases():
    boss = engine.ENEMIES["断魂堡主"]
    assert (boss["hp"], boss["atk"], boss["defense"]) == (920, 80, 23)
    assert (boss["exp"], boss["gold"], boss["level"], boss["tier"]) == (660, 260, 15, "boss")
    assert boss["drops"] == [
        {"item": "大还丹", "chance": 0.6, "guaranteed": True},
        {"item": "黑风寨军械残片", "chance": 1.0, "guaranteed": True, "quantity": 2},
    ]
    assert [(ph.get("threshold"), ph.get("atk_mult"), ph.get("defense_bonus"), ph.get("heal_percent", 0))
            for ph in boss["phases"]] == [(0.65, 1.12, 1, 0), (0.3, 1.28, -1, 0.04)]
    assert [sk["name"] for sk in boss["skills"]] == ["断魂斩", "慑魂刀风", "绝命三连", "断魂绝刀"]
    # 黑市头目保持 Alpha287 校准面板，不受本次微调影响。
    market = engine.ENEMIES["黑市头目"]
    assert (market["hp"], market["atk"], market["defense"]) == (725, 61, 20)


def test_alpha316_apothecary_treatment_then_continues_conversation_when_busy():
    player = make_player("施药续聊验收", "medicine_shop", 0)
    player.hp = 20
    assert player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])

    assert "气血恢复 25 点。" in value
    assert player.hp == 45
    assert "百草堂主 含笑应道：" in value
    assert "只匆匆应了一声" not in value
    assert "暂时脱不开身" not in value
    # 反应结算后走完整交谈流程，等同于普通交谈推进一个时辰。
    assert result is None
    assert engine.ROOMS["medicine_shop"]["desc"] not in value


def test_alpha316_apothecary_second_talk_same_day_keeps_dialogue_without_reward():
    player = make_player("施药防重验收", "medicine_shop", 0)
    player.hp = 20
    player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    capture(handle_talk_and_ask, player, ["药铺老板"])
    assert player.hp == 45

    player.set_npc_state("药铺老板", "normal")
    player.hp = 20
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])

    assert "气血恢复" not in value
    assert player.hp == 20
    assert "百草堂主 含笑应道：" in value
    assert result is None
    assert player.world_state["variables"]["npc_action_days"]["药铺老板"] == 0


def test_alpha316_guard_patrol_then_continues_conversation_when_busy():
    player = make_player("巡守续聊验收", "village_gate", 15)
    player.world_state["variables"]["weather_world"] = {
        "kind": "rain", "until_tick": 300, "term_ordinal": 0, "seed": 1,
    }
    assert player.set_npc_state("守卫", "busy", duration=5, reason="正在巡街")
    value, result = capture(handle_talk_and_ask, player, ["守卫"])

    assert "盘查从简" in value
    assert "区域变化：" in value and "安全度 +1" in value
    assert main_security(player) == 1
    assert "守卫 沉声道：" in value
    assert "只匆匆应了一声" not in value
    assert result is None
    assert engine.ROOMS["village_gate"]["desc"] not in value


def test_alpha316_guard_second_talk_same_day_keeps_dialogue_without_patrol_reward():
    player = make_player("巡守防重验收", "village_gate", 15)
    player.world_state["variables"]["weather_world"] = {
        "kind": "rain", "until_tick": 300, "term_ordinal": 0, "seed": 1,
    }
    player.set_npc_state("守卫", "busy", duration=5, reason="正在巡街")
    capture(handle_talk_and_ask, player, ["守卫"])
    assert main_security(player) == 1

    player.set_npc_state("守卫", "normal")
    value, result = capture(handle_talk_and_ask, player, ["守卫"])

    assert "区域变化：" not in value
    assert main_security(player) == 1
    assert "守卫 沉声道：" in value
    assert result is None


def test_alpha316_busy_npc_without_reaction_still_uses_short_reply():
    player = make_player("忙碌短应答验收", "medicine_shop", 0)
    player.hp = player.max_hp
    player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    value, result = capture(handle_talk_and_ask, player, ["药铺老板"])

    assert "只匆匆应了一声" in value
    assert "含笑应道" not in value
    assert result is False
