import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))


def test_wudang_route_is_connected_to_existing_world():
    rooms = load('rooms.json')
    assert '南' not in rooms['official_road_east_1']['exits']
    assert rooms['official_road_east_2']['exits']['北'] == 'road_wudang_turnoff'
    route = ['official_road_east_2', 'road_wudang_turnoff', 'road_wudang_old_post', 'road_wudang_mountain_path', 'wudang_foothill']
    for a, b in zip(route, route[1:]):
        assert b in rooms[a]['exits'].values()
        assert any(target == a for target in rooms[b]['exits'].values())
    chain = ['wudang_foothill', 'wudang_pine_path', 'wudang_stone_steps', 'wudang_gate']
    for a, b in zip(chain, chain[1:]):
        assert b in rooms[a]['exits'].values()
        assert any(target == a for target in rooms[b]['exits'].values())


def test_wudang_internal_rooms_have_reciprocal_exits_and_valid_coordinates():
    rooms = load('rooms.json')
    ids = [key for key in rooms if key.startswith('wudang_')]
    assert len(ids) >= 9
    coords = set()
    for rid in ids:
        room = rooms[rid]
        coord = room.get('coord')
        assert isinstance(coord, list) and len(coord) == 2
        assert tuple(coord) not in coords
        coords.add(tuple(coord))
        for direction, target in room.get('exits', {}).items():
            assert target in rooms
            if rooms[target].get('zone') == room.get('zone'):
                opposite = {'北':'南','南':'北','东':'西','西':'东'}[direction]
                assert rooms[target].get('exits', {}).get(opposite) == rid


def test_wudang_access_gates_and_teaching_npcs_are_present():
    rooms = load('rooms.json')
    npcs = load('npcs.json')
    assert rooms['wudang_outer_court']['access']['sect'] == '武当'
    assert rooms['wudang_training_ground']['access']['sect'] == '武当'
    assert rooms['wudang_disciple_courtyard']['access']['sect'] == '武当'
    assert rooms['wudang_zhenwu_hall']['access']['min_rank_index'] == 2
    for rid in ['wudang_gate', 'wudang_guest_hall', 'wudang_outer_court', 'wudang_training_ground']:
        for name in rooms[rid].get('npcs', []):
            assert name in npcs
    assert '太极剑' in str(npcs['武当传功师父']['dialogue_choices'])
    assert '绵掌' in str(npcs['武当传功师兄']['dialogue_choices'])
    assert '两仪剑诀' in str(npcs['武当传功师兄']['dialogue_choices'])


def test_wudang_world_region_exists():
    regions = json.loads((ROOT / 'data' / 'world_regions.json').read_text(encoding='utf-8'))
    assert regions['wudang_mountain']['name'] == '武当山'
    assert regions['wudang_mountain']['recommended_level'] == 3
