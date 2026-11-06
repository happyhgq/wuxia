"""Alpha79：玩家向 NPC 出售材料时遵守 NPC 的真实库存容量。"""
import copy
import unittest
from economy import TradeService


class Player:
    def __init__(self, state, items, gold=100):
        self.economy_state = copy.deepcopy(state)
        self.inventory = list(items)
        self.inventory_capacity = 100
        self.gold = gold
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha79NpcPurchaseCapacityTests(unittest.TestCase):
    def test_gatherer_cannot_be_overfilled_by_player_sale(self):
        player = Player({"npc_inventory": {"采药人阿芷": {"草药": 15}},
                         "npc_gold": {"采药人阿芷": 100}}, ["草药", "草药"])
        before = copy.deepcopy(player.economy_state)
        ok, message = TradeService.sell(player, "草药", 2, 4, "采药人阿芷")
        self.assertFalse(ok)
        self.assertIn("最多还能收购 1 份", message)
        self.assertEqual(player.inventory, ["草药", "草药"])
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.economy_state, before)

    def test_full_gatherer_rejects_sale_without_destroying_player_goods(self):
        player = Player({"npc_inventory": {"矿工顾三": {"铁矿石": 10}},
                         "npc_gold": {"矿工顾三": 100}}, ["铁矿石"])
        before = copy.deepcopy(player.economy_state)
        ok, message = TradeService.sell(player, "铁矿石", 1, 3, "矿工顾三")
        self.assertFalse(ok)
        self.assertIn("库存已满", message)
        self.assertEqual(player.inventory, ["铁矿石"])
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.economy_state, before)

    def test_recipe_supplier_stock_target_is_also_a_purchase_limit(self):
        player = Player({"npc_inventory": {"木匠老许": {"木材": 2}},
                         "npc_gold": {"木匠老许": 100}}, ["木材", "木材"])
        ok, message = TradeService.sell(player, "木材", 2, 2, "木匠老许")
        self.assertFalse(ok)
        self.assertIn("最多还能收购 1 份", message)
        self.assertEqual(player.inventory, ["木材", "木材"])
        self.assertEqual(player.gold, 100)

    def test_npc_with_no_configured_cap_keeps_legacy_purchase_behavior(self):
        player = Player({"npc_inventory": {"普通商家": {"木材": 0}},
                         "npc_gold": {"普通商家": 100}}, ["木材"] * 5)
        ok, message = TradeService.sell(player, "木材", 5, 2, "普通商家")
        self.assertTrue(ok, message)
        self.assertEqual(player.economy_state["npc_inventory"]["普通商家"]["木材"], 5)


if __name__ == "__main__":
    unittest.main()
