"""Alpha189：门派道路连接专项审计，避免少林与武当共用同一入口节点。"""
import json
from collections import deque, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOMS = json.loads((ROOT / 'data' / 'rooms.json').read_text(encoding='utf-8'))
OPPOSITE = {
    '北': '南', '南': '北', '东': '西', '西': '东',
    '内': '外', '外': '内', '后': '前', '前': '后',
}


def test_every_normal_exit_points_to_a_real_room_and_same_zone_links_return():
    for room_id, room in ROOMS.items():
        for direction, target in (room.get('exits') or {}).items():
            assert target in ROOMS, f'{room_id} 的{direction}出口指向不存在的地点 {target}'
            if ROOMS[target].get('zone', 'main') == room.get('zone', 'main'):
                opposite = OPPOSITE[direction]
                back = ROOMS[target].get('exits', {}).get(opposite) == room_id
                hidden_back = any(
                    isinstance(entry, dict) and entry.get('target') == room_id
                    for entry in (ROOMS[target].get('hidden_exits') or {}).values()
                )
                assert back or hidden_back, (
                    f'{room_id} 的{direction}出口与 {target} 不构成双向道路'
                )


def test_map_coordinates_are_unique_inside_each_zone():
    occupied = defaultdict(dict)
    for room_id, room in ROOMS.items():
        coord = room.get('coord')
        if not (isinstance(coord, list) and len(coord) == 2):
            continue
        zone = room.get('zone', 'main')
        point = tuple(coord)
        assert point not in occupied[zone], (
            f'{zone} 区域坐标 {point} 被 {occupied[zone].get(point)} 与 {room_id} 重复使用'
        )
        occupied[zone][point] = room_id


def test_shaolin_and_wudang_use_distinct_world_junctions():
    # Shaolin remains on the north branch of the eastern road segment.
    assert ROOMS['official_road_east_1']['exits']['北'] == 'songshan_foothill'
    assert '南' not in ROOMS['official_road_east_1']['exits']
    # Wudang now has a separate three-step approach from the next road segment.
    route = [
        'official_road_east_2', 'road_wudang_turnoff', 'road_wudang_old_post',
        'road_wudang_mountain_path', 'wudang_foothill', 'wudang_pine_path',
        'wudang_stone_steps', 'wudang_gate',
    ]
    for a, b in zip(route, route[1:]):
        assert b in ROOMS[a]['exits'].values(), f'{ROOMS[a]["name"]} 无法前往 {ROOMS[b]["name"]}'
        assert any(target == a for target in ROOMS[b]['exits'].values()), f'{ROOMS[b]["name"]} 无法沿路返回'
    assert ROOMS['wudang_foothill']['exits']['西'] == 'road_wudang_mountain_path'


def test_all_rooms_are_reachable_when_discovered_hidden_passages_are_included():
    # The submerged cache is intentionally gated by a discoverable hidden exit.
    seen = {'village_gate'}
    queue = deque(['village_gate'])
    while queue:
        room_id = queue.popleft()
        room = ROOMS[room_id]
        targets = list((room.get('exits') or {}).values())
        targets.extend(
            entry.get('target')
            for entry in (room.get('hidden_exits') or {}).values()
            if isinstance(entry, dict) and entry.get('target')
        )
        for target in targets:
            if target in ROOMS and target not in seen:
                seen.add(target)
                queue.append(target)
    assert seen == set(ROOMS), f'存在无法从主世界到达的地点：{sorted(set(ROOMS) - seen)}'
