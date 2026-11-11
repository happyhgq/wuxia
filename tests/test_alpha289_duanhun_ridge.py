# -*- coding: utf-8 -*-
"""Alpha289：断魂岭 L13–15 高等级野外路线、装备、任务链与存档回归。"""
import collections
import json
from pathlib import Path

import combat
import engine
from player import Player

ROOT = Path(__file__).resolve().parents[1]

DIRECTION_VECTORS = {"北": (0, 1), "南": (0, -1), "东": (1, 0), "西": (-1, 0)}

DUANHUN_ROOMS = {
    "duanhun_camp": ("断魂岭猎户棚", [3, 5], {"南": "bandit_old_beacon", "北": "duanhun_trail"}),
    "duanhun_trail": ("断魂岭栈道", [3, 6], {"南": "duanhun_camp", "北": "duanhun_ravine", "东": "duanhun_cliff", "西": "duanhun_wolf_den"}),
    "duanhun_cliff": ("断魂崖", [4, 6], {"西": "duanhun_trail", "北": "duanhun_sword_grave", "东": "duanhun_watchtower"}),
    "duanhun_wolf_den": ("狼谷", [2, 6], {"东": "duanhun_trail", "北": "duanhun_old_camp"}),
    "duanhun_old_camp": ("黑风旧营", [2, 7], {"南": "duanhun_wolf_den", "东": "duanhun_ravine", "北": "duanhun_rain_shrine"}),
    "duanhun_ravine": ("枯骨涧", [3, 7], {"南": "duanhun_trail", "北": "duanhun_fort_gate", "西": "duanhun_old_camp"}),
    "duanhun_rain_shrine": ("岭雨祠", [2, 8], {"南": "duanhun_old_camp"}),
    "duanhun_fort_gate": ("断魂堡门", [3, 8], {"南": "duanhun_ravine", "北": "duanhun_keep", "东": "duanhun_supply_cave"}),
    "duanhun_supply_cave": ("堡后粮道", [4, 8], {"西": "duanhun_fort_gate"}),
    "duanhun_watchtower": ("断魂哨塔", [5, 6], {"西": "duanhun_cliff"}),
    "duanhun_sword_grave": ("断魂剑冢", [4, 7], {"南": "duanhun_cliff"}),
    "duanhun_keep": ("断魂堡内厅", [3, 9], {"南": "duanhun_fort_gate"}),
}

DUANHUN_ENEMIES = {
    "断魂岭马贼": (420, 56, 16, 181, 88, 13, "normal"),
    "岭道弩手": (420, 56, 16, 181, 80, 13, "ranged"),
    "枯骨涧刀客": (450, 60, 17, 200, 96, 14, "normal"),
    "断魂堡守卫长": (630, 66, 21, 360, 140, 14, "elite"),
    "断魂堡死卫": (480, 64, 18, 220, 100, 15, "normal"),
    # Alpha316：L15 五门派实战复核后微调 864/76/22 → 920/80/23，经验与掉落不变。
    "断魂堡主": (920, 80, 23, 660, 260, 15, "boss"),
}

EQUIPMENT_BANDS = {"normal": 0.02, "ranged": 0.02, "elite": 0.05, "boss": 0.12}

DUANHUN_QUESTS = {
    "断魂岭·岭道清剿": {
        "npc": "守岭猎户",
        "target_name": "断魂岭马贼",
        "required_cnt": 3,
        "requires": {"level": 12, "flags": ["quest_completed:清剿黑风山"]},
        "reward": {"exp": 500, "gold": 120, "item": "苍脊刀", "honor_delta": 6},
    },
    "断魂岭·破堡除凶": {
        "npc": "守岭猎户",
        "target_name": "断魂堡主",
        "required_cnt": 1,
        "requires": {"level": 13, "flags": ["quest_completed:断魂岭·岭道清剿"]},
        "reward": {"exp": 680, "gold": 220, "honor_delta": 10},
    },
    "断魂岭·巡道除匪": {
        "npc": "守岭猎户",
        "target_name": "断魂岭马贼",
        "required_cnt": 2,
        "requires": {"level": 12, "flags": ["quest_completed:断魂岭·岭道清剿"]},
        "reward": {"exp": 300, "gold": 90, "honor_delta": 1},
        "repeat_reward": {"exp": 160, "gold": 60},
        "repeat_cooldown_ticks": 48,
    },
}


