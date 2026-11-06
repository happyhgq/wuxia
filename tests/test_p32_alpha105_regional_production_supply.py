"""Alpha105: NPC production changes supply in the region where production occurs."""
from economy import EconomyManager


def make_manager():
    state = {
        "tick": 0,
        "npc_inventory": {"铁匠": {"铁矿石": 2, "铁剑": 0}},
        "npc_gold": {"铁匠": 100},
        "market": {
            "铁矿石": {"supply": 20, "traded": 0, "last_price": 5},
            "铁剑": {"supply": 20, "traded": 0, "last_price": 30},
        },
        "regional_market": {
            "city": {
                "铁矿石": {"supply": 20, "traded": 7, "last_price": 5},
                "铁剑": {"supply": 20, "traded": 3, "last_price": 30},
            },
            "forest": {"铁矿石": {"supply": 40, "traded": 0, "last_price": 5}},
        },
    }
    manager = EconomyManager(state)
    manager.resources = {}
    manager.gatherers = {}
    manager.caravan_config = {}
    manager.recipes = {"铁匠": {"room_id": "forge_room", "interval": 1,
                                "inputs": {"铁矿石": 2}, "outputs": {"铁剑": 1},
                                "output_capacity": {"铁剑": 10}}}
    manager.world_rooms = {"forge_room": {"zone": "city"}}
    return manager


def test_npc_production_adjusts_local_supply_without_faking_trade_volume():
    manager = make_manager()
    manager.update(1)
    city = manager.state.regional_market["city"]
    forest = manager.state.regional_market["forest"]
    assert city["铁矿石"]["supply"] == 18
    assert city["铁剑"]["supply"] == 21
    assert city["铁矿石"]["traded"] == 7
    assert city["铁剑"]["traded"] == 3
    assert forest["铁矿石"]["supply"] == 40


def test_regional_supply_is_bounded_when_old_save_has_extreme_values():
    manager = make_manager()
    manager.state.regional_market["city"]["铁剑"]["supply"] = 9999
    manager.update(1)
    assert manager.state.regional_market["city"]["铁剑"]["supply"] == 9999
