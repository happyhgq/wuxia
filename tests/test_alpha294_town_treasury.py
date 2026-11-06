"""Alpha294：城镇资金池通过商税闭环，避免商队售货后无限枯竭。"""
from economy import EconomyManager


def _tracked(manager):
    return (manager.state.town_gold
            + sum(manager.state.npc_gold.values())
            + sum(row.get("gold", 0) for row in manager.state.caravans.values()
                  if isinstance(row, dict)))


def test_town_tax_moves_existing_money_without_creating_any():
    manager = EconomyManager({
        "town_gold": 1000,
        "npc_gold": {"商户": 1100},
        "caravans": {"商队": {"gold": 1800, "inventory": {}, "capacity": 8}},
    })
    manager.state.tick = 10
    before = _tracked(manager)

    collected = manager._collect_town_tax()

    assert collected > 0
    assert _tracked(manager) == before
    assert manager.state.town_gold == 1000 + collected
    assert manager.state.npc_gold["商户"] >= manager.TOWN_TAX_RESERVE
    assert manager.state.caravans["商队"]["gold"] >= manager.CARAVAN_TAX_RESERVE
    ledger = manager.state.events["economy_money_ledger"]
    assert ledger["town_tax_collected"] == collected


def test_tax_runs_only_on_interval_and_stops_at_treasury_target():
    manager = EconomyManager({"town_gold": 1000, "npc_gold": {"商户": 1100}})
    manager.state.tick = 9
    assert manager._collect_town_tax() == 0
    manager.state.tick = 10
    assert manager._collect_town_tax() > 0

    full = EconomyManager({"town_gold": 8000, "npc_gold": {"商户": 5000}})
    full.state.tick = 10
    assert full._collect_town_tax() == 0
    assert full.state.npc_gold["商户"] == 5000


def test_tax_rate_responds_to_region_commerce_and_security():
    def collect(commerce, security):
        manager = EconomyManager({
            "town_gold": 4000,
            "npc_gold": {"商户": 3000},
            "events": {"region_ecology": {"guiyun_city": {
                "commerce": commerce, "security": security}}},
        })
        manager.state.tick = 10
        return manager._collect_town_tax()

    assert collect(90, 90) > collect(30, 30) > 0


def test_tax_never_creates_money_for_empty_wallets():
    manager = EconomyManager({
        "town_gold": 0,
        "npc_gold": {"商户": 0},
        "caravans": {"商队": {"gold": 0, "inventory": {}, "capacity": 8}},
    })
    manager.state.tick = 10
    assert manager._collect_town_tax() == 0
    assert manager.state.town_gold == 0


def test_long_cycle_keeps_town_treasury_and_caravan_cargo_flowing():
    manager = EconomyManager()
    manager.update(1500)
    snapshot = manager.economic_audit_snapshot()

    # 旧版在 500 Tick 内就见底并让商队长期滞留货物；商税闭环应维持城镇购买力。
    assert snapshot["town_gold"] > 1000
    assert snapshot["town_tax_collected"] > 0
    assert snapshot["caravan_item_units"] < 60
