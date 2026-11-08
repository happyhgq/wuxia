# -*- coding: utf-8 -*-
"""Alpha309：断魂岭 L14–15 支线扩容（狼谷、旧营、岭雨祠、哨塔、剑冢、粮道）。"""
import collections
import contextlib
import io
import json
from pathlib import Path

import combat
import engine
from actions import _conditional_dialogue_text, handle_quest, handle_talk_and_ask
from player import Player

ROOT = Path(__file__).resolve().parents[1]

DIRECTION_VECTORS = {"北": (0, 1), "南": (0, -1), "东": (1, 0), "西": (-1, 0)}

EXPANDED_ROOMS = {
    "duanhun_wolf_den": ("狼谷", [2, 6], {"东": "duanhun_trail", "北": "duanhun_old_camp"}, ["断魂岭恶狼"]),
    "duanhun_old_camp": ("黑风旧营", [2, 7], {"南": "duanhun_wolf_den", "东": "duanhun_ravine", "北": "duanhun_rain_shrine"}, ["黑风寨残兵"]),
    "duanhun_rain_shrine": ("岭雨祠", [2, 8], {"南": "duanhun_old_camp"}, []),
    "duanhun_watchtower": ("断魂哨塔", [5, 6], {"西": "duanhun_cliff"}, ["岭道弩手", "断魂岭马贼"]),
    "duanhun_sword_grave": ("断魂剑冢", [4, 7], {"南": "duanhun_cliff"}, ["守冢剑客"]),
    "duanhun_supply_cave": ("堡后粮道", [4, 8], {"西": "duanhun_fort_gate"}, []),
}

EXPANDED_ENEMIES = {
    "断魂岭恶狼": (450, 60, 17, 200, 60, 14, "normal"),
    "黑风寨残兵": (450, 60, 17, 200, 100, 14, "normal"),
    "守冢剑客": (672, 70, 22, 396, 150, 15, "elite"),
}

EXPANDED_QUESTS = {
    "断魂岭·狼谷除患": {
        "npc": "守岭猎户",
        "target_type": "kill",
        "target_name": "断魂岭恶狼",
        "required_cnt": 3,
        "difficulty": "高难",
        "exp": 620,
        "gold": 180,
    },
    "断魂岭·寻回镖货": {
        "npc": "落难镖师",
        "target_type": "collect",
        "target_name": "镖局镖箱",
        "required_cnt": 3,
        "difficulty": "进阶",
        "exp": 200,
        "gold": 180,
    },
    "断魂岭·剑冢旧誓": {
        "npc": "守冢老人",
        "target_type": "kill",
        "target_name": "守冢剑客",
        "required_cnt": 1,
        "difficulty": "高难",
        "exp": 340,
        "gold": 200,
    },
}

PREREQUISITE = "quest_completed:断魂岭·破堡除凶"


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def test_expanded_rooms_keep_reciprocal_vectors_and_extend_the_ridge():
    rooms = engine.ROOMS
    for room_id, (name, coord, exits, _) in EXPANDED_ROOMS.items():
        room = rooms[room_id]
        assert room["name"] == name
        assert room["zone"] == "duanhun_ridge"
        assert room["coord"] == coord
        assert room["exits"] == exits
        assert room["exploration_events"]
        for direction, target in exits.items():
            dx, dy = DIRECTION_VECTORS[direction]
            assert rooms[target]["coord"] == [coord[0] + dx, coord[1] + dy], (room_id, direction)

    ridge_rooms = [rid for rid, room in rooms.items() if room.get("zone") == "duanhun_ridge"]
    assert len(ridge_rooms) == 12
    for room_id in ridge_rooms:
        for direction, target in rooms[room_id]["exits"].items():
            assert target in rooms, (room_id, direction)
            if rooms[target].get("zone") != "duanhun_ridge":
                continue
            opposite = {"北": "南", "南": "北", "东": "西", "西": "东"}[direction]
            assert rooms[target]["exits"].get(opposite) == room_id, (room_id, direction, target)

    seen = {"village_square"}
    queue = collections.deque(["village_square"])
    while queue:
        room_id = queue.popleft()
        for target in rooms[room_id].get("exits", {}).values():
            if target in rooms and target not in seen:
                seen.add(target)
                queue.append(target)
    assert set(EXPANDED_ROOMS) <= seen


