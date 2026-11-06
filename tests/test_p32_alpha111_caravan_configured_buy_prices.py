"""Alpha111：商队配置中的收购价必须真正参与 NPC 采购。"""
from economy import EconomyManager


def test_caravan_uses_configured_price_when_buying_from_gatherer():
    manager = EconomyManager({
        "tick": 0,
        "caravans": {"行商": {"position": 1, "gold": 100, "inventory": {}, "capacity": 8, "visits": 0}},
        "npc_inventory": {"采药人": {"草药": 4}},
        "npc_gold": {"采药人": 0},
        "market": {"草药": {"supply": 20, "traded": 0, "last_price": 5}},
    })
    manager.caravan_config = {
        "行商": {
            "route": ["采集点", "别处"], "gold": 100, "inventory": {}, "capacity": 8,
            "buy_prices": {"草药": 9}, "travel_interval": 1,
        }
    }
    manager.resources = {}
    manager.recipes = {}
    manager.gatherers = {"采药人": {"room_id": "采集点", "item": "草药", "capacity": 10}}
    manager.world_rooms = {"采集点": {"zone": "forest"}, "别处": {"zone": "town"}}

    manager.update(1)

    caravan = manager.state.caravans["行商"]
    assert caravan["inventory"]["草药"] == 4
    assert caravan["gold"] == 64
    assert manager.state.npc_inventory["采药人"]["草药"] == 0
    assert manager.state.npc_gold["采药人"] == 36
    assert manager.state.market["草药"]["last_price"] == 9
    assert manager.state.regional_market["forest"]["草药"]["last_price"] == 9


def test_caravan_buy_price_overrides_recipe_trade_price_for_finished_goods():
    manager = EconomyManager({
        "tick": 0,
        "caravans": {"行商": {"position": 1, "gold": 100, "inventory": {}, "capacity": 8, "visits": 0}},
        "npc_inventory": {"木匠": {"木剑": 2}},
        "npc_gold": {"木匠": 0},
        "market": {"木剑": {"supply": 20, "traded": 0, "last_price": 12}},
    })
    manager.caravan_config = {
        "行商": {
            "route": ["作坊", "别处"], "gold": 100, "inventory": {}, "capacity": 8,
            "buy_prices": {"木剑": 17}, "travel_interval": 1,
        }
    }
    manager.resources = {}
    manager.gatherers = {}
    manager.recipes = {
        "木匠": {
            "room_id": "作坊", "inputs": {"木材": 1}, "outputs": {"木剑": 1},
            "output_capacity": {"木剑": 8}, "trade_prices": {"木剑": 12}, "interval": 99,
        }
    }
    manager.world_rooms = {"作坊": {"zone": "town"}, "别处": {"zone": "forest"}}

    manager.update(1)

    caravan = manager.state.caravans["行商"]
    assert caravan["inventory"]["木剑"] == 2
    assert caravan["gold"] == 66
    assert manager.state.npc_inventory["木匠"]["木剑"] == 0
    assert manager.state.npc_gold["木匠"] == 34
    assert manager.state.market["木剑"]["last_price"] == 17
    assert manager.state.regional_market["town"]["木剑"]["last_price"] == 17
