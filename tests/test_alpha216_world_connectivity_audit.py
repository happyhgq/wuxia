"""Alpha216：全地图连通、隐藏入口和动态 NPC 场景配置审计。"""
import json
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def test_every_room_is_reachable_from_start_when_discovered_hidden_routes_are_included():
    rooms = load("rooms")
    start = "village_gate"
    assert start in rooms
    graph = {room_id: set((room.get("exits") or {}).values()) for room_id, room in rooms.items()}
    for room_id, room in rooms.items():
        for hidden in (room.get("hidden_exits") or {}).values():
            if isinstance(hidden, dict) and hidden.get("target"):
                graph[room_id].add(hidden["target"])
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in graph[current]:
            assert target in rooms, f"场景 {current} 指向不存在的地点 {target}"
            if target not in seen:
                seen.add(target)
                queue.append(target)
    assert seen == set(rooms), f"存在无法从起始世界抵达的场景：{sorted(set(rooms) - seen)}"


def test_hidden_exits_have_valid_targets_and_discovery_flags():
    rooms = load("rooms")
    for room_id, room in rooms.items():
        for direction, hidden in (room.get("hidden_exits") or {}).items():
            assert isinstance(hidden, dict), (room_id, direction, hidden)
            assert hidden.get("target") in rooms, (room_id, direction, hidden)
            assert isinstance(hidden.get("flag"), str) and hidden["flag"], (room_id, direction, hidden)


def test_duplicate_fixed_npc_placements_must_match_a_declared_dynamic_route():
    rooms, npcs = load("rooms"), load("npcs")
    placements = defaultdict(set)
    for room_id, room in rooms.items():
        for name in room.get("npcs") or []:
            placements[name].add(room_id)
    for name, room_ids in placements.items():
        if len(room_ids) <= 1:
            continue
        info = npcs.get(name, {})
        route = set((info.get("autonomy_profile") or {}).get("route") or [])
        # 分层日程（T1/T2）与住址同样解释了同一人物为何出现在多个固定场景。
        route |= {entry.get("location") for entry in info.get("daily_schedule") or []
                  if entry.get("location")}
        if info.get("home_room"):
            route.add(info["home_room"])
        assert room_ids <= route, (
            f"NPC {name} 在多个固定场景重复配置，但没有覆盖这些地点的动态路线："
            f"placements={sorted(room_ids)}, route={sorted(route)}"
        )
