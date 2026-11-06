"""Alpha208：地图跨区域出口与区域标题必须使用中文显示名。"""
import re

import engine
from ui_output import _ANSI_RE


def test_every_room_zone_has_a_player_facing_chinese_name():
    zones = {room.get("zone", "main") for room in engine.ROOMS.values()}
    assert zones <= set(engine.MapEngine.ZONE_NAMES)
    for zone in zones:
        assert engine.MapEngine.ZONE_NAMES[zone]
        assert not re.fullmatch(r"[a-z0-9_]+", engine.MapEngine.ZONE_NAMES[zone])


def test_cross_zone_exits_do_not_expose_internal_zone_ids():
    checked = 0
    for room_key, room in engine.ROOMS.items():
        zone = room.get("zone", "main")
        for direction, target in (room.get("exits", {}) or {}).items():
            target_room = engine.ROOMS.get(target, {})
            target_zone = target_room.get("zone", "main")
            if target_zone == zone:
                continue
            checked += 1
            rendered = _ANSI_RE.sub("", engine.MAP_ENGINE.render(room_key))
            if direction in ("上", "下"):
                # 上下楼是同一建筑内的楼层切换，地图直接显示“下 -> 一楼大堂”，
                # 不再附加“(进入主世界)”这类跨区域提示。
                assert "inn_upper" not in rendered
                continue
            assert f"(进入{engine.MapEngine.ZONE_NAMES[target_zone]})" in rendered
            assert f"(进入{target_zone})" not in rendered
    assert checked > 0


def test_all_same_zone_exit_coordinates_match_their_direction():
    vectors = engine.MapEngine.DIR_VECTORS
    checked = 0
    for room_key, room in engine.ROOMS.items():
        # 内室不参与地图布局，也没有坐标；自定义方向（内/外/后/前）不按坐标位移。
        if room.get("map_hidden"):
            continue
        for direction, target in (room.get("exits", {}) or {}).items():
            if target not in engine.ROOMS or direction not in vectors:
                continue
            if engine.ROOMS[target].get("map_hidden"):
                continue
            if room.get("zone", "main") != engine.ROOMS[target].get("zone", "main"):
                continue
            x, y = engine.MAP_ENGINE.room_coords[room_key]
            tx, ty = engine.MAP_ENGINE.room_coords[target]
            assert (tx - x, ty - y) == vectors[direction], (room_key, direction, target, (tx - x, ty - y))
            checked += 1
    assert checked > 0
