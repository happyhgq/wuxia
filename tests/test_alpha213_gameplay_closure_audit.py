"""Alpha213：补齐任务目标、场景位置与战斗效果的数据闭环审计。"""
import json
from pathlib import Path

import engine
from player import Player

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))

def test_every_quest_stage_target_exists_in_runtime_data():
    quests, npcs, enemies = load("quests"), load("npcs"), load("enemies")
    enemy_names = set(enemies) | {v.get("name") for v in enemies.values() if isinstance(v, dict)}
    for quest_id, quest in quests.items():
        stages = [{"target_type": quest.get("target_type"), "target_name": quest.get("target_name")}] + (quest.get("stages") or [])
        for index, stage in enumerate(stages):
            target, name = stage.get("target_type"), stage.get("target_name")
            if not name:
                continue
            if target == "kill":
                assert name in enemy_names, f"任务《{quest_id}》第 {index} 阶段击杀目标不存在：{name}"
            elif target == "talk":
                assert name in npcs, f"任务《{quest_id}》第 {index} 阶段交谈目标不存在：{name}"

def test_every_quest_giver_and_turn_in_has_a_scene_location():
    rooms, npcs, quests = load("rooms"), load("npcs"), load("quests")
    placed = {name for room in rooms.values() for name in (room.get("npcs") or [])}
    for quest_id, quest in quests.items():
        for field in ("npc", "turn_in_npc"):
            name = quest.get(field)
            if name:
                assert name in npcs, f"任务《{quest_id}》引用不存在的 NPC：{name}"
                assert name in placed or npcs[name].get("room"), f"任务《{quest_id}》的{field}没有场景位置：{name}"

def test_all_skill_and_item_status_effects_are_supported_by_combat():
    skills, items = load("skills"), load("items")
    valid_skill_types = {"status", "self_status", "combo", "mp_restore"}
    for sect, rows in skills.items():
        for skill in rows:
            effects = skill.get("effects")
            if not isinstance(effects, list):
                effects = [skill.get("effect", {})]
            for effect in effects:
                if not effect:
                    continue
                assert effect.get("type") in valid_skill_types, (sect, skill.get("name"), effect)
                if effect.get("type") in {"status", "self_status"}:
                    assert effect.get("status") in engine.STATUS_EFFECTS, (sect, skill.get("name"), effect)
    for name, item in items.items():
        effect = item.get("weapon_effect") or {}
        if effect.get("type") == "status":
            assert effect.get("status") in engine.STATUS_EFFECTS, (name, effect)
        effect = item.get("effect") or {}
        for key in ("status", "target_status"):
            status = effect.get(key)
            if isinstance(status, dict):
                assert status.get("name") in engine.STATUS_EFFECTS, (name, key, status)

def test_new_player_can_reach_and_unlock_the_first_village_quest():
    rooms = load("rooms")
    player = Player("新手流程闭环验收", "散人")
    assert player.location == "village_gate"
    assert "守卫" in (rooms[player.location].get("npcs") or [])
    assert rooms[player.location]["exits"]["北"] == "village_south_street"
    assert rooms["village_south_street"]["exits"]["北"] == "village_square"
    assert rooms["village_square"]["exits"]["北"] == "village_north_street"
    assert rooms["village_north_street"]["exits"]["西"] == "village_head_house"
    assert not engine.check_conditions(engine.QUESTS["清剿黑风山"].get("requires"), player.world_state, player.completed_quests, player)
    for _ in range(3):
        player.change_talk_relation("村长", 2, engine.DEFAULT_TALK_RELATION_CAP)
    # 成长修订后，《清剿黑风山》还要求等级 7 与完成村道巡查。
    player.level = 7
    player.completed_quests.append("村道巡查·清理残匪")
    assert engine.check_conditions(engine.QUESTS["清剿黑风山"].get("requires"), player.world_state, player.completed_quests, player)
