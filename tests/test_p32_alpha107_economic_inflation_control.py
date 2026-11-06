"""Alpha107：起始资金只初始化一次，商队运营费用是明确的货币回收口。"""
from economy import EconomyManager, TradeService
from types import SimpleNamespace


def test_counterparty_starting_wallet_is_seeded_only_once():
    player = SimpleNamespace(
        gold=100,
        inventory=["草药"],
        economy_state={"npc_gold": {}, "npc_inventory": {}, "events": {}},
    )
    ok, _ = TradeService.sell(player, "草药", 1, 8, "临时商贩")
    assert ok
    assert player.economy_state["npc_gold"]["临时商贩"] == 992
    # 钱包后来被花空/缺失，不得再次发放同一笔起始资金。
    del player.economy_state["npc_gold"]["临时商贩"]
    player.inventory.append("草药")
    ok, _ = TradeService.sell(player, "草药", 1, 8, "临时商贩")
    assert not ok
    assert player.economy_state["npc_gold"]["临时商贩"] == 0
    assert player.gold == 108
    assert player.inventory == ["草药"]


def test_wallet_bootstrap_is_one_time_and_never_refills_spent_money():
    manager = EconomyManager()
    manager.update(1)
    assert manager.state.events["economy_money_ledger"]["initial_wallets_seeded"] is True

    # 模拟所有经济主体把手头银两花完；后续 Tick 不得再因钱包缺失/默认值而恢复本金。
    for npc_id in list(manager.state.npc_gold):
        manager.state.npc_gold[npc_id] = 0
    for caravan in manager.state.caravans.values():
        if isinstance(caravan, dict):
            caravan["gold"] = 0
    manager.state.town_gold = 0
    manager.update(120)

    assert all(int(value) == 0 for value in manager.state.npc_gold.values())
    assert all(int(row.get("gold", 0)) == 0 for row in manager.state.caravans.values() if isinstance(row, dict))
    assert manager.state.town_gold == 0


def test_caravan_stop_upkeep_is_recorded_as_money_sink():
    manager = EconomyManager()
    manager.update(1)
    ledger = manager.state.events.get("economy_money_ledger", {})
    assert int(ledger.get("destroyed_caravan_upkeep", 0)) > 0
    costs = [int(row.get("operating_cost_per_stop", 0)) for row in manager.caravan_config.values()]
    assert sorted(costs) == [2, 4, 7]
    activities = manager.recent_world_activity(100)
    assert any(row.get("action") == "支付行商开销" for row in activities)