def test_expanded_rooms_carry_expected_levels_danger_and_residents():
    rooms = engine.ROOMS
    expected = {
        "duanhun_wolf_den": (14, "high", False, False),
        "duanhun_old_camp": (14, "extreme", False, False),
        "duanhun_rain_shrine": (14, "normal", True, True),
        "duanhun_watchtower": (13, "high", False, False),
        "duanhun_sword_grave": (15, "extreme", False, False),
        "duanhun_supply_cave": (14, "extreme", False, True),
    }
    for room_id, (level, danger, safe, indoor) in expected.items():
        room = rooms[room_id]
        assert room["difficulty_level"] == level
        assert room["recommended_level"] == level
        assert room["danger"] == danger
        assert bool(room.get("safe")) is safe
        assert bool(room.get("indoor")) is indoor

    assert rooms["duanhun_rain_shrine"]["npcs"] == ["守冢老人", "守祠老妪"]
    assert rooms["duanhun_supply_cave"]["npcs"] == ["落难镖师"]
    for room_id, (_, _, _, enemies) in EXPANDED_ROOMS.items():
        assert rooms[room_id].get("enemies", []) == enemies


def test_expanded_enemies_follow_tier_templates_and_drop_gradient():
    enemies = engine.ENEMIES
    for name, (hp, atk, defense, exp, gold, level, tier) in EXPANDED_ENEMIES.items():
        enemy = enemies[name]
        assert (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"], enemy["gold"]) == (hp, atk, defense, exp, gold)
        assert enemy["level"] == level
        assert enemy["tier"] == tier
        for drop in enemy["drops"]:
            assert drop["item"] in engine.ITEMS, (name, drop)
        if enemy.get("equipment"):
            assert enemy["equipment"]["weapon"] in engine.ITEMS
            assert enemy["equipment"]["armor"] in engine.ITEMS
            assert 0 < enemy["equipment_drop_chance"] <= 0.05

    wolf = enemies["断魂岭恶狼"]
    assert "equipment" not in wolf
    assert wolf["ai"]["style"] == "beast"
    assert [drop["item"] for drop in wolf["drops"]] == ["狼皮", "野猪肉"]

    remnant = enemies["黑风寨残兵"]
    assert remnant["drops"][0] == {"item": "镖局镖箱", "chance": 1.0, "guaranteed": True}
    assert remnant["loadout_variants"]
    assert sum(entry["weight"] for entry in remnant["loadout_variants"]) > 0

    swordsman = enemies["守冢剑客"]
    assert swordsman["respawn_seconds"] == 240
    assert swordsman["loadout_variants"]
    assert [drop["item"] for drop in swordsman["drops"]] == ["断剑残锋", "大还丹"]


def test_expanded_enemies_do_not_scale_beyond_room_level():
    rooms = engine.ROOMS
    for room_id, (_, _, _, enemies) in EXPANDED_ROOMS.items():
        room_level = rooms[room_id]["difficulty_level"]
        for enemy_name in enemies:
            profile = combat.get_enemy_profile(enemy_name, room_id)
            base_level = engine.ENEMIES[enemy_name]["level"]
            assert profile["level"] == max(base_level, room_level), (room_id, enemy_name)
            assert profile["growth_levels"] == max(0, room_level - base_level)
            assert profile["difficulty_level"] == room_level


def test_expanded_kill_quest_exp_matches_room_profiles():
    quests = _data("quests.json")
    for name, (enemy_name, room_id) in {
        "断魂岭·狼谷除患": ("断魂岭恶狼", "duanhun_wolf_den"),
        "断魂岭·剑冢旧誓": ("守冢剑客", "duanhun_sword_grave"),
    }.items():
        quest = quests[name]
        profile = combat.get_enemy_profile(enemy_name, room_id)
        combat_exp = profile["exp"] * quest["required_cnt"]
        ratio = quest["reward"]["exp"] / combat_exp
        assert 0.8 <= ratio <= 1.2, (name, ratio)


def test_expanded_items_are_registered_with_expected_value():
    items = engine.ITEMS
    assert (items["狼皮"]["type"], items["狼皮"]["price"], items["狼皮"]["id"]) == ("material", 18, "lang pi")
    assert (items["镖局镖箱"]["type"], items["镖局镖箱"]["price"], items["镖局镖箱"]["id"]) == ("quest", 0, "biao ju biao xiang")
    assert (items["断剑残锋"]["type"], items["断剑残锋"]["price"], items["断剑残锋"]["id"]) == ("material", 60, "duan jian can feng")
    for name in ("狼皮", "镖局镖箱", "断剑残锋"):
        assert items[name]["desc"]
        assert items[name]["use_hint"]


def test_expanded_npcs_are_always_available_in_their_rooms():
    npcs = _data("npcs.json")
    expected = {
        "落难镖师": ("duanhun_supply_cave", ["断魂岭·寻回镖货"]),
        "守冢老人": ("duanhun_rain_shrine", ["断魂岭·剑冢旧誓"]),
        "守祠老妪": ("duanhun_rain_shrine", []),
    }
    assert len(npcs) == 77
    for name, (home_room, quests) in expected.items():
        info = npcs[name]
        assert info["home_room"] == home_room
        assert info.get("quests", []) == quests
        assert info["schedule_tier"] == "T3"
        assert info["always_available"] is True
        assert info["scene_status"].strip()
        assert "daily_schedule" not in info
        assert info["talk_verb"].endswith("道")
        for field in ("appearance", "voice", "demeanor", "behavior_hint"):
            assert info[field].strip(), (name, field)


def test_expanded_quests_form_a_gated_l14_l15_chain():
    quests = _data("quests.json")
    assert len(quests) == 71
    for name, expected in EXPANDED_QUESTS.items():
        quest = quests[name]
        assert quest["npc"] == expected["npc"]
        assert quest["turn_in_npc"] == expected["npc"]
        assert quest["target_type"] == expected["target_type"]
        assert quest["target_name"] == expected["target_name"]
        assert quest["required_cnt"] == expected["required_cnt"]
        assert quest["difficulty"] == expected["difficulty"]
        assert quest["reward"]["exp"] == expected["exp"]
        assert quest["reward"]["gold"] == expected["gold"]
        assert PREREQUISITE in quest["requires"]["flags"]

    wolf = quests["断魂岭·狼谷除患"]
    assert wolf["requires"]["level"] == 14
    assert wolf["reward"]["items"] == [{"item": "金创药", "quantity": 2}]
    assert wolf["on_complete"] == {
        "set_flags": {"duanhun_ridge:wolf_cleared": True},
        "relations": {"守岭猎户": 3},
    }

    cargo = quests["断魂岭·寻回镖货"]
    assert cargo["requires"]["level"] == 14
    assert cargo["reward"]["items"] == [{"item": "金创药", "quantity": 3}]
    assert cargo["on_complete"] == {
        "set_flags": {"duanhun_ridge:cargo_recovered": True},
        "relations": {"落难镖师": 8},
    }

    oath = quests["断魂岭·剑冢旧誓"]
    assert oath["requires"]["level"] == 15
    assert oath["requires"]["flags"] == [PREREQUISITE, "quest_completed:断魂岭·寻回镖货"]
    assert oath["on_complete"] == {
        "set_flags": {"duanhun_ridge:sword_oath_kept": True},
        "relations": {"守冢老人": 5},
        "region_effects": {"duanhun_ridge": {"security": 4, "travel": 2}},
    }
    assert [entry["item"] for entry in oath["reward"]["items"]] == ["断魂精铁", "大还丹"]


def test_cargo_quest_turns_in_only_with_three_boxes_and_consumes_them():
    player = Player("镖货回收验收", "散人")
    player.level = 14
    player.location = "duanhun_supply_cave"
    player.set_flag(PREREQUISITE, True)

    _capture(handle_talk_and_ask, player, ["落难镖师", "接受委托", "断魂岭·寻回镖货"])
    assert "断魂岭·寻回镖货" in player.active_quests

    player.inventory.extend(["镖局镖箱", "镖局镖箱"])
    for _ in range(3):
        _capture(player.update_quest_progress, "镖局镖箱", event_type="collect")
    output, _ = _capture(handle_quest, player, "jiaofu", ["断魂岭·寻回镖货"])
    assert "交付失败" in output
    assert "断魂岭·寻回镖货" in player.active_quests

    player.inventory.append("镖局镖箱")
    gold_before = player.gold
    relation_before = player.get_relation("落难镖师")
    _capture(handle_quest, player, "jiaofu", ["断魂岭·寻回镖货"])

    assert "断魂岭·寻回镖货" in player.completed_quests
    assert "断魂岭·寻回镖货" not in player.active_quests
    assert player.get_flag("duanhun_ridge:cargo_recovered") is True
    assert player.get_relation("落难镖师") == relation_before + 8
    assert player.inventory.count("镖局镖箱") == 0
    assert player.inventory.count("金创药") == 3
    assert player.gold == gold_before + 180


def test_sword_oath_applies_flags_relation_and_region_effects():
    player = Player("剑冢旧誓验收", "散人")
    player.level = 15
    player.location = "duanhun_rain_shrine"
    player.set_flag(PREREQUISITE, True)
    player.set_flag("quest_completed:断魂岭·寻回镖货", True)

    _capture(handle_talk_and_ask, player, ["守冢老人", "接受委托", "断魂岭·剑冢旧誓"])
    assert "断魂岭·剑冢旧誓" in player.active_quests
    _capture(player.update_quest_progress, "守冢剑客")
    relation_before = player.get_relation("守冢老人")
    _capture(handle_quest, player, "jiaofu", ["断魂岭·剑冢旧誓"])

    assert "断魂岭·剑冢旧誓" in player.completed_quests
    assert player.get_flag("duanhun_ridge:sword_oath_kept") is True
    assert player.get_relation("守冢老人") == relation_before + 5
    assert player.inventory.count("断魂精铁") >= 1
    assert player.inventory.count("大还丹") >= 1
    region = player.get_var("region_activity", {})["duanhun_ridge"]
    assert region["security"] == 4
    assert region["travel"] == 2


def test_new_flags_drive_conditional_dialogue_for_ridge_npcs():
    player = Player("岭上条件台词", "散人")
    assert _conditional_dialogue_text(player, engine.NPCS["守冢老人"]) is None

    player.set_flag("duanhun_ridge:sword_oath_kept", True)
    text = _conditional_dialogue_text(player, engine.NPCS["守冢老人"])
    assert "剑都扶正了" in text

    assert _conditional_dialogue_text(player, engine.NPCS["守岭猎户"]) is None
    player.set_flag("duanhun_ridge:wolf_cleared", True)
    text = _conditional_dialogue_text(player, engine.NPCS["守岭猎户"])
    assert "狼谷安静了" in text


def test_quest_detail_renders_item_rewards_without_raw_dicts():
    player = Player("奖励显示验收", "散人")

    output, _ = _capture(handle_quest, player, "quests", ["断魂岭·寻回镖货"])
    assert "物品 金创药×3" in output
    reward_line = output.split("奖励：", 1)[1].splitlines()[0]
    assert "{" not in reward_line and "'item'" not in reward_line

    output, _ = _capture(handle_quest, player, "quests", ["断魂岭·破堡除凶"])
    assert "物品 断魂刀、苍脊重甲" in output

    output, _ = _capture(handle_quest, player, "quests", ["断魂岭·精铁换药"])
    assert "物品 大还丹" in output


def test_v12_roundtrip_preserves_expanded_quest_progress_and_flags(tmp_path):
    player = Player("断魂岭扩容存档", "散人")
    player.level = 14
    player.location = "duanhun_supply_cave"
    player.active_quests = {"断魂岭·寻回镖货": 2}
    player.quest_states = {
        "断魂岭·寻回镖货": {"stage": 0, "progress": 2, "branch_pending": False, "accepted_at": 240}
    }
    player.completed_quests = ["断魂岭·破堡除凶"]
    player.world_state["flags"]["duanhun_ridge:cargo_recovered"] = True

    path = tmp_path / "alpha309_duanhun_expansion.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert engine.SAVE_VERSION == 12
    assert loaded.level == 14
    assert loaded.location == "duanhun_supply_cave"
    assert loaded.active_quests == player.active_quests
    assert loaded.quest_states == player.quest_states
    assert loaded.completed_quests == player.completed_quests
    assert loaded.get_flag("duanhun_ridge:cargo_recovered") is True
