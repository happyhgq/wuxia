"""Alpha72: player-facing economy acceptance across NPCs, caravans, and save/resume."""
import copy
from economy import EconomyManager, TradeService


class Player:
    def __init__(self, state=None, inventory=None, gold=1000, capacity=100):
        self.gold = gold
        self.inventory = list(inventory or [])
        self.inventory_capacity = capacity
        self.economy_state = copy.deepcopy(state or {})
        self.world_state = {"variables": {"quest_clock": 0}}
        self.location = "village_square"


def caravan_state(gold=500, capacity=8, inventory=None):
    return {"caravans": {"北路商队": {"gold": gold, "capacity": capacity,
                                      "inventory": dict(inventory or {})}},
            "npc_inventory": {"药铺老板": {"草药": 5, "疗伤药": 2}},
            "npc_gold": {"药铺老板": 300}}


def test_player_sells_gathered_material_to_caravan_and_state_moves_atomically():
    player = Player(caravan_state(), ["草药", "草药"])
    ok, message = TradeService.sell_to_caravan(player, "北路商队", "草药", 2, 6)
    assert ok, message
    assert player.inventory == []
    assert player.gold == 1012
    assert player.economy_state["caravans"]["北路商队"]["inventory"]["草药"] == 2
    assert player.economy_state["caravans"]["北路商队"]["gold"] == 488
    assert player.economy_state["trade_history"][-1]["side"] == "sell"


def test_player_buys_caravan_goods_and_stock_and_wallet_reconcile():
    player = Player(caravan_state(inventory={"木材": 4}), [], gold=100)
    ok, message = TradeService.buy_from_caravan(player, "北路商队", "木材", 2, 10)
    assert ok, message
    assert player.inventory == ["木材", "木材"]
    assert player.gold == 80
    assert player.economy_state["caravans"]["北路商队"]["inventory"]["木材"] == 2
    assert player.economy_state["caravans"]["北路商队"]["gold"] == 520


def test_caravan_insufficient_gold_does_not_partially_remove_player_goods():
    player = Player(caravan_state(gold=5), ["铁矿石", "铁矿石"])
    before = copy.deepcopy(player.economy_state)
    ok, _ = TradeService.sell_to_caravan(player, "北路商队", "铁矿石", 2, 10)
    assert not ok
    assert player.inventory == ["铁矿石", "铁矿石"]
    assert player.gold == 1000
    assert player.economy_state == before


def test_full_cargo_does_not_partially_settle_player_sale():
    player = Player(caravan_state(capacity=2, inventory={"木材": 2}), ["草药"])
    before = copy.deepcopy(player.economy_state)
    ok, _ = TradeService.sell_to_caravan(player, "北路商队", "草药", 1, 6)
    assert not ok
    assert player.inventory == ["草药"]
    assert player.gold == 1000
    assert player.economy_state == before


def test_player_can_sell_material_to_real_npc_and_buy_only_available_stock():
    player = Player(caravan_state(), ["草药", "草药"])
    ok, message = TradeService.sell(player, "草药", 2, 4, "药铺老板")
    assert ok, message
    assert player.inventory == []
    assert player.gold == 1008
    assert player.economy_state["npc_inventory"]["药铺老板"]["草药"] == 7
    ok, message = TradeService.buy(player, "疗伤药", 1, 12, "药铺老板")
    assert ok, message
    assert player.inventory == ["疗伤药"]
    assert player.gold == 996
    assert player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"] == 1


def test_economy_save_resume_preserves_player_trade_and_world_cycle_bounds():
    manager = EconomyManager()
    manager.update(300)
    snapshot = manager.export_state()
    resumed = EconomyManager(copy.deepcopy(snapshot))
    resumed.update(300)
    final = resumed.export_state()
    assert final["tick"] == 600
    assert len(final.get("trade_history", [])) <= 100
    for row in final.get("resources", {}).values():
        assert row["remaining"] >= 0
    for caravan in final.get("caravans", {}).values():
        assert caravan["gold"] >= 0
        assert sum(max(0, int(v)) for v in caravan["inventory"].values()) <= caravan["capacity"]
