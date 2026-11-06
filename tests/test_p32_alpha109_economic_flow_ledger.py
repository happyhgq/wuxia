"""Alpha109：把玩家交易与系统奖励区分记入经济流水。"""
from types import SimpleNamespace

from economy import TradeService
from rewards import apply_reward_bundle


def _player():
    return SimpleNamespace(
        gold=100,
        inventory=["草药", "草药"],
        inventory_capacity=30,
        location="village_square",
        economy_state={"npc_gold": {"药商": 200}, "npc_inventory": {"药商": {"草药": 4}}, "market": {}, "events": {}},
        world_state={"variables": {"quest_clock": 42}},
        gain_exp=lambda amount: None,
    )


def test_player_trade_ledger_records_transfers_without_calling_them_new_money():
    player = _player()
    ok, _ = TradeService.buy(player, "草药", 1, 8, "药商")
    assert ok
    ok, _ = TradeService.sell(player, "草药", 1, 6, "药商")
    assert ok

    ledger = player.economy_state["events"]["economic_flow_ledger"]
    assert ledger["player_trade_gold_paid"] == 8
    assert ledger["player_trade_gold_received"] == 6
    assert ledger["player_trade_items_bought"] == 1
    assert ledger["player_trade_items_sold"] == 1
    assert ledger["player_trade_transactions"] == 2
    assert "player_reward_gold_created" not in ledger
    rows = player.economy_state["events"]["economic_flow_history"]
    assert [row["direction"] for row in rows] == ["buy", "sell"]
    assert all(row["tick"] == 42 for row in rows)


def test_system_reward_is_tracked_as_new_source_not_trade_transfer():
    player = _player()
    result = apply_reward_bundle(
        player,
        {"gold": 25, "items": [{"item": "草药", "quantity": 3}]},
        source="任务奖励",
        announce=False,
    )
    assert result["ok"]
    ledger = player.economy_state["events"]["economic_flow_ledger"]
    assert ledger["player_reward_gold_created"] == 25
    assert ledger["player_reward_item_units_created"] == 3
    assert ledger["player_reward_items_created"] == {"草药": 3}
    assert ledger.get("player_trade_gold_paid", 0) == 0
    rows = player.economy_state["events"]["economic_flow_history"]
    assert len(rows) == 2
    assert all(row["source"] == "任务奖励" and row["tick"] == 42 for row in rows)


def test_flow_history_is_bounded_and_old_saves_without_ledger_remain_compatible():
    player = _player()
    player.economy_state["events"]["economic_flow_history"] = [{"tick": i} for i in range(100)]
    for _ in range(3):
        TradeService.record_trade(player, "buy", "草药", 1, 1, "药商")
    rows = player.economy_state["events"]["economic_flow_history"]
    assert len(rows) == 100
    assert rows[-1]["source"] == "玩家交易"
    assert player.economy_state["events"]["economic_flow_ledger"]["player_trade_transactions"] == 3
