import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


def _npcs():
    return json.loads((BASE / 'data' / 'npcs.json').read_text(encoding='utf-8'))


def test_residents_have_explicit_home_rooms_and_home_schedule_entries():
    npcs = _npcs()
    expected = {
        '菜贩孙婶': 'sun_aunt_yard',
        '挑水老邱': 'old_qiu_residence',
        '农家阿禾': 'farmer_ahe_yard',
        '铁匠学徒小石': 'blacksmith',
    }
    for name, home in expected.items():
        npc = npcs[name]
        assert npc['home_room'] == home
        assert any(entry.get('location') == home for entry in npc.get('daily_schedule', []))


def test_home_schedule_entries_have_valid_clock_ranges_and_rooms():
    npcs = _npcs()
    rooms = json.loads((BASE / 'data' / 'rooms.json').read_text(encoding='utf-8'))
    for name in ('菜贩孙婶', '挑水老邱', '农家阿禾', '铁匠学徒小石'):
        for entry in npcs[name].get('daily_schedule', []):
            assert 0 <= int(entry['start']) <= 23
            assert 0 <= int(entry['end']) <= 23
            assert entry.get('location') in rooms


def test_residential_scene_owner_matches_explicit_home_configuration():
    npcs = _npcs()
    rooms = json.loads((BASE / 'data' / 'rooms.json').read_text(encoding='utf-8'))
    for room_id in ('sun_aunt_yard', 'old_qiu_residence', 'farmer_ahe_yard'):
        owner = rooms[room_id]['residence']['owner']
        assert npcs[owner]['home_room'] == room_id
