import json
import os
import unittest
from economy import EconomyManager, TradeService

BASE = os.path.dirname(os.path.dirname(__file__))


class DummyPlayer:
    def __init__(self):
        self.gold = 500
        self.inventory = ["铁矿石"] * 5
        self.economy_state = {}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha14ProductionLoopTests(unittest.TestCase):
    def test_smith_recipe_has_a_finite_output_stock_cap(self):
        with open(os.path.join(BASE, "data", "economy", "recipes.json"), encoding="utf-8") as f:
            recipes = json.load(f)
        self.assertEqual(recipes["铁匠"]["output_capacity"]["铁剑"], 8)
        self.assertEqual(recipes["百炼铁铺铁匠"]["output_capacity"]["铁剑"], 8)

    def test_smith_consumes_real_ore_and_produces_swords(self):
        manager = EconomyManager({
            "npc_inventory": {"铁匠": {"铁矿石": 5, "铁剑": 0}},
            "npc_gold": {"铁匠": 1000},
        })
        manager.caravan_config = {}
        manager.update(5)
        stock = manager.state.npc_inventory["铁匠"]
        self.assertEqual(stock["铁矿石"], 0)
        self.assertEqual(stock["铁剑"], 1)
        self.assertGreaterEqual(manager.state.market["铁剑"]["supply"], 21)

    def test_smith_stock_never_exceeds_configured_capacity(self):
        manager = EconomyManager({
            "npc_inventory": {"铁匠": {"铁矿石": 100, "铁剑": 8}},
        })
        manager.caravan_config = {}
        manager.update(20)
        self.assertLessEqual(manager.state.npc_inventory["铁匠"]["铁剑"], 8)
        self.assertEqual(manager.state.npc_inventory["铁匠"]["铁矿石"], 100)

    def test_player_can_sell_ore_to_smith_and_buy_a_real_sword(self):
        manager = EconomyManager({
            "npc_inventory": {"铁匠": {"铁矿石": 0, "铁剑": 1}},
            "npc_gold": {"铁匠": 1000},
        })
        player = DummyPlayer()
        player.economy_state = manager.export_state()
        ok, message = TradeService.sell(player, "铁矿石", 5, 2, "铁匠")
        self.assertTrue(ok, message)
        self.assertEqual(player.economy_state["npc_inventory"]["铁匠"]["铁矿石"], 5)
        ok, message = TradeService.buy(player, "铁剑", 1, 30, "铁匠")
        self.assertTrue(ok, message)
        self.assertEqual(player.economy_state["npc_inventory"]["铁匠"]["铁剑"], 0)
        self.assertIn("铁剑", player.inventory)

    def test_north_caravan_delivers_ore_and_can_buy_smith_stock(self):
        manager = EconomyManager({
            "resources": {"abandoned_iron_mine": {"remaining": 20, "last_tick": 0}},
            "npc_inventory": {"铁匠": {"铁矿石": 0, "铁剑": 0}},
            "npc_gold": {"铁匠": 1000},
            "caravans": {"北路商队": {"position": 0, "gold": 500, "inventory": {"铁矿石": 0, "铁剑": 0}, "visits": 0}},
        })
        manager.update(20)
        caravan = manager.state.caravans["北路商队"]
        smith = manager.state.npc_inventory["铁匠"]
        self.assertGreaterEqual(caravan["visits"], 12)
        self.assertGreaterEqual(manager.state.market.get("铁剑", {}).get("traded", 0), 1)
        self.assertGreaterEqual(caravan["inventory"].get("铁剑", 0), 0)
        self.assertGreaterEqual(smith.get("铁剑", 0), 0)
        # The production/sales loop must preserve non-negative stock and wallets.
        self.assertGreaterEqual(caravan["gold"], 0)
        self.assertGreaterEqual(manager.state.npc_gold.get("铁匠", 0), 0)
        self.assertGreaterEqual(manager.state.town_gold, 0)
        self.assertLess(manager.state.town_gold, 5000)  # 城镇确实为商队成品付款


if __name__ == "__main__":
    unittest.main()
