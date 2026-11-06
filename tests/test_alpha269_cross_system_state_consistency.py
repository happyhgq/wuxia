"""Alpha269：世界时钟、商旅、区域生态与经济库存的跨系统状态一致性审计。"""
import random

from player import Player
from economy import EconomyManager


def test_long_cycle_world_and_economy_clocks_and_caravan_state_stay_consistent():
    player = Player("跨系统审计侠客", "散人")
    random.seed(2692026)
    player.tick_quest_clock(360)

    economy = player.economy_state
    assert player.get_quest_clock() == economy.get("tick") == 360

    manager = EconomyManager(economy)
    configured = manager.caravan_config
    caravans = economy.get("caravans", {})
    assert set(configured).issubset(caravans)
    for caravan_id, cfg in configured.items():
        state = caravans[caravan_id]
        route = cfg.get("route", [])
        assert route
        assert 0 <= int(state.get("position", -1)) < len(route)
        capacity = int(state.get("capacity", 0))
        inventory = state.get("inventory", {})
        assert isinstance(inventory, dict)
        assert all(int(amount) >= 0 for amount in inventory.values())
        assert sum(int(amount) for amount in inventory.values()) <= capacity
        assert 0 <= int(state.get("gold", -1)) <= 2_000_000_000

    events = economy.get("events", {})
    active = events.get("active_caravans", {})
    valid_active = []
    for key, row in active.items():
        assert isinstance(row, dict)
        assert row.get("name") in configured
        assert row.get("room") in ("village_square", "guiyun_central_square")
        assert int(row.get("until_tick", -1)) > economy["tick"]
        valid_active.append((key, row))
    # 公开商队采用全局错峰调度，同一时刻不得在两个广场同时出现。
    assert len(valid_active) <= 1

    ecology = events.get("region_ecology", {})
    for zone, row in ecology.items():
        assert isinstance(row, dict)
        for field in ("security", "commerce", "travel"):
            assert 0 <= int(row.get(field, -1)) <= 100, (zone, field, row)

    for npc_id, stock in economy.get("npc_inventory", {}).items():
        assert isinstance(stock, dict)
        assert all(0 <= int(amount) <= 9999 for amount in stock.values()), npc_id


def test_economy_update_prunes_expired_caravan_presence_and_preserves_inventory_invariants():
    manager = EconomyManager({
        "tick": 10,
        "events": {"active_caravans": {
            "过期商队:village_square": {"name": "村镇行商", "room": "village_square", "until_tick": 10},
            "有效商队:guiyun_central_square": {"name": "南路商队", "room": "guiyun_central_square", "until_tick": 15},
        }},
        "caravans": {
            "村镇行商": {"position": 0, "gold": 100, "capacity": 8, "inventory": {"草药": 3}},
            "南路商队": {"position": 0, "gold": 200, "capacity": 8, "inventory": {"铁矿石": 2}},
        },
    })
    manager.update(1)
    active = manager.state.events["active_caravans"]
    assert "过期商队:village_square" not in active
    assert active["有效商队:guiyun_central_square"]["until_tick"] > manager.state.tick
    # 同一 Tick 允许商队按路线执行真实采购/销售；无论库存变化，货舱约束必须保持。
    for caravan in manager.state.caravans.values():
        stock = caravan.get("inventory", {})
        assert all(int(amount) >= 0 for amount in stock.values())
        assert sum(int(amount) for amount in stock.values()) <= int(caravan.get("capacity", 0))
