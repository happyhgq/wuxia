from copy import deepcopy

from economy import TradeService
from player import Player


def test_failed_sale_does_not_initialize_unaffordable_counterparty_wallet():
    player = Player("交易测试", "散人")
    player.inventory = ["草药", "草药"]
    state = {
        "npc_inventory": {},
        "npc_gold": {},
        "market": {},
        "trade_history": [],
        "events": {"economy_money_ledger": {"seeded_trade_counterparty_gold": 0}},
    }
    player.economy_state = deepcopy(state)
    before_inventory = list(player.inventory)
    before_gold = player.gold
    before_state = deepcopy(player.economy_state)

    ok, message = TradeService.sell(player, "草药", 2, 600, "临时药商")

    assert not ok
    assert "银两不足" in message
    assert player.inventory == before_inventory
    assert player.gold == before_gold
    assert player.economy_state == before_state
    assert "临时药商" not in player.economy_state["npc_gold"]
    assert "临时药商" not in player.economy_state["events"].get("counterparty_wallet_bootstrap", {})
