"""Alpha307 工作副本：资源补给、商旅库存与价格和世界事件/区域状态的联动复核。"""
from types import SimpleNamespace

import actions
from economy import EconomyManager, TradeService


def quote_player(state, location="village_square"):
    return SimpleNamespace(economy_state=state, location=location)


def schedule_manager(commerce=70, penalty=0):
    manager = EconomyManager({
        "tick": 0,
        "events": {
            "caravan_global_schedule": {"next_tick": 1, "arrivals": 0},
            "region_ecology": {
                "main": {"security": 70, "commerce": commerce, "travel": 70},
                "guiyun_city": {"security": 70, "commerce": commerce, "travel": 70},
            },
            "world_crises": {
                zone: {"id": "road_crisis", "title": "商路动荡", "travel_penalty": penalty}
                for zone in ("main", "guiyun_city")
            } if penalty else {},
        },
    })
    manager.caravan_config = {"测试行商": {
        "tier": "small",
        "route": ["village_square", "guiyun_central_square"],
        "appearances": [
            {"room": "village_square", "interval": 30, "offset": 1},
            {"room": "guiyun_central_square", "interval": 30, "offset": 1},
        ],
        "stay_ticks": [3, 5],
        "arrival_interval": [30, 30],
        "weight": 1,
        "gold": 500,
        "inventory": {},
        "capacity": 8,
    }}
    manager.resources = {}
    manager.recipes = {}
    manager.gatherers = {}
    manager.world_rooms = {
        "village_square": {"zone": "main"},
        "guiyun_central_square": {"zone": "guiyun_city"},
    }
    return manager


def test_global_market_event_changes_live_quotes_and_expires():
    manager = EconomyManager({"tick": 29})
    manager.caravan_config = {}
    manager.resources = {}
    manager.recipes = {}
    manager.gatherers = {}
    manager.update(1)
    state = manager.export_state()
    assert state["events"]["market_event_rate"] == 1.15

    player = quote_player(state)
    # 店铺展示价与实际成交共用同一行情倍率。
    assert actions._market_quote(player, "木材", 100, "buy") == 115
    assert TradeService.market_price(player, "木材", 100, "buy", 1.0, 1.15) == 115

    manager.update(10)  # 事件在 tick 40 到期，报价回落到常态。
    assert manager.state.events["market_event_rate"] == 1.0
    expired = quote_player(manager.export_state())
    assert actions._market_quote(expired, "木材", 100, "buy") == 100


def test_regional_market_event_only_changes_its_own_zone():
    manager = EconomyManager({"tick": 44})
    manager.caravan_config = {}
    manager.resources = {}
    manager.recipes = {}
    manager.gatherers = {}
    manager.update(1)
    state = manager.export_state()
    assert state["events"]["regional_market_events"]["mistwood"]["rate"] == 1.18

    forest = quote_player(state, "mistwood_trail")
    village = quote_player(state, "village_square")
    assert TradeService.market_price(forest, "木材", 100, "buy") == 118
    assert TradeService.market_price(village, "木材", 100, "buy") == 100


def test_low_commerce_and_crisis_stretch_the_next_public_caravan_gap():
    normal = schedule_manager(commerce=70, penalty=0)
    low_commerce = schedule_manager(commerce=10, penalty=0)
    crisis = schedule_manager(commerce=70, penalty=80)
    for manager in (normal, low_commerce, crisis):
        manager.update(1)
        schedule = manager.state.events["caravan_global_schedule"]
        # 基础间隔 30；低商路延迟 3 Tick，严重危机同样延迟 3 Tick。
        assert schedule["arrivals"] == 1
        active = [row for row in manager.state.events["active_caravans"].values()
                  if isinstance(row, dict) and row.get("room") in ("village_square", "guiyun_central_square")]
        assert len(active) == 1
    assert normal.state.events["caravan_global_schedule"]["next_tick"] == 31
    assert low_commerce.state.events["caravan_global_schedule"]["next_tick"] == 34
    assert crisis.state.events["caravan_global_schedule"]["next_tick"] == 34


def test_caravan_stock_comes_from_real_resource_node_and_respects_capacity():
    manager = EconomyManager({"caravans": {}})
    manager.caravan_config = {"取材行商": {
        "route": ["start", "wood_stop"],
        "gold": 500,
        "inventory": {},
        "capacity": 8,
        "travel_interval": 1,
    }}
    manager.resources = {"wood_stop": {"item": "木材", "capacity": 10}}
    manager.recipes = {}
    manager.gatherers = {}
    manager.world_rooms = {"start": {"zone": "main"}, "wood_stop": {"zone": "mistwood"}}
    manager.update(1)

    assert manager.state.resources["wood_stop"]["remaining"] == 8
    inventory = manager.state.caravans["取材行商"]["inventory"]
    assert inventory.get("木材") == 2
    assert sum(max(0, int(amount)) for amount in inventory.values()) <= 8


def test_player_and_npc_share_finite_resource_node_with_capped_regen():
    manager = EconomyManager({})
    manager.caravan_config = {}
    ok, result = manager.chop("mistwood_trail", 3)
    assert ok is True
    assert result == ("木材", 3)
    row = manager.state.resources["mistwood_trail"]
    assert row["remaining"] == 27

    manager.update(4)
    row = manager.state.resources["mistwood_trail"]
    woodcutter = manager.state.npc_inventory["樵夫老周"]["木材"]
    assert row["remaining"] == 25
    assert woodcutter == 2
    # 玩家与 NPC 的产出都来自同一处 30 份储量。
    assert row["remaining"] + woodcutter + 3 == 30

    manager.update(2)  # tick 6 触发一次 +4 恢复，且不超过上限。
    assert manager.state.resources["mistwood_trail"]["remaining"] == 29
    assert manager.state.resources["mistwood_trail"]["remaining"] <= 30

    manager.state.resources["mistwood_trail"]["remaining"] = 0
    assert manager.chop("mistwood_trail", 1) == (False, "这处资源暂时耗尽了，请过些时日再来。")
