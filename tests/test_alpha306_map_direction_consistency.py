"""Alpha306：场景相邻关系与方向文案一致性回归。

守卫播报“往北边（青石长街）去了”时，地名不再与方向矛盾：
这里的“长街”只是街名，不再带“南”字；青石村南北街巷的坐标与出口方向一致。
"""

import engine

_DIR_VECTORS = {"北": (0, 1), "南": (0, -1), "东": (1, 0), "西": (-1, 0)}
_OPPOSITE = {"北": "南", "南": "北", "东": "西", "西": "东"}

# 有意保留的单向/弯折连接；键为 (起点, 方向, 终点)。
_ASYMMETRIC_EXITS = {
    ("bandit_back_mountain", "东", "wild_fields"): "黑风后山越界通往村后荒野的单向山道",
    ("northfront_gate", "南", "guiyun_south_gate"): "北境镇门到归云城南门为道路弯折，回程走东",
    ("guiyun_south_gate", "东", "northfront_gate"): "同一处弯折的另一半",
    ("sunken_cache", "西", "sunken_channel"): "沉河暗库为单向潜入点",
    ("sunken_weir", "西", "sunken_cache"): "沉河堰口经隐蔽水道返回暗库，来路为隐蔽出口",
}


def _rooms():
    return engine.ROOMS


def test_every_cardinal_exit_matches_coordinate_step():
    mismatch = []
    for room_id, room in _rooms().items():
        coord = room.get("coord")
        for direction, target_id in (room.get("exits") or {}).items():
            if direction not in _DIR_VECTORS:
                continue
            target = _rooms().get(target_id)
            if not target:
                mismatch.append((room_id, direction, target_id, "目标场景不存在"))
                continue
            target_coord = target.get("coord")
            if not coord or not target_coord or target.get("zone") != room.get("zone"):
                continue
            delta = (target_coord[0] - coord[0], target_coord[1] - coord[1])
            if delta != _DIR_VECTORS[direction]:
                mismatch.append((room_id, direction, target_id, delta))
    assert mismatch == [], f"出口方向与坐标不一致：{mismatch}"


def test_every_cardinal_exit_has_reverse_exit():
    missing = []
    for room_id, room in _rooms().items():
        for direction, target_id in (room.get("exits") or {}).items():
            if direction not in _DIR_VECTORS:
                continue
            key = (room_id, direction, target_id)
            if key in _ASYMMETRIC_EXITS:
                continue
            target = _rooms().get(target_id) or {}
            back = (target.get("exits") or {}).get(_OPPOSITE[direction])
            if back != room_id:
                missing.append((room_id, direction, target_id, back))
    assert missing == [], f"缺少对向出口：{missing}"


def test_village_streets_do_not_contradict_compass():
    rooms = _rooms()
    gate = rooms["village_gate"]
    assert gate["exits"]["北"] == "village_south_street"
    # 村口向北依次是长街、广场、后街，坐标逐级北移。
    chain = ["village_gate", "village_south_street", "village_square", "village_north_street"]
    assert [rooms[room_id]["coord"][1] for room_id in chain] == [1, 2, 3, 4]
    assert rooms["village_south_street"]["name"] == "青石长街"
    assert rooms["village_north_street"]["name"] == "青石后街"
    for room_id in ("village_gate", "village_south_street", "village_square",
                    "village_north_street", "inn", "residents_lane"):
        text = rooms[room_id].get("name", "") + rooms[room_id].get("desc", "")
        assert "村南大街" not in text and "村北街" not in text


def test_npc_dialogue_uses_renamed_streets():
    text = str(engine.NPCS)
    assert "村南大街" not in text and "村北街" not in text
