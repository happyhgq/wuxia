import unittest
from economy import EconomyManager, TradeService


class RegionalPlayer:
    def __init__(self, location):
        self.location = location
        self.gold = 1000
        self.inventory = []
        self.inventory_capacity = 100
        self.economy_state = {"market": {"木材": {"traded": 0, "last_price": 5, "supply": 20}}}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha42RegionalMarketTests(unittest.TestCase):
    def test_trade_supply_isolated_by_room_zone(self):
        village = RegionalPlayer("village_square")
        forest = RegionalPlayer("mistwood_trail")
        TradeService.record_trade(village, "sell", "木材", 12, 5, "村镇行商")
        self.assertIn("main", village.economy_state["regional_market"])
        self.assertEqual(village.economy_state["regional_market"]["main"]["木材"]["supply"], 32)
        # Separate player state in another zone starts from the global baseline, not the village's regional row.
        self.assertEqual(TradeService.market_price(forest, "木材", 10, "buy"), 10)
        TradeService.record_trade(forest, "buy", "木材", 4, 10, "行商")
        self.assertEqual(forest.economy_state["regional_market"]["mistwood"]["木材"]["supply"], 16)
        self.assertNotIn("main", forest.economy_state["regional_market"])

    def test_new_region_does_not_inherit_other_regions_global_supply(self):
        player = RegionalPlayer("mistwood_trail")
        # 模拟其他地区已大量出售木材，令全局供给远高于中性值。
        player.economy_state["market"]["木材"]["supply"] = 180
        TradeService.record_trade(player, "sell", "木材", 3, 5, "林间行商")
        # 新区域应从自己的中性供给 20 开始，只叠加本次出售的 3 件。
        assert player.economy_state["regional_market"]["mistwood"]["木材"]["supply"] == 23

    def test_region_price_responds_to_local_supply(self):
        player = RegionalPlayer("mistwood_trail")
        player.economy_state["regional_market"] = {
            "mistwood": {"木材": {"traded": 10, "last_price": 10, "supply": 0}},
            "main": {"木材": {"traded": 10, "last_price": 10, "supply": 80}},
        }
        local_scarce = TradeService.market_price(player, "木材", 100, "buy")
        player.location = "village_square"
        local_abundant = TradeService.market_price(player, "木材", 100, "buy")
        self.assertGreater(local_scarce, local_abundant)

    def test_regional_market_survives_economy_state_roundtrip_and_recovers(self):
        manager = EconomyManager({
            "regional_market": {"mistwood": {"木材": {"traded": 40, "last_price": 12, "supply": 0}}},
            "market": {}, "resources": {}, "npc_inventory": {}, "npc_gold": {},
            "caravans": {}, "events": {}, "tick": 0,
        })
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.caravan_config = {}
        manager.update(10)
        exported = manager.export_state()
        self.assertEqual(exported["regional_market"]["mistwood"]["木材"]["supply"], 1)
        restored = EconomyManager(exported)
        restored.resources = {}
        restored.gatherers = {}
        restored.recipes = {}
        restored.caravan_config = {}
        restored.update(10)
        self.assertEqual(restored.state.regional_market["mistwood"]["木材"]["supply"], 2)

    def test_legacy_state_without_regional_market_remains_supported(self):
        manager = EconomyManager({"market": {"木材": {"supply": 25}}})
        self.assertEqual(manager.state.regional_market, {})
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.caravan_config = {}
        manager.update(1)
        self.assertIsInstance(manager.export_state()["regional_market"], dict)


if __name__ == "__main__":
    unittest.main()
