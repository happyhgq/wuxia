# -*- coding: utf-8 -*-
import copy
import json
from types import SimpleNamespace

import pytest

import engine
import npc_perception
from actions import _conditional_dialogue_text


def make_player(hp=100, max_hp=100, hour=12, weather_kind=None,
                equipment=None, world_state=None, completed_quests=None):
    variables = {}
    if weather_kind:
        variables["weather_world"] = {"kind": weather_kind, "until_tick": 24, "term_ordinal": 0, "seed": 1}
    state = world_state if world_state is not None else {"flags": {}, "variables": variables}
    p = SimpleNamespace(
        hp=hp,
        max_hp=max_hp,
        equipment=dict(equipment or {}),
        world_state=state,
        completed_quests=set(completed_quests or []),
    )
    p.get_quest_clock = lambda: (hour - 6) % 24
    return p


def test_snapshot_reports_time_weather_injury_and_gear():
    player = make_player(
        hp=50,
        hour=18,
        weather_kind="rain",
        equipment={"weapon": "铁剑·稀有", "armor": "锁子甲", "accessory": None},
    )
    snap = npc_perception.build_snapshot(player)
    assert snap["hour"] == 18
    assert snap["time_phase"] == "dusk"
    assert snap["weather"] == "rain"
    assert snap["hp_percent"] == 50
    assert snap["injury"] == "wounded"
    assert snap["equipment_quality"] == {"weapon": "稀有", "armor": "普通", "accessory": "普通"}
    assert snap["best_equipment_quality"] == "稀有"


@pytest.mark.parametrize("hour,expected", [
    (4, "night"), (5, "dawn"), (8, "dawn"), (9, "day"),
    (16, "day"), (17, "dusk"), (19, "dusk"), (20, "night"),
])
def test_time_phase_boundaries(hour, expected):
    assert npc_perception.time_phase(hour) == expected


@pytest.mark.parametrize("hp_percent,expected", [
    (0, "badly_wounded"), (34, "badly_wounded"), (35, "wounded"),
    (69, "wounded"), (70, "healthy"), (100, "healthy"),
])
def test_injury_boundaries(hp_percent, expected):
    assert npc_perception.injury_level(hp_percent) == expected


def test_quality_rule_uses_minimum_and_exact_semantics():
    snapshot = {"equipment_quality": {"weapon": "稀有", "armor": "普通", "accessory": "普通"},
                "best_equipment_quality": "稀有"}
    assert npc_perception._perception_matches(snapshot, {"equipment_quality": {"weapon": "精良"}})
    assert npc_perception._perception_matches(snapshot, {"equipment_quality": {"best": "稀有"}})
    assert not npc_perception._perception_matches(snapshot, {"equipment_quality": {"weapon": "史诗"}})
    assert not npc_perception._perception_matches(snapshot, {"equipment_quality": {"weapon": {"eq": "精良"}}})
    assert npc_perception._perception_matches(snapshot, {"equipment_quality": {"weapon": {"gte": "稀有"}}})


def test_combined_environment_rules_must_all_match():
    snapshot = {"time_phase": "night", "weather": "storm", "injury": "badly_wounded", "hp_percent": 20}
    rules = {"time_phase": ["dusk", "night"], "weather": "storm", "injury": "badly_wounded"}
    assert npc_perception._perception_matches(snapshot, rules)
    assert not npc_perception._perception_matches(snapshot, {**rules, "weather": "clear"})
    assert not npc_perception._perception_matches(snapshot, {**rules, "hp_percent": {"lt": 20}})


def test_unknown_perception_key_fails_closed():
    snapshot = {"time_phase": "day"}
    assert not npc_perception._perception_matches(snapshot, {"unknown_fact": "day"})


def test_requires_and_perception_must_both_match():
    player = make_player(hp=20, hour=21)
    npc_data = {"conditional_dialogue": [{
        "priority": 30,
        "requires": {"flags": ["village_saved"]},
        "perception": {"injury": "badly_wounded"},
        "text": "你伤得不轻，先进屋。",
    }]}
    assert _conditional_dialogue_text(player, npc_data) is None
    player.world_state["flags"]["village_saved"] = True
    assert _conditional_dialogue_text(player, npc_data) == "你伤得不轻，先进屋。"
    player.hp = 100
    assert _conditional_dialogue_text(player, npc_data) is None


def test_selection_prefers_priority_then_data_order():
    player = make_player(hp=20, hour=23)
    npc_data = {"conditional_dialogue": [
        {"priority": 10, "perception": {"time_phase": "night"}, "text": "低优先级"},
        {"priority": 40, "perception": {"injury": "badly_wounded"}, "text": "高优先级甲"},
        {"priority": 40, "perception": {"time_phase": "night"}, "text": "高优先级乙"},
    ]}
    assert _conditional_dialogue_text(player, npc_data) == "高优先级甲"


def test_existing_conditional_dialogue_without_perception_is_unchanged():
    player = make_player()
    player.world_state["flags"]["world:test:done"] = True
    npc_data = {"conditional_dialogue": [{
        "priority": 15,
        "requires": {"flags": ["world:test:done"]},
        "text": "旧条件对白。",
    }]}
    assert _conditional_dialogue_text(player, npc_data) == "旧条件对白。"


def test_selection_does_not_initialize_weather_state():
    player = make_player(hour=22)
    before = copy.deepcopy(player.world_state)
    npc_data = {"conditional_dialogue": [{
        "priority": 20,
        "perception": {"time_phase": "night"},
        "text": "夜深了。",
    }]}
    assert _conditional_dialogue_text(player, npc_data) == "夜深了。"
    assert player.world_state == before
    assert "weather_world" not in player.world_state["variables"]


@pytest.mark.parametrize("npc_name", [
    "铁匠", "药铺老板", "掌柜", "归云城守门校尉", "村长", "樵夫老周", "店小二",
])
def test_named_npcs_have_perception_reactions(npc_name):
    entries = engine.NPCS[npc_name].get("conditional_dialogue", [])
    perception_entries = [entry for entry in entries if isinstance(entry, dict) and entry.get("perception")]
    assert perception_entries
    for entry in perception_entries:
        assert isinstance(entry.get("text"), str) and entry["text"].strip()
        for key, rule in entry["perception"].items():
            assert key in npc_perception.PERCEPTION_KEYS
            if key == "equipment_quality":
                assert isinstance(rule, dict) and rule
                for slot, quality_rule in rule.items():
                    assert slot in {"best", *npc_perception.EQUIPMENT_SLOTS}
                    if isinstance(quality_rule, str):
                        assert quality_rule in npc_perception.QUALITY_ORDER


def test_shop_owner_reaction_reads_injury_but_not_healthy_player():
    data = engine.NPCS["药铺老板"]
    wounded = make_player(hp=30, hour=12)
    line = npc_perception.select_reaction_text(wounded, data)
    assert "伤势" in line
    healthy = make_player(hp=100, hour=12)
    assert npc_perception.select_reaction_text(healthy, data) != line
