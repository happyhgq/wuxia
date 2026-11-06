import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_gatherable_rooms_have_independent_resource_nodes():
    rooms = load_json(ROOT / "data" / "rooms.json")
    resources = load_json(ROOT / "data" / "economy" / "resources.json")
    gather_rooms = []
    for room_id, room in rooms.items():
        forage = room.get("forage", {})
        if not isinstance(forage, dict):
            continue
        for item in forage:
            cfg = resources.get(room_id)
            assert isinstance(cfg, dict), f"{room_id} has forage {item} but no resource node"
            assert cfg.get("action") == "gather", f"{room_id} is not configured as a gathering node"
            assert cfg.get("item") == item, f"{room_id} forage item does not match resource node"
            assert int(cfg.get("capacity", 0)) > 0
            assert int(cfg.get("regen_interval", 0)) > 0
            assert int(cfg.get("regen_amount", 0)) > 0
            gather_rooms.append(room_id)
    assert len(gather_rooms) >= 8
    assert len(gather_rooms) == len(set(gather_rooms))


def test_neighboring_herb_locations_are_connected_and_have_separate_capacity():
    rooms = load_json(ROOT / "data" / "rooms.json")
    resources = load_json(ROOT / "data" / "economy" / "resources.json")
    # 村后荒野可沿出口前往官道或雾隐林道；采药溪谷可前往药香浅滩。
    assert rooms["wild_fields"]["exits"]["北"] == "mistwood_trail"
    assert rooms["mistwood_trail"]["exits"]["北"] == "mistwood_stream"
    assert rooms["mistwood_stream"]["exits"]["西"] == "herb_springbank"
    ids = ("wild_fields", "mistwood_stream", "herb_springbank", "rocky_herb_slope")
    capacities = [int(resources[room_id]["capacity"]) for room_id in ids]
    assert len(set(ids)) == len(ids)
    assert all(capacity > 0 for capacity in capacities)
    assert resources["wild_fields"]["item"] == resources["mistwood_stream"]["item"] == "草药"
    assert resources["herb_springbank"]["item"] == resources["rocky_herb_slope"]["item"] == "草药"


def test_resource_recovery_settings_allow_a_gathering_route():
    resources = load_json(ROOT / "data" / "economy" / "resources.json")
    for room_id in ("wild_fields", "official_road", "mistwood_stream", "herb_springbank", "rocky_herb_slope"):
        cfg = resources[room_id]
        assert int(cfg["regen_interval"]) <= 6
        assert int(cfg["regen_amount"]) >= 2
        assert int(cfg["capacity"]) >= 8
