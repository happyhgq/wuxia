import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def test_residential_rooms_exist_and_are_connected():
    rooms = json.loads((BASE / 'data' / 'rooms.json').read_text(encoding='utf-8'))
    required = {'residents_lane', 'public_well', 'public_drying_yard', 'sun_aunt_yard', 'old_qiu_residence', 'farm_lane', 'farmer_ahe_yard', 'vacant_yard'}
    assert required <= rooms.keys()
    assert rooms['village_north_street']['exits']['东'] == 'residents_lane'
    assert rooms['residents_lane']['exits']['西'] == 'village_north_street'
    assert rooms['residents_lane']['exits']['东'] == 'public_well'
    assert rooms['farm_lane']['exits']['南'] == 'vacant_yard'


def test_private_houses_have_access_rules_and_future_yard_is_open():
    rooms = json.loads((BASE / 'data' / 'rooms.json').read_text(encoding='utf-8'))
    for room_id, owner in [('sun_aunt_yard', '菜贩孙婶'), ('old_qiu_residence', '挑水老邱'), ('farmer_ahe_yard', '农家阿禾')]:
        access = rooms[room_id]['residence']
        assert access['private'] is True
        assert access['owner'] == owner
        assert access['trust_required'] == 20
    assert rooms['vacant_yard']['residence']['reserved_for_future_player_home'] is True
    assert rooms['vacant_yard']['residence']['private'] is False


def test_new_rooms_have_unique_coordinates_and_valid_cardinal_links():
    rooms = json.loads((BASE / 'data' / 'rooms.json').read_text(encoding='utf-8'))
    vectors = {'北': (0, 1), '南': (0, -1), '东': (1, 0), '西': (-1, 0)}
    vertical = {'上', '下'}
    custom = {'内', '外', '后', '前'}
    seen = {}
    for rid, room in rooms.items():
        key = (room.get('zone', 'main'), tuple(room['coord']))
        assert key not in seen, f'duplicate coordinate {key}: {seen.get(key)} / {rid}'
        seen[key] = rid
        for direction, target in room.get('exits', {}).items():
            assert direction in vectors or direction in vertical or direction in custom
            assert target in rooms
            if room.get('zone', 'main') == rooms[target].get('zone', 'main') and direction in vectors:
                dx, dy = vectors[direction]
                x, y = room['coord']
                assert rooms[target]['coord'] == [x + dx, y + dy], (rid, direction, target)
