"""Alpha147：偏远门派区域、身份门禁与已探索道路快速旅行。"""
import contextlib
import io

import engine
from player import Player
from travel_system import available_destinations, handle_travel, room_access_denial


def test_new_huashan_region_connects_to_existing_world_and_has_return_route():
    rooms = engine.ROOMS
    assert rooms['old_woodlot']['exits']['东'] == 'pine_ridge_foot'
    assert rooms['pine_ridge_foot']['exits']['西'] == 'old_woodlot'
    assert rooms['cloud_stack_road']['exits']['东'] == 'huashan_approach'
    assert rooms['huashan_approach']['exits']['西'] == 'cloud_stack_road'
    assert rooms['huashan_approach']['zone'] == 'huashan_mountain'
    assert rooms['huashan_gate']['exits']['南'] == 'huashan_guest_path'


def test_visitors_can_reach_gate_and_guest_hall_but_not_inner_practice_area():
    player = Player('访客测试', '散人')
    assert room_access_denial(player, engine.ROOMS['huashan_gate']) == ''
    assert room_access_denial(player, engine.ROOMS['huashan_guest_hall']) == ''
    assert engine.ROOMS['huashan_gate']['exits']['西'] == 'huashan_guest_hall'
    assert '华山' in room_access_denial(player, engine.ROOMS['huashan_front_court'])
    assert '演武场' in room_access_denial(player, engine.ROOMS['huashan_training_ground'])
    player.level = max(player.level, 3)
    player.join_sect('华山')
    assert room_access_denial(player, engine.ROOMS['huashan_front_court']) == ''
    assert room_access_denial(player, engine.ROOMS['huashan_training_ground']) == ''


def test_fast_travel_requires_a_fully_visited_route():
    player = Player('路线测试', '散人')
    player.location = 'village_gate'
    # Merely knowing the town gate must not unlock a remote location.
    options, _ = available_destinations(player)
    assert all(dest != 'huashan_gate' for dest, _, _ in options)
    path = ['village_gate', 'official_road', 'official_road_east_1', 'official_road_east_2',
            'guiyun_south_gate', 'official_road_east_2', 'official_road_east_1', 'official_road',
            'wild_fields', 'old_woodlot', 'pine_ridge_foot', 'stone_creek_bridge', 'cloud_stack_road',
            'huashan_approach', 'huashan_guest_path', 'huashan_gate']
    for rid in set(path):
        player.mark_visited(rid)
    options, error = available_destinations(player)
    assert not error
    assert any(dest == 'huashan_gate' for dest, _, _ in options)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert handle_travel(player, ['华山山门']) is True
    assert player.location == 'huashan_gate'
    assert '华山山门' in output.getvalue()


def test_fast_travel_does_not_bypass_unvisited_or_restricted_rooms():
    player = Player('门禁路线测试', '散人')
    player.location = 'village_gate'
    for rid in ('village_gate', 'official_road', 'official_road_east_1', 'official_road_east_2',
                'guiyun_south_gate', 'wild_fields', 'old_woodlot', 'pine_ridge_foot',
                'cloud_stack_road', 'huashan_approach', 'huashan_guest_path', 'huashan_gate'):
        player.mark_visited(rid)
    # Inner rooms are not hubs, and a route cannot skip the unvisited stone bridge.
    options, _ = available_destinations(player)
    assert all(dest != 'huashan_front_court' for dest, _, _ in options)
    assert all(dest != 'huashan_gate' for dest, _, _ in options)  # the old-town start route has not been fully traversed
