import unittest
from economy import EconomyManager, EconomyState, TradeService


class DummyPlayer:
    def __init__(self):
        self.gold = 100
        self.inventory = ["铁矿石", "铁矿石", "草药"]
        self.economy_state = {}
        self.world_state = {"variables": {"quest_clock": 12}}


class EconomyAlpha5Tests(unittest.TestCase):
    def test_configured_npc_cannot_sell_item_missing_from_inventory(self):
        player = DummyPlayer()
        player.economy_state = {"npc_inventory": {"铁匠": {"铁矿石": 3}}}
        before = (player.gold, list(player.inventory))
        ok, message = TradeService.buy(player, "铁剑", 1, 30, "铁匠")
        self.assertFalse(ok)
        self.assertIn("库存不足", message)
        self.assertEqual((player.gold, player.inventory), before)

    def test_npc_wallet_limits_player_sales_atomically(self):
        player = DummyPlayer()
        player.economy_state = {"npc_gold": {"铁匠": 3}}
        before = (player.gold, list(player.inventory))
        ok, message = TradeService.sell(player, "铁矿石", 1, 4, "铁匠")
        self.assertFalse(ok)
        self.assertIn("银两不足", message)
        self.assertEqual((player.gold, player.inventory), before)
        self.assertNotIn("铁匠", player.economy_state.get("npc_inventory", {}))

    def test_npc_wallet_and_inventory_round_trip(self):
        player = DummyPlayer()
        ok, _ = TradeService.sell(player, "草药", 1, 3, "药农")
        self.assertTrue(ok)
        self.assertEqual(player.economy_state["npc_gold"]["药农"], 997)
        restored = EconomyState(player.economy_state)
        self.assertEqual(restored.to_dict()["npc_gold"]["药农"], 997)
        self.assertEqual(restored.npc_inventory["药农"]["草药"], 1)

    def test_production_consumes_real_ore_and_updates_market_supply(self):
        manager = EconomyManager({"npc_inventory": {"铁匠": {"铁矿石": 5, "铁剑": 0}}})
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.update(5)
        stock = manager.state.npc_inventory["铁匠"]
        self.assertEqual(stock["铁矿石"], 0)
        self.assertEqual(stock["铁剑"], 1)
        self.assertGreater(manager.state.market["铁剑"]["supply"], 20)

    def test_production_does_not_overfill_configured_output_capacity(self):
        manager = EconomyManager({"npc_inventory": {"铁匠": {"铁矿石": 10, "铁剑": 2}}})
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.recipes["铁匠"]["output_capacity"] = {"铁剑": 2}
        manager.update(10)
        stock = manager.state.npc_inventory["铁匠"]
        self.assertEqual(stock["铁剑"], 2)
        self.assertEqual(stock["铁矿石"], 10)


if __name__ == "__main__":
    unittest.main()
