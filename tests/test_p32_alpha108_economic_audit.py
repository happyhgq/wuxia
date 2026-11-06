"""Alpha108：为资金与实物库存建立可复核的经济审计快照。"""
from economy import EconomyManager


def test_audit_snapshot_counts_real_wallets_and_items_not_market_supply():
    manager = EconomyManager({
        "town_gold": 120,
        "npc_gold": {"药商": 30, "铁匠": 50},
        "npc_inventory": {"药商": {"草药": 3}, "铁匠": {"铁剑": 2}},
        "caravans": {"南来商队": {"gold": 20, "inventory": {"草药": 4}, "capacity": 8}},
        "market": {"草药": {"supply": 900, "traded": 10000, "last_price": 8}},
    })
    snapshot = manager.economic_audit_snapshot()
    assert snapshot["tracked_gold"] == 220
    assert snapshot["npc_gold"] == 80
    assert snapshot["caravan_gold"] == 20
    assert snapshot["town_gold"] == 120
    assert snapshot["tracked_item_units"] == 9
    assert snapshot["item_totals"] == {"草药": 7, "铁剑": 2}
    # 行情供给和累计成交是价格指标，不得混入真实库存总量。
    assert snapshot["tracked_item_units"] != 900 + 10000


def test_long_cycle_audit_keeps_wallets_and_real_inventory_within_bounds():
    manager = EconomyManager()
    manager.update(2000)
    snapshot = manager.economic_audit_snapshot()
    assert snapshot["tick"] == 2000
    assert snapshot["tracked_gold"] == (
        snapshot["npc_gold"] + snapshot["caravan_gold"] + snapshot["town_gold"]
    )
    assert snapshot["tracked_item_units"] == (
        snapshot["npc_item_units"] + snapshot["caravan_item_units"]
    )
    assert snapshot["tracked_gold"] >= 0
    assert snapshot["tracked_item_units"] >= 0
    assert all(0 <= amount <= 9999 for amount in snapshot["item_totals"].values())
    assert snapshot["destroyed_caravan_upkeep"] >= 0
    assert snapshot["seeded_npc_gold"] >= 0
    assert snapshot["seeded_caravan_gold"] >= 0
