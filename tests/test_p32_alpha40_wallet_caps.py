import copy
import unittest

from economy import TradeService


MAX_WALLET = 2_000_000_000


class DummyPlayer:
    def __init__(self, state=None, inventory=None, gold=1000):
        self.gold = gold
        self.inventory = list(inventory or [])
        self.inventory_capacity = 100
        self.economy_state = copy.deepcopy(state or {})
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha40WalletCapTests(unittest.TestCase):
    def test_player_sale_to_caravan_rejects_wallet_overflow_atomically(self):
        player = DummyPlayer({"caravans": {"测试商队": {
            "gold": 100, "capacity": 8, "inventory": {}}}}, ["木材"], MAX_WALLET - 2)
        before_state = copy.deepcopy(player.economy_state)
        ok, _ = TradeService.sell_to_caravan(player, "测试商队", "木材", 1, 5)
        self.assertFalse(ok)
        self.assertEqual(player.gold, MAX_WALLET - 2)
        self.assertEqual(player.inventory, ["木材"])
        self.assertEqual(player.economy_state, before_state)

    def test_caravan_buy_rejects_caravan_wallet_overflow_atomically(self):
        player = DummyPlayer({"caravans": {"测试商队": {
            "gold": MAX_WALLET - 2, "capacity": 8, "inventory": {"木材": 1}}}}, [], 100)
        before_state = copy.deepcopy(player.economy_state)
        ok, _ = TradeService.buy_from_caravan(player, "测试商队", "木材", 1, 5)
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state, before_state)

    def test_npc_shop_sale_and_purchase_respect_wallet_caps(self):
        player = DummyPlayer({"npc_inventory": {"木匠老许": {"木剑": 2}},
                              "npc_gold": {"木匠老许": MAX_WALLET}}, [], 100)
        before_state = copy.deepcopy(player.economy_state)
        ok, _ = TradeService.buy(player, "木剑", 1, 6, "木匠老许")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state, before_state)

        player = DummyPlayer({"npc_inventory": {"樵夫老周": {}},
                              "npc_gold": {"樵夫老周": 1000}}, ["木材"], MAX_WALLET - 1)
        before_state = copy.deepcopy(player.economy_state)
        ok, _ = TradeService.sell(player, "木材", 1, 5, "樵夫老周")
        self.assertFalse(ok)
        self.assertEqual(player.gold, MAX_WALLET - 1)
        self.assertEqual(player.inventory, ["木材"])
        self.assertEqual(player.economy_state, before_state)

    def test_invalid_player_wallet_is_rejected_without_mutation(self):
        player = DummyPlayer({"caravans": {"测试商队": {
            "gold": 100, "capacity": 8, "inventory": {"木材": 1}}}}, [], MAX_WALLET + 1)
        before_state = copy.deepcopy(player.economy_state)
        ok, _ = TradeService.buy_from_caravan(player, "测试商队", "木材", 1, 5)
        self.assertFalse(ok)
        self.assertEqual(player.gold, MAX_WALLET + 1)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state, before_state)


if __name__ == "__main__":
    unittest.main()
