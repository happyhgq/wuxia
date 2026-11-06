# -*- coding: utf-8 -*-
"""Alpha263：V12 存档关键运行态回归。"""
import json

import engine
from player import Player


def _snapshot_player(tmp_path, player):
    path = tmp_path / "save.json"
    assert player.save_to_file(str(path)) is True
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    return loaded


def test_v12_roundtrip_preserves_quest_sect_skill_and_world_progress(tmp_path):
    player = Player("存档回归侠客", "华山")
    player.level = 18
    player.exp = 321
    player.location = "huashan_gate" if "huashan_gate" in engine.ROOMS else player.location
    player.active_quests = {"Alpha263回归任务": 2}
    player.quest_states = {
        "Alpha263回归任务": {"stage": 1, "progress": 2, "branch_pending": False, "accepted_at": 77}
    }
    player.completed_quests = ["已完成的回归任务"]
    player.change_sect_reputation("华山", 73)
    sect_state = player._ensure_sect_state()
    sect_state.setdefault("progress", {}).setdefault("华山", {})["official_rank_index"] = 2
    player._skill_state()["回归测试武学"] = {"learned": True, "mastery": 67}
    variables = player.world_state["variables"]
    variables["quest_clock"] = 456
    variables["region_ecology"] = {"mistwood": {"security": 38, "prosperity": 61, "danger": 72, "last_update": 450}}
    variables["world_events"] = {"alpha263_event": {"count": 1, "last_clock": 440}}
    variables["faction_relations"] = {"少林:黑风寨": -42, "黑风寨:少林": -42}
    variables["npc_memory"] = {"村长": {"alpha263_memory": {"strength": 55, "clock": 430}}}
    variables["random_pedestrians"] = {
        "by_room": {player.location: [{"name": "回归路人甲", "role": "行脚客"}]},
        "last_check": {player.location: 450},
        "region_population": {"main": 2},
        "region_population_clock": {"main": 450},
    }

    loaded = _snapshot_player(tmp_path, player)
    assert loaded.level == 18 and loaded.exp == 321
    assert loaded.active_quests == player.active_quests
    assert loaded.quest_states == player.quest_states
    assert loaded.completed_quests == player.completed_quests
    assert loaded.get_sect() == "华山"
    assert loaded.get_sect_reputation("华山") == 73
    assert loaded._sect_progress_state()["华山"]["official_rank_index"] == 2
    skill_progress = loaded.get_skill_progress("回归测试武学")
    assert skill_progress["learned"] is True and skill_progress["mastery"] == 67
    assert loaded.get_quest_clock() == 456
    assert loaded.get_region_ecology("mistwood")["security"] == 38
    assert loaded.world_state["variables"]["world_events"]["alpha263_event"]["count"] == 1
    assert loaded.get_faction_relation("少林", "黑风寨") == -42
    assert loaded.world_state["variables"]["npc_memory"]["村长"]["alpha263_memory"]["strength"] == 55
    assert loaded.world_state["variables"]["random_pedestrians"]["by_room"][player.location][0]["name"] == "回归路人甲"


def test_legacy_v12_missing_newer_runtime_fields_loads_with_safe_defaults(tmp_path):
    # 模拟早期 V12：没有后续版本逐步写入的门派、技能、生态和路人字段。
    legacy = {
        "version": 12, "name": "早期V12侠客", "sect": "散人", "level": 12,
        "exp": 88, "exp_to_level": 200, "hp": 80, "max_hp": 100,
        "mp": 30, "max_mp": 50, "atk": 20, "defense": 10, "gold": 99,
        "inventory": ["草药"], "equipment": {"weapon": None, "armor": None},
        "equip_enhance": {"weapon": 0, "armor": 0}, "location": "village_gate",
        "active_quests": {"旧档进行中任务": 3}, "completed_quests": ["旧档已完成任务"],
        "world_state": {"flags": {"legacy_flag": True}, "variables": {"quest_clock": 90}},
    }
    path = tmp_path / "legacy_v12.json"
    path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.name == "早期V12侠客"
    assert loaded.level == 12 and loaded.gold == 99
    assert loaded.active_quests["旧档进行中任务"] == 3
    assert "旧档已完成任务" in loaded.completed_quests
    assert loaded.world_state["flags"]["legacy_flag"] is True
    assert loaded.get_quest_clock() == 90
    assert isinstance(loaded._ensure_sect_state(), dict)
    assert isinstance(loaded._ensure_skill_state(), dict)
    assert isinstance(loaded.get_region_ecology("main"), dict)


def test_v12_migration_does_not_drop_unknown_world_variables_or_flags():
    raw = {
        "version": 12, "name": "迁移保留测试", "sect": "散人",
        "world_state": {
            "flags": {"custom_story_flag": "kept"},
            "variables": {"custom_runtime_record": {"nested": [1, 2, 3]}},
        },
    }
    migrated, old_version = engine.migrate_save_data(raw)
    assert old_version == 12
    assert migrated["version"] == engine.SAVE_VERSION == 12
    assert migrated["world_state"]["flags"]["custom_story_flag"] == "kept"
    assert migrated["world_state"]["variables"]["custom_runtime_record"] == {"nested": [1, 2, 3]}


def test_corrupt_optional_runtime_substate_is_repaired_without_losing_character(tmp_path):
    raw = {
        "version": 12, "name": "容错回归侠客", "sect": "少林", "level": 9,
        "world_state": {
            "flags": [],
            "variables": {
                "sect_state": [], "skill_progress": "bad",
                "region_ecology": [], "random_pedestrians": "bad",
            },
        },
    }
    path = tmp_path / "partially_corrupt_v12.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    loaded = Player.load_from_file(str(path))
    assert loaded is not None
    assert loaded.name == "容错回归侠客"
    assert loaded.get_sect() == "少林"
    assert isinstance(loaded._ensure_sect_state(), dict)
    assert isinstance(loaded._ensure_skill_state(), dict)
    assert isinstance(loaded.get_region_ecology("main"), dict)
