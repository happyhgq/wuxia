import json
import random
from pathlib import Path
from unittest.mock import patch

import engine
from player import Player
import random_npcs


def setup_module():
    random_npcs.reset_config_cache()


def _player(room='village_gate'):
    p = Player('测试侠客')
    p.location = room
    p.world_state = {'flags': {}, 'variables': {}}
    return p


def test_random_pedestrian_spawns_in_allowed_current_room_and_is_not_fixed_npc():
    p = _player('village_gate')
    config = random_npcs.get_config()
    old = config['zones']['main']['spawn_chance']
    config['zones']['main']['spawn_chance'] = 1.0
    try:
        with patch('random.random', return_value=0.0):
            names = p.get_npcs_in_room('village_gate')
        random_names = [n for n in names if random_npcs.is_random_pedestrian(p, n)]
        assert len(random_names) == 1
        assert random_names[0] not in engine.NPCS
    finally:
        config['zones']['main']['spawn_chance'] = old


def test_repeat_scene_query_does_not_recheck_before_interval():
    p = _player('village_gate')
    config = random_npcs.get_config()
    old = config['zones']['main']['spawn_chance']
    config['zones']['main']['spawn_chance'] = 1.0
    try:
        with patch('random.random', return_value=0.0):
            first = p.get_npcs_in_room('village_gate')
            second = p.get_npcs_in_room('village_gate')
        assert first == second
        assert len(random_npcs.get_room_pedestrians(p, 'village_gate')) <= 2
    finally:
        config['zones']['main']['spawn_chance'] = old


def test_scene_change_reclaims_random_pedestrians_only():
    p = _player('village_gate')
    config = random_npcs.get_config()
    old = config['zones']['main']['spawn_chance']
    config['zones']['main']['spawn_chance'] = 1.0
    try:
        with patch('random.random', return_value=0.0):
            p.get_npcs_in_room('village_gate')
        assert random_npcs.get_room_pedestrians(p, 'village_gate')
        p.location = 'guiyun_central_square'
        with patch('random.random', return_value=1.0):
            p.get_npcs_in_room(p.location)
        assert random_npcs.get_room_pedestrians(p, 'village_gate') == []
    finally:
        config['zones']['main']['spawn_chance'] = old


def test_special_sect_area_does_not_spawn():
    p = _player('shaolin_gate')
    with patch('random.random', return_value=0.0):
        p.get_npcs_in_room(p.location)
    assert random_npcs.get_room_pedestrians(p, p.location) == []


def test_random_talk_is_lightweight_and_does_not_add_npc_registry_entry():
    p = _player('village_gate')
    state = p.world_state['variables'].setdefault('random_pedestrians', {'by_room': {}, 'last_check': {}})
    state['by_room']['village_gate'] = [{'name': '测试路人甲', 'role': '行脚客', 'room': 'village_gate', 'created_clock': 0}]
    assert '测试路人甲' in random_npcs.talk_text(p, '测试路人甲')
    assert '测试路人甲' not in engine.NPCS


def test_v12_save_shape_remains_unchanged(tmp_path):
    p = _player('village_gate')
    p.world_state['variables']['random_pedestrians'] = {'by_room': {}, 'last_check': {}}
    target = tmp_path / 'save.json'
    assert p.save_to_file(str(target))
    payload = json.loads(target.read_text(encoding='utf8'))
    assert 'world_state' in payload
    assert 'random_pedestrians' in payload['world_state']['variables']
    assert 'random_pedestrians' not in payload


def test_random_pedestrians_survive_save_load_without_duplicate_generation(tmp_path):
    p = _player('village_gate')
    state = p.world_state['variables'].setdefault('random_pedestrians', {'by_room': {}, 'last_check': {}})
    state['by_room']['village_gate'] = [{'name': '存档路人甲', 'role': '当地百姓', 'room': 'village_gate', 'created_clock': 0}]
    state['last_check']['village_gate'] = 0
    target = tmp_path / 'save.json'
    assert p.save_to_file(str(target))
    loaded = Player.load_from_file(str(target))
    assert loaded is not None
    assert random_npcs.get_room_pedestrians(loaded, 'village_gate') == ['存档路人甲']
    with patch('random.random', return_value=0.0):
        names = loaded.get_npcs_in_room('village_gate')
    assert names.count('存档路人甲') == 1


