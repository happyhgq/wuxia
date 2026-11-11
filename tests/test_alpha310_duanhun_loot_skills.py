# -*- coding: utf-8 -*-
"""Alpha310：断魂剑谱、断魂剑法、断锋护符与岭上素材兑换。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import apply_consumable, handle_explore, handle_quest, show_equipment
from player import Player

ROOT = Path(__file__).resolve().parents[1]

MANUAL = "断魂剑谱"
SKILL = "断魂剑法"
ACCESSORY = "断锋护符"
PELT_QUEST = "断魂岭·皮货换药"
BLADE_QUEST = "断魂岭·断锋回炉"
PREREQUISITE = "quest_completed:断魂岭·破堡除凶"
MANUAL_FLAG = "explore:duanhun_sword_grave:manual_found"


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return stream.getvalue(), result


def _ridge_player(name, location="duanhun_rain_shrine"):
    player = Player(name, "散人")
    player.level = 14
    player.location = location
    player.set_flag(PREREQUISITE, True)
    return player


def test_duanhun_skill_and_manual_are_registered_with_balanced_stats():
    skill = next(entry for entry in engine.SKILLS["江湖秘籍"] if entry["name"] == SKILL)
    assert skill["level"] == 12
    assert skill["mp_cost"] == 26
    assert skill["power"] == 2.45
    assert skill["manual_learnable"] is True
    assert skill["effect"] == {"type": "status", "status": "armor_break", "chance": 0.55, "turns": 2, "value": 4}
    assert engine.STATUS_EFFECTS["armor_break"]["name"] == "破防"
    top_power = max(entry["power"] for group in engine.SKILLS.values() for entry in group)
    assert skill["power"] < top_power

    item = engine.ITEMS[MANUAL]
    assert item["type"] == "manual"
    assert item["teaches_skill"] == SKILL
    assert item["desc"] and item["use_hint"]


def test_duanhun_manual_has_grave_and_elite_sources_at_low_rate():
    enemies = _data("enemies.json")
    assert enemies["守冢剑客"]["manual_drop"] == {"item": MANUAL, "chance": 0.002}
    for name, enemy in enemies.items():
        manual = enemy.get("manual_drop")
        if not manual:
            continue
        assert 0 < manual["chance"] <= 0.01, name
        assert manual["item"] in engine.ITEMS, name

    grave = engine.ROOMS["duanhun_sword_grave"]
    manual_events = [event for event in grave["exploration_events"]
                     if isinstance(event, dict) and event.get("item") == MANUAL]
    assert len(manual_events) == 1
    event = manual_events[0]
    assert event["requires"] == {"not_flags": [MANUAL_FLAG]}
    assert event["effects"] == {"set_flags": {MANUAL_FLAG: True}}
    assert engine.ITEMS[event["item"]]["teaches_skill"] == SKILL
    assert "探索" in grave["desc"]


def test_duanhun_manual_is_a_one_time_grave_reward():
    player = _ridge_player("剑冢探索验收", location="duanhun_sword_grave")
    for _ in range(12):
        _capture(handle_explore, player)
        if player.inventory.count(MANUAL) >= 1:
            break
    assert player.inventory.count(MANUAL) == 1
    assert player.get_flag(MANUAL_FLAG) is True

    for _ in range(6):
        _capture(handle_explore, player)
    assert player.inventory.count(MANUAL) == 1


def test_duanhun_manual_respects_level_and_consumes_only_on_success():
    low = Player("剑谱门槛", "少林")
    low.level = 11
    low.inventory.append(MANUAL)
    assert apply_consumable(low, MANUAL) is False
    assert low.inventory.count(MANUAL) == 1
    assert low.get_skill_progress(SKILL)["learned"] is False

    ready = Player("剑谱研习", "少林")
    ready.level = 12
    ready.inventory.append(MANUAL)
    assert apply_consumable(ready, MANUAL) is True
    assert ready.inventory.count(MANUAL) == 0
    assert ready.get_skill_progress(SKILL)["learned"] is True

    ready.inventory.append(MANUAL)
    assert apply_consumable(ready, MANUAL) is False
    assert ready.inventory.count(MANUAL) == 1


def test_duanhun_skill_is_castable_across_sects_after_learning():
    for sect in ("少林", "华山", "散人"):
        player = Player("跨门剑法", sect)
        player.level = 12
        player.inventory.append(MANUAL)
        assert apply_consumable(player, MANUAL) is True
        learned = {entry["name"]: entry for entry in player.get_available_skills()}
        assert SKILL in learned, sect
        assert learned[SKILL]["effect"]["status"] == "armor_break"
        assert learned[SKILL]["power"] == 2.45


def test_duanhun_accessory_is_equippable_and_feeds_affix_totals():
    item = engine.ITEMS[ACCESSORY]
    assert (item["type"], item["slot"]) == ("accessory", "accessory")
    assert item["defense"] == 2
    assert item["crit_bonus"] == 0.01
    assert item["attribute_bonus"] == {"insight": 1}

    player = Player("护符佩戴验收", "散人")
    player.inventory.append(ACCESSORY)
    defense_before = player.get_total_defense()
    insight_before = player.get_effective_attribute("insight")

    ok, message = player.equip_item(ACCESSORY)
    assert ok and "饰品" in message
    assert player.equipment["accessory"] == ACCESSORY
    assert player.get_total_defense() == defense_before + 2
    assert player.get_effective_attribute("insight") == insight_before + 1
    assert player.get_equipment_affixes()["crit_bonus"] == 0.01

    output, _ = _capture(show_equipment, player)
    assert "饰品：" in output and ACCESSORY in output

    ok, _ = player.unequip_item("accessory")
    assert ok
    assert player.equipment.get("accessory") is None
    assert player.inventory.count(ACCESSORY) == 1
    assert player.get_total_defense() == defense_before
    assert player.get_effective_attribute("insight") == insight_before


def test_existing_sect_accessories_share_the_same_slot_rules():
    player = Player("旧饰品验收", "少林")
    player.inventory.append("菩提念珠")
    defense_before = player.get_total_defense()
    ok, _ = player.equip_item("菩提念珠")
    assert ok
    assert player.get_total_defense() == defense_before + engine.ITEMS["菩提念珠"]["defense"]
    assert player.get_effective_attribute("insight") == player.get_attribute("insight") + 1


def test_accessory_slot_survives_a_v12_roundtrip(tmp_path):
    player = Player("护符存档", "散人")
    player.inventory.append(ACCESSORY)
    assert player.equip_item(ACCESSORY)[0] is True

    path = tmp_path / "alpha310_accessory.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert engine.SAVE_VERSION == 12
    assert loaded.equipment.get("accessory") == ACCESSORY
    assert loaded.get_total_defense() == player.get_total_defense()
    assert loaded.get_equipment_affixes()["crit_bonus"] == 0.01


def test_duanhun_exchange_quests_are_gated_non_exp_repeatables():
    quests = _data("quests.json")
    expected = {
        PELT_QUEST: ("守祠老妪", "狼皮", 3, {"gold": 15, "item": "护体丹"}),
        BLADE_QUEST: ("守冢老人", "断剑残锋", 1, {"gold": 20, "item": "断魂精铁"}),
    }
    for name, (npc, target, count, reward) in expected.items():
        quest = quests[name]
        assert quest["npc"] == quest["turn_in_npc"] == npc
        assert quest["target_type"] == "collect"
        assert quest["target_name"] == target
        assert quest["required_cnt"] == count
        assert quest["requires"] == {"level": 14, "flags": [PREREQUISITE]}
        assert quest["reward"] == reward
        assert quest["repeat_reward"] == reward
        assert quest["repeatable"] is True and quest["retryable"] is True
        assert quest["repeat_cooldown_ticks"] == 12
        assert "exp" not in reward

    assert sum(info.get("reward", {}).get("exp", 0) for info in quests.values()) == 16114


def test_pelt_exchange_consumes_three_hides_for_medicine(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = _ridge_player("皮货换药验收")
    output, _ = _capture(handle_quest, player, "jiequ", [PELT_QUEST])
    assert "已接取任务" in output
    assert player.active_quests[PELT_QUEST] == 0

    player.inventory.extend(["狼皮", "狼皮"])
    player.active_quests[PELT_QUEST] = 3
    output, _ = _capture(handle_quest, player, "jiaofu", [PELT_QUEST])
    assert "交付失败" in output
    assert player.inventory.count("狼皮") == 2

    player.inventory.append("狼皮")
    gold_before = player.gold
    output, _ = _capture(handle_quest, player, "jiaofu", [PELT_QUEST])
    assert "恭喜完成任务" in output
    assert player.inventory.count("狼皮") == 0
    assert player.inventory.count("护体丹") == 1
    assert player.gold == gold_before + 15
    assert PELT_QUEST in player.completed_quests


def test_blade_exchange_trades_one_scrap_for_iron(monkeypatch):
    monkeypatch.setattr(Player, "save_to_file", lambda self, filename=None: True)
    player = _ridge_player("断锋回炉验收")
    output, _ = _capture(handle_quest, player, "jiequ", [BLADE_QUEST])
    assert "已接取任务" in output

    player.inventory.append("断剑残锋")
    player.active_quests[BLADE_QUEST] = 1
    gold_before = player.gold
    output, _ = _capture(handle_quest, player, "jiaofu", [BLADE_QUEST])
    assert "恭喜完成任务" in output
    assert player.inventory.count("断剑残锋") == 0
    assert player.inventory.count("断魂精铁") == 1
    assert player.gold == gold_before + 20
    assert BLADE_QUEST in player.completed_quests


def test_duanhun_exchanges_reject_players_without_the_fort_flag():
    player = Player("未破堡验收", "散人")
    player.level = 14
    player.location = "duanhun_rain_shrine"
    for quest_name in (PELT_QUEST, BLADE_QUEST):
        output, _ = _capture(handle_quest, player, "jiequ", [quest_name])
        assert "接取失败" in output
        assert quest_name not in player.active_quests


def test_duanhun_material_hints_point_to_exchange_npcs():
    items = engine.ITEMS
    assert "守祠老妪" in items["狼皮"]["use_hint"]
    assert "守冢老人" in items["断剑残锋"]["use_hint"]
    npcs = _data("npcs.json")
    assert PELT_QUEST in npcs["守祠老妪"]["quests"]
    assert BLADE_QUEST in npcs["守冢老人"]["quests"]
