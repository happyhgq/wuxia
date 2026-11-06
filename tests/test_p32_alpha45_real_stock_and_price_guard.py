"""Alpha45: prevent simulated economy NPCs from selling phantom stock or free trades."""
import unittest
from economy import TradeService


class PlayerStub:
    def __init__(self, inventory=None, gold=100, economy_state=None):
        self.location = "abandoned_iron_mine"
        self.inventory = list(inventory or [])
        self.inventory_capacity = 20
        self.gold = gold
        self.economy_state = economy_state or {"npc_inventory": {}, "npc_gold": {}, "market": {}}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha45TradeGuardTests(unittest.TestCase):
    def test_economy_npc_cannot_sell_when_legacy_save_has_no_stock_entry(self):
        player = PlayerStub(economy_state={"npc_inventory": {}, "npc_gold": {"矿工顾三": 100}, "market": {}})
        before = (player.gold, list(player.inventory), dict(player.economy_state["npc_gold"]))
        ok, message = TradeService.buy(player, "铁矿石", 1, 3, "矿工顾三")
        self.assertFalse(ok)
        self.assertIn("现货", message)
        self.assertEqual((player.gold, player.inventory, player.economy_state["npc_gold"]), before)

    def test_economy_npc_cannot_sell_more_than_real_stock(self):
        player = PlayerStub(economy_state={"npc_inventory": {"矿工顾三": {"铁矿石": 1}}, "npc_gold": {"矿工顾三": 100}, "market": {}})
        ok, _ = TradeService.buy(player, "铁矿石", 2, 3, "矿工顾三")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_inventory"]["矿工顾三"]["铁矿石"], 1)

    def test_zero_price_purchase_is_rejected_without_mutation(self):
        player = PlayerStub(economy_state={"npc_inventory": {"矿工顾三": {"铁矿石": 1}}, "npc_gold": {"矿工顾三": 100}, "market": {}})
        ok, _ = TradeService.buy(player, "铁矿石", 1, 0, "矿工顾三")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_inventory"]["矿工顾三"]["铁矿石"], 1)

    def test_zero_price_sale_is_rejected_without_mutation(self):
        player = PlayerStub(inventory=["木材"], gold=100)
        ok, _ = TradeService.sell(player, "木材", 1, 0, "木匠老许")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, ["木材"])
        self.assertNotIn("木匠老许", player.economy_state["npc_inventory"])

    def test_legacy_static_shop_without_simulated_stock_remains_compatible(self):
        player = PlayerStub()
        ok, _ = TradeService.buy(player, "布料", 1, 2, "旧式杂货铺")
        self.assertTrue(ok)
        self.assertEqual(player.gold, 98)
        self.assertEqual(player.inventory, ["布料"])


if __name__ == "__main__":
    unittest.main()
