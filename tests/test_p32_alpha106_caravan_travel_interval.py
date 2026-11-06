"""Alpha106: configured caravan travel intervals govern route movement."""
from economy import EconomyManager


def make_manager(interval=3, penalty=0):
    manager = EconomyManager({
        "caravans": {"行商甲": {"position": 0, "gold": 500, "inventory": {}, "capacity": 8, "visits": 0}},
        "events": {"world_crises": {"danger_zone": {"id": "road_crisis", "title": "商路动荡", "travel_penalty": penalty}}},
    })
    manager.caravan_config = {"行商甲": {
        "route": ["safe_stop", "danger_stop"], "gold": 500, "inventory": {},
        "capacity": 8, "travel_interval": interval,
    }}
    manager.resources = {}
    manager.recipes = {}
    manager.gatherers = {}
    manager.world_rooms = {"safe_stop": {"zone": "safe_zone"}, "danger_stop": {"zone": "danger_zone"}}
    return manager


def test_route_moves_only_after_configured_interval():
    manager = make_manager(interval=3)
    manager.update(1)
    assert manager.state.caravans["行商甲"]["position"] == 1  # 首次行进保持旧版语义
    manager.update(2)
    assert manager.state.caravans["行商甲"]["position"] == 1
    manager.update(1)
    assert manager.state.caravans["行商甲"]["position"] == 0
    assert manager.state.caravans["行商甲"]["visits"] == 4


def test_crisis_delays_only_due_movement_not_each_waiting_tick():
    manager = make_manager(interval=3, penalty=18)
    manager.update(1)  # 首次应移动，但受危机影响而延误
    assert manager.state.caravans["行商甲"]["position"] == 0
    assert manager.state.caravans["行商甲"]["crisis_delayed_ticks"] == 1
    manager.update(2)  # 等待期间不重复累计延误
    assert manager.state.caravans["行商甲"]["crisis_delayed_ticks"] == 1