def _data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_duanhun_ridge_topology_connects_to_bandit_pass_without_breaking_vectors():
    rooms = engine.ROOMS
    assert engine.MapEngine.ZONE_NAMES["duanhun_ridge"] == "断魂岭"

    beacon = rooms["bandit_old_beacon"]
    assert beacon["exits"]["北"] == "duanhun_camp"
    assert beacon["coord"] == [3, 4]

    for room_id, (name, coord, exits) in DUANHUN_ROOMS.items():
        room = rooms[room_id]
        assert room["name"] == name
        assert room["zone"] == "duanhun_ridge"
        assert room["coord"] == coord
        assert room["exits"] == exits
        for direction, target in exits.items():
            assert target in rooms, (room_id, direction, target)
            dx, dy = DIRECTION_VECTORS[direction]
            assert rooms[target]["coord"] == [coord[0] + dx, coord[1] + dy], (room_id, direction)

    assert rooms["duanhun_camp"].get("safe") is True
    assert rooms["duanhun_camp"]["npcs"] == ["守岭猎户"]
    level_by_room = {
        "duanhun_camp": 13,
        "duanhun_trail": 13,
        "duanhun_cliff": 13,
        "duanhun_watchtower": 13,
        "duanhun_wolf_den": 14,
        "duanhun_old_camp": 14,
        "duanhun_rain_shrine": 14,
        "duanhun_supply_cave": 14,
        "duanhun_ravine": 14,
        "duanhun_fort_gate": 14,
        "duanhun_sword_grave": 15,
        "duanhun_keep": 15,
    }
    for room_id, level in level_by_room.items():
        room = rooms[room_id]
        assert room["difficulty_level"] == level
        assert room["recommended_level"] == level
        assert room["exploration_events"]


def test_duanhun_ridge_is_reachable_from_the_village_and_leads_to_the_keep():
    rooms = engine.ROOMS
    seen = {"village_square"}
    queue = collections.deque(["village_square"])
    while queue:
        room_id = queue.popleft()
        for target in rooms[room_id].get("exits", {}).values():
            if target in rooms and target not in seen:
                seen.add(target)
                queue.append(target)
    assert set(DUANHUN_ROOMS) <= seen
    assert "duanhun_keep" in seen


def test_duanhun_enemies_use_high_level_template_and_drop_gradient():
    enemies = engine.ENEMIES
    for name, (hp, atk, defense, exp, gold, level, tier) in DUANHUN_ENEMIES.items():
        enemy = enemies[name]
        assert (enemy["hp"], enemy["atk"], enemy["defense"], enemy["exp"], enemy["gold"]) == (hp, atk, defense, exp, gold)
        assert enemy["level"] == level
        assert enemy["tier"] == tier
        assert enemy["equipment_drop_chance"] == EQUIPMENT_BANDS[tier]
        assert enemy["equipment"]["weapon"] in engine.ITEMS
        assert enemy["equipment"]["armor"] in engine.ITEMS
        assert enemy["drops"]
        for drop in enemy["drops"]:
            assert drop["item"] in engine.ITEMS, (name, drop)
        assert "manual_drop" not in enemy

    for name in ("断魂岭马贼", "岭道弩手", "枯骨涧刀客", "断魂堡守卫长", "断魂堡死卫"):
        assert enemies[name]["loadout_variants"], name
        variant_share = sum(entry["weight"] for entry in enemies[name]["loadout_variants"])
        for entry in enemies[name]["loadout_variants"]:
            assert 0 < entry["weight"] <= variant_share
            assert entry["equipment"]["weapon"] in engine.ITEMS
            assert entry["equipment"]["armor"] in engine.ITEMS

    boss = enemies["断魂堡主"]
    assert [phase["threshold"] for phase in boss["phases"]] == [0.65, 0.3]
    assert {skill["name"] for skill in boss["skills"]} == {"断魂斩", "慑魂刀风", "绝命三连", "断魂绝刀"}
    assert boss["drops"] == [
        {"item": "大还丹", "chance": 0.6, "guaranteed": True},
        {"item": "黑风寨军械残片", "chance": 1.0, "guaranteed": True, "quantity": 2},
    ]


def test_duanhun_rooms_do_not_scale_enemies_beyond_their_own_level():
    rooms = engine.ROOMS
    for room_id, (_, _, _) in DUANHUN_ROOMS.items():
        room_level = rooms[room_id]["difficulty_level"]
        for enemy_name in rooms[room_id].get("enemies", []):
            base_level = engine.ENEMIES[enemy_name]["level"]
            profile = combat.get_enemy_profile(enemy_name, room_id)
            assert profile["level"] == max(base_level, room_level), (room_id, enemy_name)
            assert profile["growth_levels"] == max(0, room_level - base_level)
            assert profile["difficulty_level"] == room_level


