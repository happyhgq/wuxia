"""Alpha257：门派历练任务目标地点与发布/交付路线可达性审计。"""
import json
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def _reachable_rooms(rooms, starts):
    seen = set(starts)
    queue = deque(starts)
    while queue:
        room_id = queue.popleft()
        for target in rooms[room_id].get("exits", {}).values():
            if target in rooms and target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def test_all_sect_trial_givers_and_turnins_exist_in_real_rooms():
    rooms, npcs, quests = _load("rooms.json"), _load("npcs.json"), _load("quests.json")
    names = [name for name in quests if "历练" in name]
    assert names
    for quest_name in names:
        quest = quests[quest_name]
        giver = quest.get("npc")
        turn_in = quest.get("turn_in_npc") or giver
        assert giver in npcs, f"{quest_name}: 发布人不存在：{giver}"
        assert turn_in in npcs, f"{quest_name}: 交付人不存在：{turn_in}"
        giver_rooms = [rid for rid, room in rooms.items() if giver in room.get("npcs", [])]
        turnin_rooms = [rid for rid, room in rooms.items() if turn_in in room.get("npcs", [])]
        assert giver_rooms, f"{quest_name}: 发布人未配置在任何场景"
        assert turnin_rooms, f"{quest_name}: 交付人未配置在任何场景"
        assert set(giver_rooms) & set(turnin_rooms), f"{quest_name}: 发布人与交付人没有共同交付地点"


def test_all_sect_trial_targets_are_present_and_reachable_from_the_giver():
    rooms, quests = _load("rooms.json"), _load("quests.json")
    names = [name for name in quests if "历练" in name]
    for quest_name in names:
        quest = quests[quest_name]
        target = quest.get("target_name")
        assert target, f"{quest_name}: 缺少目标名称"
        target_rooms = [rid for rid, room in rooms.items() if target in room.get("enemies", [])]
        assert target_rooms, f"{quest_name}: 目标敌人没有配置在任何场景：{target}"
        giver = quest.get("npc")
        starts = [rid for rid, room in rooms.items() if giver in room.get("npcs", [])]
        reachable = _reachable_rooms(rooms, starts)
        assert any(rid in reachable for rid in target_rooms), f"{quest_name}: 从发布人场景无法到达目标敌人"


def test_sect_followup_rewards_do_not_repeat_permanent_sect_reputation():
    quests = _load("quests.json")
    for quest_name in (
        "铁衣门历练·护路除匪",
        "少林历练·巡山护戒",
        "武当历练·松径清扰",
        "华山历练·险道试剑",
        "铁衣门历练·清除巡哨",
    ):
        quest = quests[quest_name]
        if quest.get("repeatable"):
            repeat_reward = quest.get("repeat_reward", quest.get("reward", {}))
            assert not repeat_reward.get("sect_reputation"), f"{quest_name}: 重复奖励不应无限增加门派声望"
