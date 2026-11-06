"""Alpha212: data-reference and player-facing content audit regressions."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def test_every_room_exit_points_to_an_existing_room():
    rooms = load("rooms")
    for room_id, room in rooms.items():
        for direction, target in room.get("exits", {}).items():
            assert target in rooms, f"{room_id} 的{direction}出口指向不存在的场景：{target}"
        for direction, entry in room.get("hidden_exits", {}).items():
            if isinstance(entry, dict) and entry.get("target"):
                assert entry["target"] in rooms, f"{room_id} 的隐藏出口{direction}指向不存在的场景"


def test_every_fixed_room_npc_reference_exists():
    rooms = load("rooms")
    npcs = load("npcs")
    for room_id, room in rooms.items():
        for npc_name in room.get("npcs", []) or []:
            assert npc_name in npcs, f"{room_id} 引用了不存在的固定 NPC：{npc_name}"


def test_quest_givers_turn_ins_and_reward_items_exist():
    quests, npcs, items = load("quests"), load("npcs"), load("items")
    for quest_id, quest in quests.items():
        for field in ("npc", "turn_in_npc"):
            npc_name = quest.get(field)
            if npc_name:
                assert npc_name in npcs, f"任务《{quest_id}》的{field}不存在：{npc_name}"
        reward = quest.get("reward", {})
        if isinstance(reward, dict):
            for field in ("item", "item_id"):
                item_name = reward.get(field)
                if item_name:
                    assert item_name in items, f"任务《{quest_id}》奖励物品不存在：{item_name}"


def test_player_facing_item_descriptions_have_no_generic_template_filler():
    items = load("items")
    filler = "材质与做工虽不算华贵，却能看出制作者留下的用心。"
    for item_name, item in items.items():
        assert filler not in item.get("desc", ""), f"物品《{item_name}》仍有通用模板描述"
    assert "复耗损之内力" not in items["回内丹"].get("desc", "")


def test_skill_descriptions_and_combat_hints_are_not_generic_templates():
    skills = load("skills")
    generic_desc = "讲究招式与内息相合，须在实战中反复体会，方能发挥完整威力。"
    generic_hint = "施展前留意自身内力与招式等级。"
    for sect, rows in skills.items():
        for skill in rows:
            assert generic_desc not in skill.get("desc", ""), f"{sect}的《{skill.get('name')}》仍是通用描述"
            assert skill.get("combat_hint") != generic_hint, f"{sect}的《{skill.get('name')}》仍是通用战斗提示"


def test_all_regions_remain_connected_to_the_starting_world():
    rooms = load("rooms")
    start = "village_gate"
    assert start in rooms
    seen = {start}
    pending = [start]
    while pending:
        room_id = pending.pop()
        room = rooms[room_id]
        targets = list((room.get("exits") or {}).values())
        for entry in (room.get("hidden_exits") or {}).values():
            if isinstance(entry, dict) and entry.get("target"):
                targets.append(entry["target"])
        for target in targets:
            if target in rooms and target not in seen:
                seen.add(target)
                pending.append(target)
    missing = sorted(set(rooms) - seen)
    assert not missing, f"存在无法从起始世界抵达的场景：{missing}"
