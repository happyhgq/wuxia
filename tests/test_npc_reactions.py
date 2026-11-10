# -*- coding: utf-8 -*-
"""NPC 感知后的可执行反应：守卫坏天气简查加巡、药铺老板见重伤施药。"""

import contextlib
import io
from types import SimpleNamespace

import data_validator
import engine
import npc_reaction
from actions import handle_talk_and_ask
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return _ANSI_RE.sub("", stream.getvalue()), result


def make_player(hp=100, max_hp=100, hour=12, weather_kind=None):
    variables = {}
    if weather_kind:
        variables["weather_world"] = {"kind": weather_kind, "until_tick": 24, "term_ordinal": 0, "seed": 1}
    player = SimpleNamespace(
        hp=hp,
        max_hp=max_hp,
        world_state={"flags": {}, "variables": variables},
        completed_quests=set(),
    )
    player.get_quest_clock = lambda: (hour - 6) % 24
    return player


def main_security(player):
    return player.world_state["variables"].get("region_activity", {}).get("main", {}).get("security", 0)


def test_guard_shortens_check_and_adds_patrol_in_rain():
    player = make_player(hour=12, weather_kind="rain")
    result = npc_reaction.run_talk_action(player, "守卫", engine.NPCS["守卫"])
    assert result["id"] == "gate_short_check_rain"
    assert result["region_effects"] == {"main": {"security": 1}}
    assert main_security(player) == 1
    assert player.world_state["variables"]["npc_action_days"]["守卫"] == 0


def test_guard_patrol_only_once_per_world_day():
    player = make_player(hour=12, weather_kind="storm")
    assert npc_reaction.run_talk_action(player, "守卫", engine.NPCS["守卫"]) is not None
    assert npc_reaction.run_talk_action(player, "守卫", engine.NPCS["守卫"]) is None
    assert main_security(player) == 1

    player.get_quest_clock = lambda: 24 + (12 - 6) % 24
    assert npc_reaction.run_talk_action(player, "守卫", engine.NPCS["守卫"]) is not None
    assert main_security(player) == 2


def test_guard_shortens_check_at_night_with_clear_weather():
    player = make_player(hour=20)
    result = npc_reaction.run_talk_action(player, "守卫", engine.NPCS["守卫"])
    assert result["id"] == "gate_short_check_night"
    assert main_security(player) == 1


def test_guard_stays_normal_on_clear_daytime():
    player = make_player(hour=12)
    assert npc_reaction.run_talk_action(player, "守卫", engine.NPCS["守卫"]) is None
    assert "npc_action_days" not in player.world_state["variables"]
    assert main_security(player) == 0


def test_apothecary_tends_badly_wounded_player():
    player = make_player(hp=20, max_hp=100)
    result = npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"])
    assert result["id"] == "tend_badly_wounded"
    assert result["heal"] == 25
    assert player.hp == 45


def test_apothecary_treatment_limited_to_once_per_day():
    player = make_player(hp=10, max_hp=100)
    npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"])
    assert player.hp == 35
    assert npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"]) is None
    assert player.hp == 35

    player.get_quest_clock = lambda: 24
    player.hp = 20
    npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"])
    assert player.hp == 45


def test_apothecary_ignores_wounded_and_healthy_players():
    for hp in (50, 90):
        player = make_player(hp=hp)
        assert npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"]) is None
        assert player.hp == hp


def test_heal_never_exceeds_max_hp():
    player = make_player(hp=1, max_hp=30)
    result = npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"])
    assert result["heal"] == 7
    assert player.hp == 8


def test_action_state_stays_inside_existing_variables():
    player = make_player(hp=5)
    npc_reaction.run_talk_action(player, "药铺老板", engine.NPCS["药铺老板"])
    assert set(player.world_state) == {"flags", "variables"}
    assert "药铺老板" in player.world_state["variables"]["npc_action_days"]