def test_duanhun_gear_is_endgame_tier():
    items = engine.ITEMS
    assert (items["苍脊刀"]["atk"], items["苍脊刀"]["price"]) == (30, 480)
    assert items["苍脊刀"]["weapon_effect"]["status"] == "bleed"
    assert (items["断魂刀"]["atk"], items["断魂刀"]["price"]) == (40, 900)
    assert items["断魂刀"]["weapon_effect"]["turns"] == 3
    assert (items["苍脊重甲"]["defense"], items["苍脊重甲"]["price"]) == (18, 540)
    for name in ("苍脊刀", "断魂刀", "苍脊重甲"):
        assert items[name]["enhance_max"] == 5
        assert items[name]["enhance_ore_cost"] == 1


def test_duanhun_npc_and_quest_chain_form_a_gated_progression():
    npcs = _data("npcs.json")
    quests = _data("quests.json")
    rooms = _data("rooms.json")

    hunter = npcs["守岭猎户"]
    assert hunter["home_room"] == "duanhun_camp"
    assert hunter["quests"] == [
        "断魂岭·岭道清剿",
        "断魂岭·破堡除凶",
        "断魂岭·巡道除匪",
        "断魂岭·狼谷除患",
        "断魂岭·精铁换药",
    ]
    assert "守岭猎户" in rooms["duanhun_camp"]["npcs"]
    assert hunter["autonomy_profile"]["route"] == ["duanhun_camp"]

    for name, expected in DUANHUN_QUESTS.items():
        quest = quests[name]
        assert quest["npc"] == expected["npc"]
        assert quest["turn_in_npc"] == expected["npc"]
        assert quest["target_type"] == "kill"
        assert quest["target_name"] == expected["target_name"]
        assert quest["required_cnt"] == expected["required_cnt"]
        assert quest["requires"] == expected["requires"]
        for key, value in expected["reward"].items():
            assert quest["reward"][key] == value, (name, key)
        assert "item" not in expected["reward"] or quest["reward"]["item"] in engine.ITEMS

    assert quests["断魂岭·破堡除凶"]["reward"]["items"] == [
        {"item": "断魂刀", "quantity": 1},
        {"item": "苍脊重甲", "quantity": 1},
    ]
    assert quests["断魂岭·破堡除凶"]["on_complete"] == {
        "set_flags": {"duanhun_ridge:fort_cleared": True}
    }
    patrol = quests["断魂岭·巡道除匪"]
    assert patrol["repeatable"] is True
    assert patrol["retryable"] is True
    assert patrol["repeat_cooldown_ticks"] == 48
    assert patrol["reward"] == {"exp": 300, "gold": 90, "honor_delta": 1}
    assert patrol["repeat_reward"] == {"exp": 160, "gold": 60}


def test_duanhun_region_metadata_matches_extreme_wilderness():
    region = _data("world_regions.json")["duanhun_ridge"]
    assert region["name"] == "断魂岭"
    assert region["recommended_level"] == 13
    assert region["danger"] == "extreme"
    assert region["faction_exposure"] == ["黑风寨", "江湖"]
    assert region["region_ecology"] == {"security_base": 22, "commerce_base": 18, "travel_base": 20}
    assert region["danger_thresholds"] == {"high": 18, "extreme": 8}
    assert len(region["exploration_events"]) >= 3
    assert region["conflict_events"]


def test_v12_roundtrip_preserves_duanhun_quest_and_flag_progress(tmp_path):
    player = Player("断魂岭存档回归", "华山")
    player.level = 14
    player.location = "duanhun_ravine"
    player.active_quests = {"断魂岭·破堡除凶": 0}
    player.quest_states = {
        "断魂岭·破堡除凶": {"stage": 0, "progress": 0, "branch_pending": False, "accepted_at": 120}
    }
    player.completed_quests = ["断魂岭·岭道清剿"]
    player.world_state["flags"]["duanhun_ridge:fort_cleared"] = True

    path = tmp_path / "alpha289_duanhun.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert engine.SAVE_VERSION == 12
    assert loaded.level == 14
    assert loaded.location == "duanhun_ravine"
    assert loaded.active_quests == player.active_quests
    assert loaded.quest_states == player.quest_states
    assert loaded.completed_quests == player.completed_quests
    assert loaded.world_state["flags"]["duanhun_ridge:fort_cleared"] is True
