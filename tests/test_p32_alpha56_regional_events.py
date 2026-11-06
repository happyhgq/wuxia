"""Alpha56：地区行情事件只影响指定地区，并能到期、存档往返。"""
import unittest
from economy import EconomyManager, TradeService


class MarketPlayer:
    def __init__(self, location, state):
        self.location = location
        self.gold = 1000
        self.inventory = []
        self.inventory_capacity = 100
        self.economy_state = state


class Alpha56RegionalEventTests(unittest.TestCase):
    def test_regional_event_changes_only_matching_region_quote(self):
        state = {
            "tick": 10,
            "market": {"木材": {"supply": 20}},
            "regional_market": {},
            "events": {"tick": 10, "regional_market_events": {
                "mistwood": {"name": "山林行情", "rate": 1.2, "until_tick": 20}
            }},
        }
        forest = MarketPlayer("mistwood_trail", state)
        village = MarketPlayer("village_square", state)
        self.assertGreater(TradeService.market_price(forest, "木材", 100, "buy"),
                           TradeService.market_price(village, "木材", 100, "buy"))

    def test_expired_regional_event_no_longer_changes_quote(self):
        state = {
            "tick": 20,
            "market": {"木材": {"supply": 20}},
            "regional_market": {},
            "events": {"tick": 20, "regional_market_events": {
                "mistwood": {"name": "已结束行情", "rate": 1.5, "until_tick": 20}
            }},
        }
        player = MarketPlayer("mistwood_trail", state)
        self.assertEqual(TradeService.market_price(player, "木材", 100, "buy"), 100)

    def test_manager_creates_regional_event_and_preserves_it_in_export(self):
        manager = EconomyManager({"tick": 44, "events": {}, "market": {}, "regional_market": {},
                                  "resources": {}, "npc_inventory": {}, "npc_gold": {},
                                  "caravans": {}, "professions": {}})
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.caravan_config = {}
        manager.update(1)
        state = manager.export_state()
        self.assertIn("mistwood", state["events"]["regional_market_events"])
        self.assertEqual(state["events"]["regional_market_events"]["mistwood"]["until_tick"], 57)
        restored = EconomyManager(state)
        self.assertEqual(restored.state.events["regional_market_events"]["mistwood"]["rate"], 1.18)


if __name__ == "__main__":
    unittest.main()