def test_legacy_v12_without_random_pedestrian_field_still_loads(tmp_path):
    p = _player('village_gate')
    target = tmp_path / 'legacy.json'
    assert p.save_to_file(str(target))
    payload = json.loads(target.read_text(encoding='utf8'))
    payload['world_state']['variables'].pop('random_pedestrians', None)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
    loaded = Player.load_from_file(str(target))
    assert loaded is not None
    assert random_npcs.get_room_pedestrians(loaded, 'village_gate') == []


def test_security_level_changes_random_pedestrian_spawn_chance():
    p = _player('village_gate')
    config = random_npcs.get_config()
    profile = config['zones']['main']
    old_chance = profile['spawn_chance']
    profile['spawn_chance'] = 0.4
    try:
        p.get_region_ecology = lambda zone=None: {'security': 100}
        with patch('random.random', return_value=0.35):
            p.get_npcs_in_room('village_gate')
        assert random_npcs.get_room_pedestrians(p, 'village_gate') == []

        p.world_state['variables']['random_pedestrians'] = {'by_room': {}, 'last_check': {}}
        p.get_region_ecology = lambda zone=None: {'security': 20}
        with patch('random.random', return_value=0.35):
            p.get_npcs_in_room('village_gate')
        assert random_npcs.get_room_pedestrians(p, 'village_gate')
    finally:
        profile['spawn_chance'] = old_chance


def test_low_security_can_add_ambient_role_without_creating_fixed_npc():
    p = _player('village_gate')
    config = random_npcs.get_config()
    profile = config['zones']['main']
    old_chance = profile['spawn_chance']
    profile['spawn_chance'] = 1.0
    try:
        p.get_region_ecology = lambda zone=None: {'security': 10}
        with patch('random.random', return_value=0.0), patch('random.choice', side_effect=lambda seq: seq[0]):
            p.get_npcs_in_room('village_gate')
        rows = p.world_state['variables']['random_pedestrians']['by_room']['village_gate']
        assert rows[0]['role'] in profile['roles'] + config['security_profiles']['unsafe']['extra_roles']
        assert rows[0]['name'] not in engine.NPCS
    finally:
        profile['spawn_chance'] = old_chance


def test_region_cap_counts_previous_room_population_without_retaining_old_entities():
    p = _player('village_gate')
    config = random_npcs.get_config()
    main = config['zones']['main']
    old_scene_cap, old_region_cap, old_chance = main['scene_cap'], main['region_cap'], main['spawn_chance']
    main['scene_cap'], main['region_cap'], main['spawn_chance'] = 2, 1, 1.0
    try:
        with patch('random.random', return_value=0.0):
            p.get_npcs_in_room('village_gate')
        assert len(random_npcs.get_room_pedestrians(p, 'village_gate')) == 1
        p.location = 'village_square'
        with patch('random.random', return_value=0.0):
            p.get_npcs_in_room('village_square')
        # 旧场景实体已回收，但区域人口计数保留，因此新场景不能绕过区域上限。
        assert random_npcs.get_room_pedestrians(p, 'village_gate') == []
        assert random_npcs.get_room_pedestrians(p, 'village_square') == []
        state = p.world_state['variables']['random_pedestrians']
        assert state['region_population'].get('main') == 1
    finally:
        main['scene_cap'], main['region_cap'], main['spawn_chance'] = old_scene_cap, old_region_cap, old_chance


def test_region_population_is_released_after_time_passes():
    p = _player('village_gate')
    config = random_npcs.get_config()
    main = config['zones']['main']
    old_region_cap, old_chance = main['region_cap'], main['spawn_chance']
    main['region_cap'], main['spawn_chance'] = 1, 1.0
    try:
        state = random_npcs._state(p)
        state['region_population']['main'] = 1
        state['region_population_clock']['main'] = 0
        p.get_quest_clock = lambda: 100
        with patch('random.random', return_value=0.0):
            p.get_npcs_in_room('village_gate')
        assert random_npcs.get_room_pedestrians(p, 'village_gate')
        assert state['region_population'].get('main', 0) == 0
    finally:
        main['region_cap'], main['spawn_chance'] = old_region_cap, old_chance


def test_random_pedestrians_are_not_exposed_when_querying_non_current_room():
    p = _player('village_gate')
    state = random_npcs._state(p)
    state['by_room']['village_square'] = [{
        'name': '不应跨场景显示的路人',
        'role': '行脚客',
        'room': 'village_square',
        'created_clock': 0,
    }]

    # 固定 NPC 的查询仍正常，但临时路人只对玩家当前场景可见。
    assert '不应跨场景显示的路人' not in p.get_npcs_in_room('village_square')
    assert random_npcs.get_room_pedestrians(p, 'village_square') == ['不应跨场景显示的路人']
