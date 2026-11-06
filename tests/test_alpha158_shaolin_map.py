import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_shaolin_map_is_connected_to_existing_world():
    rooms = read_data("rooms.json")
    assert rooms["official_road_east_1"]["exits"]["北"] == "songshan_foothill"
    assert rooms["songshan_foothill"]["exits"]["南"] == "official_road_east_1"
    for room_id in (
        "songshan_foothill", "songshan_pine_path", "songshan_stone_steps",
        "shaolin_gate", "shaolin_guest_hall", "shaolin_front_court",
        "shaolin_training_ground", "shaolin_dharma_hall",
        "shaolin_abbot_corridor", "shaolin_scripture_court",
        "shaolin_monk_quarters",
    ):
        assert room_id in rooms
        assert rooms[room_id]["zone"] == "shaolin_mountain"
        for direction, target in rooms[room_id]["exits"].items():
            assert target in rooms, (room_id, direction, target)


def test_shaolin_internal_areas_have_consistent_rank_gates():
    rooms = read_data("rooms.json")
    assert rooms["shaolin_front_court"]["access"]["sect"] == "少林"
    assert rooms["shaolin_training_ground"]["access"]["sect"] == "少林"
    # 受戒仪礼在讲经堂办理，低阶弟子必须能进入；更深的清修区域仍保留身份门槛。
    assert rooms["shaolin_dharma_hall"]["access"]["min_rank_index"] == 0
    assert rooms["shaolin_abbot_corridor"]["access"]["min_rank_index"] == 3
    assert rooms["shaolin_scripture_court"]["access"]["min_rank_index"] == 3


def test_shaolin_npcs_and_trial_quest_are_connected_to_map():
    rooms = read_data("rooms.json")
    npcs = read_data("npcs.json")
    quests = read_data("quests.json")
    assert "少林接引僧" in rooms["shaolin_guest_hall"]["npcs"]
    assert "少林传功师父" in rooms["shaolin_training_ground"]["npcs"]
    assert "少林传功师兄" in rooms["shaolin_training_ground"]["npcs"]
    assert "少林历练·黑风除恶" in npcs["少林传功师兄"]["quests"]
    assert quests["少林历练·黑风除恶"]["requires"]["sect"] == "少林"