def test_invalid_entries_are_skipped():
    npc_data = {
        "perception_actions": [
            {"id": "no_perception", "text": "无条件", "heal_percent": 50},
            {"id": "no_effect", "text": "无效果", "perception": {"injury": "badly_wounded"}},
            {"id": "not_matching", "text": "健康时不触发", "perception": {"injury": "badly_wounded"},
             "heal_percent": 50},
        ]
    }
    player = make_player(hp=100)
    assert npc_reaction.select_action(player, npc_data) is None


def test_higher_priority_action_wins():
    npc_data = {
        "perception_actions": [
            {"id": "low", "text": "低", "priority": 1, "perception": {"injury": "healthy"}, "heal_percent": 10},
            {"id": "high", "text": "高", "priority": 9, "perception": {"injury": "healthy"}, "heal_percent": 10},
        ]
    }
    player = make_player(hp=100)
    assert npc_reaction.select_action(player, npc_data)["id"] == "high"


def test_wounded_apothecary_talk_heals_even_when_busy():
    player = Player("重伤求医验收")
    player.location = "medicine_shop"
    player.set_var("quest_clock", 12)
    player.refresh_npc_schedules()
    player.hp = 20
    player.set_npc_state("药铺老板", "busy", duration=5, reason="正在坐堂配药")
    value, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "气血恢复 25 点。" in value
    assert player.hp == 45


def test_healthy_apothecary_talk_keeps_original_flow():
    player = Player("常态问药验收")
    player.location = "medicine_shop"
    player.set_var("quest_clock", 0)
    player.refresh_npc_schedules()
    value, _ = capture(handle_talk_and_ask, player, ["药铺老板"])
    assert "气血恢复" not in value
    assert "药铺老板 含笑应道：" in value


def test_guard_gate_talk_applies_patrol_on_rainy_night():
    player = Player("雨夜巡守验收")
    player.location = "village_gate"
    player.set_var("quest_clock", 15)
    player.refresh_npc_schedules()
    player.world_state["variables"]["weather_world"] = {
        "kind": "rain", "until_tick": 300, "term_ordinal": 0, "seed": 1,
    }
    value, _ = capture(handle_talk_and_ask, player, ["守卫"])
    assert "盘查从简" in value
    assert "区域变化：" in value and "安全度 +1" in value
    assert main_security(player) == 1


def test_validator_accepts_shipped_reactions():
    errors = []
    zones = {room.get("zone", "main") for room in engine.ROOMS.values()}
    for npc_name in ("守卫", "药铺老板"):
        for idx, action in enumerate(engine.NPCS[npc_name]["perception_actions"], 1):
            data_validator.validate_perception_action(
                action, f"NPC {npc_name}: perception_actions[{idx}]", zones, errors
            )
    assert errors == []


def test_validator_rejects_broken_reactions():
    zones = {"main"}
    broken = [
        {"id": "", "text": "缺 id", "perception": {"injury": "healthy"}, "heal_percent": 10},
        {"id": "no_text", "text": " ", "perception": {"injury": "healthy"}, "heal_percent": 10},
        {"id": "no_perception", "text": "无条件", "heal_percent": 10},
        {"id": "bad_heal", "text": "回血越界", "perception": {"injury": "healthy"}, "heal_percent": 120},
        {"id": "no_effect", "text": "没有效果", "perception": {"injury": "healthy"}},
        {"id": "bad_zone", "text": "区域不存在", "perception": {"injury": "healthy"},
         "region_effects": {"nowhere": {"security": 1}}},
        {"id": "bad_field", "text": "字段不存在", "perception": {"injury": "healthy"},
         "region_effects": {"main": {"danger": 1}}},
        {"id": "bad_flag", "text": "每日标记非法", "perception": {"injury": "healthy"},
         "heal_percent": 10, "once_per_day": "yes"},
    ]
    for action in broken:
        errors = []
        data_validator.validate_perception_action(action, "测试", zones, errors)
        assert errors, action["id"]
