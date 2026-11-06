"""Alpha106: real configuration long-cycle checks for economy and caravan flow."""
from economy import EconomyManager


def test_real_economy_survives_long_cycle_with_bounded_stock_and_one_public_caravan():
    manager = EconomyManager({
        "town_gold": 50000,
        "npc_gold": {
            "铁匠": 1200, "百炼铁铺铁匠": 1200,
            "采药人阿芷": 500, "守祠残僧": 500,
        },
        "npc_inventory": {
            "铁匠": {"铁矿石": 12, "铁剑": 0},
            "百炼铁铺铁匠": {"铁矿石": 12, "铁剑": 0},
            "采药人阿芷": {"草药": 0},
            "守祠残僧": {"雾露草": 0},
        },
    })
    manager.update(1500)
    state = manager.state

    assert state.tick == 1500
    assert len(state.events.get("world_activity", [])) <= 100
    assert len(state.events.get("pending_world_announcements", [])) <= 100
    assert state.town_gold >= 0

    # NPC 原料、成品和商队货物不得出现负数或突破既定容量。
    for stock in state.npc_inventory.values():
        assert isinstance(stock, dict)
        for amount in stock.values():
            assert 0 <= int(amount) <= 9999
    for caravan_id, caravan in state.caravans.items():
        assert caravan["gold"] >= 0, caravan_id
        cargo = caravan.get("inventory", {})
        assert all(0 <= int(amount) <= 9999 for amount in cargo.values()), caravan_id
        assert sum(int(amount) for amount in cargo.values()) <= int(caravan.get("capacity", 0)), caravan_id

    # 全局及分区行情数值始终处于可计算范围，避免长周期把价格输入推成异常值。
    for row in state.market.values():
        assert 0 <= int(row.get("supply", 20)) <= 9999
        assert 0 <= int(row.get("traded", 0)) <= 2_000_000_000
    for regional_rows in state.regional_market.values():
        for row in regional_rows.values():
            assert 0 <= int(row.get("supply", 20)) <= 9999
            assert 0 <= int(row.get("traded", 0)) <= 2_000_000_000

    # 两个公开广场不应同时出现两支尚未离场的商队。
    active = state.events.get("active_caravans", {})
    active_public = [row for row in active.values()
                     if isinstance(row, dict)
                     and row.get("room") in ("village_square", "guiyun_central_square")
                     and int(row.get("until_tick", -1)) > state.tick]
    assert len(active_public) <= 1
    schedule = state.events.get("caravan_global_schedule", {})
    assert int(schedule.get("arrivals", 0)) >= 5
    assert int(schedule.get("next_tick", -1)) > state.tick
