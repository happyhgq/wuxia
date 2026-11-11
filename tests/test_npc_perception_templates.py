# -*- coding: utf-8 -*-
import copy
from types import SimpleNamespace

import pytest

import data_validator
import engine
import npc_perception


def make_player(hp=100, max_hp=100, hour=12, weather_kind=None, equipment=None):
    variables = {}
    if weather_kind:
        variables["weather_world"] = {"kind": weather_kind, "until_tick": 24, "term_ordinal": 0, "seed": 1}
    player = SimpleNamespace(
        hp=hp,
        max_hp=max_hp,
        equipment=dict(equipment or {}),
        world_state={"flags": {}, "variables": variables},
        completed_quests=set(),
    )
    player.get_quest_clock = lambda: (hour - 6) % 24
    return player


def template_variants(role, predicate):
    for entry in engine.PERCEPTION_TEMPLATES[role]:
        if predicate(entry.get("perception", {})):
            return entry["variants"]
    raise AssertionError(f"未找到模板条目：{role}")


def test_templates_cover_eight_roles_with_two_variants_each():
    assert set(engine.PERCEPTION_TEMPLATES) == {
        "smith", "innkeeper", "inn_staff", "apothecary",
        "shopkeeper", "guard", "hunter", "villager",
    }
    for role, entries in engine.PERCEPTION_TEMPLATES.items():
        assert len(entries) >= 4, role
        for entry in entries:
            assert isinstance(entry.get("priority"), int)
            assert isinstance(entry.get("perception"), dict) and entry["perception"]
            variants = entry.get("variants")
            assert isinstance(variants, list) and len(variants) >= 2
            assert len(set(variants)) == len(variants)
            assert all(isinstance(text, str) and text.strip() for text in variants)


def test_perception_roles_are_assigned_within_templates():
    role_counts = {}
    for name, info in engine.NPCS.items():
        role = info.get("perception_role")
        if role:
            assert role in engine.PERCEPTION_TEMPLATES, name
            role_counts[role] = role_counts.get(role, 0) + 1
    assert sum(role_counts.values()) == 36
    assert role_counts == {
        "smith": 3, "innkeeper": 3, "inn_staff": 3, "apothecary": 4,
        "shopkeeper": 9, "guard": 5, "hunter": 3, "villager": 6,
    }


def test_npc_entries_keep_own_dialogue_before_templates():
    own = engine.NPCS["铁匠"]["conditional_dialogue"]
    entries = npc_perception.npc_entries(engine.NPCS["铁匠"])
    assert entries[:len(own)] == own
    assert entries[len(own):] == engine.PERCEPTION_TEMPLATES["smith"]


def test_unknown_role_adds_no_template_entries():
    data = {"conditional_dialogue": [], "perception_role": "no_such_role"}
    assert npc_perception.npc_entries(data) == []
    assert npc_perception.select_reaction_text(make_player(), data) is None


def test_innkeeper_template_reacts_at_night():
    player = make_player(hour=22)
    line = npc_perception.select_reaction_text(player, engine.NPCS["云来客栈掌柜"], "云来客栈掌柜")
    assert line in template_variants("innkeeper", lambda rule: rule.get("time_phase") == "night")


def test_apothecary_template_reacts_to_badly_wounded():
    player = make_player(hp=20)
    line = npc_perception.select_reaction_text(player, engine.NPCS["百草堂掌柜"], "百草堂掌柜")
    assert line in template_variants("apothecary", lambda rule: rule.get("injury") == "badly_wounded")


def test_guard_template_reacts_at_night():
    player = make_player(hour=22)
    line = npc_perception.select_reaction_text(player, engine.NPCS["狱卒"], "狱卒")
    assert line in template_variants("guard", lambda rule: rule.get("time_phase") == "night")


def test_hunter_template_reacts_to_bad_weather():
    player = make_player(weather_kind="snow")
    line = npc_perception.select_reaction_text(player, engine.NPCS["守岭猎户"], "守岭猎户")
    assert line in template_variants(
        "hunter", lambda rule: rule.get("weather") == ["rain", "storm", "snow"]
    )


