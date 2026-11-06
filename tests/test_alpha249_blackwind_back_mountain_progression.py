"""Alpha249：黑风后山危险度、敌人配置与装备掉落衔接。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    return json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))


def test_back_mountain_is_a_real_midgame_blackwind_route():
    rooms = load('rooms.json')
    enemies = load('enemies.json')
    room = rooms['bandit_back_mountain']
    assert room['recommended_level'] >= 7
    assert room['area_level'] >= 7
    assert room['danger'] == 'dangerous'
    assert {'黑风寨巡哨', '黑风刀手', '黑风寨精锐'} <= set(room['enemies'])
    assert room['exits']['西'] == 'mistwood_ridge_path'
    assert room['exits']['南'] == 'bandit_camp'
    assert room['exits']['东'] == 'wild_fields'
    assert room['exits']['北'] == 'sunken_stairs'
    assert all(name in enemies for name in room['enemies'])
    assert min(enemies[name]['level'] for name in room['enemies']) >= 5
    assert max(enemies[name]['level'] for name in room['enemies']) >= 8


def test_back_mountain_equipment_drops_are_low_chance_and_use_worn_gear():
    enemies = load('enemies.json')
    items = load('items.json')
    for name in ('黑风寨巡哨', '黑风刀手', '黑风寨精锐'):
        enemy = enemies[name]
        assert 0 < enemy['equipment_drop_chance'] <= 0.10
        for slot in ('weapon', 'armor'):
            worn = enemy.get('equipment', {}).get(slot)
            assert worn in items
            assert items[worn]['type'] in ('weapon', 'armor')
        # 武学秘籍仍使用独立极低概率，不把普通装备掉落与秘籍混在一起。
        manual = enemy.get('manual_drop')
        if manual:
            assert 0 < manual['chance'] <= 0.01