def test_own_conditional_dialogue_outranks_template():
    player = make_player(hour=13, equipment={"weapon": "铁剑·精良"})
    line = npc_perception.select_reaction_text(player, engine.NPCS["铁匠"], "铁匠")
    assert "刃口还直" in line
    assert line not in template_variants("smith", lambda rule: "equipment_quality" in rule)


def test_variants_rotate_instead_of_repeating():
    player = make_player(hour=22)
    data = engine.NPCS["云来客栈掌柜"]
    night = set(template_variants("innkeeper", lambda rule: rule.get("time_phase") == "night"))
    first = npc_perception.select_reaction_text(player, data, "云来客栈掌柜")
    second = npc_perception.select_reaction_text(player, data, "云来客栈掌柜")
    third = npc_perception.select_reaction_text(player, data, "云来客栈掌柜")
    assert {first, second, third} <= night
    assert first != second
    assert third == first


def test_variant_cursor_is_not_shared_between_players():
    first_player = make_player(hour=22)
    second_player = make_player(hour=22)
    data = engine.NPCS["云来客栈掌柜"]
    first_a = npc_perception.select_reaction_text(first_player, data, "云来客栈掌柜")
    second_a = npc_perception.select_reaction_text(second_player, data, "云来客栈掌柜")
    assert first_a == second_a
    first_b = npc_perception.select_reaction_text(first_player, data, "云来客栈掌柜")
    second_b = npc_perception.select_reaction_text(second_player, data, "云来客栈掌柜")
    assert first_b == second_b
    assert first_a != first_b


def test_variant_rotation_keeps_world_state_untouched():
    player = make_player(hour=22)
    before = copy.deepcopy(player.world_state)
    npc_perception.select_reaction_text(player, engine.NPCS["云来客栈掌柜"], "云来客栈掌柜")
    assert player.world_state == before
    assert "npc_reaction" not in player.world_state["variables"]
    assert isinstance(player._npc_reaction_cursor, dict)


def test_single_text_entries_do_not_create_variant_cursor():
    player = make_player(hour=22)
    data = {"conditional_dialogue": [{"priority": 1, "text": "只有一句。"}]}
    assert npc_perception.select_reaction_text(player, data, "测试") == "只有一句。"
    assert not hasattr(player, "_npc_reaction_cursor")


def test_asking_unknown_topic_can_exclude_templates():
    player = make_player(hour=6)
    data = engine.NPCS["菜贩孙婶"]
    assert npc_perception.select_reaction_text(player, data, "菜贩孙婶") is not None
    assert npc_perception.select_reaction_text(player, data, "菜贩孙婶", include_templates=False) is None


def test_entry_texts_supports_text_and_variants():
    assert npc_perception._entry_texts({"text": "单句"}) == ["单句"]
    assert npc_perception._entry_texts({"variants": ["甲", "乙"]}) == ["甲", "乙"]
    assert npc_perception._entry_texts({"variants": ["甲", "乙"], "text": "单句"}) == ["甲", "乙"]
    assert npc_perception._entry_texts({"variants": []}) == []


def test_validator_rejects_duplicate_or_missing_variants():
    errors = []
    data_validator.validate_conditional_entry(
        {"variants": ["甲", "甲"], "perception": {"time_phase": "night"}},
        "测试", errors, require_perception=True,
    )
    assert any("重复" in error for error in errors)

    errors = []
    data_validator.validate_conditional_entry(
        {"variants": ["甲"]}, "测试", errors, require_perception=True,
    )
    assert any("perception" in error for error in errors)


def test_validator_accepts_template_entry_without_text():
    errors = []
    data_validator.validate_conditional_entry(
        {"priority": 5, "perception": {"weather": ["rain", "storm"]}, "variants": ["甲", "乙"]},
        "测试", errors, require_perception=True,
    )
    assert errors == []
