"""Alpha96：长周期商队交易的市场统计保持在合法范围内。"""
import unittest

from economy import EconomyManager


class Alpha96MarketBoundsTests(unittest.TestCase):
    def test_caravan_town_sale_caps_market_supply_and_traded(self):
        manager = EconomyManager({
            "tick": 0,
            "caravans": {
                "行商": {
                    "position": 0,
                    "gold": 1000,
                    "inventory": {"草药": 8},
                    "capacity": 8,
                    "visits": 0,
                }
            },
            "town_gold": 100000,
            "market": {
                "草药": {"supply": 9998, "traded": 1_999_999_998, "last_price": 8}
            },
        })
        manager.caravan_config = {
            "行商": {
                "route": ["safe_stop", "guiyun_south_gate"],
                "gold": 1000,
                "inventory": {"草药": 8},
                "capacity": 8,
                "sale_prices": {"草药": 8},
            }
        }
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {}
        manager.world_rooms = {"safe_stop": {"zone": "safe"}, "guiyun_south_gate": {"zone": "city"}}

        manager.update(1)

        row = manager.state.market["草药"]
        self.assertEqual(row["supply"], 9999)
        self.assertEqual(row["traded"], 2_000_000_000)
        self.assertGreaterEqual(manager.state.town_gold, 0)
        self.assertLessEqual(manager.state.town_gold, 100000)
        self.assertLessEqual(manager.state.caravans["行商"]["gold"], 2_000_000_000)

    def test_market_statistics_remain_bounded_over_repeated_ticks(self):
        manager = EconomyManager({"tick": 0, "market": {"草药": {"supply": 9999, "traded": 2_000_000_000}}})
        manager.caravan_config = {}
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {}
        manager.world_rooms = {}
        for _ in range(100):
            manager.update(1)
        row = manager.state.market["草药"]
        self.assertGreaterEqual(row["supply"], 0)
        self.assertLessEqual(row["supply"], 9999)
        self.assertGreaterEqual(row["traded"], 0)
        self.assertLessEqual(row["traded"], 2_000_000_000)


if __name__ == "__main__":
    unittest.main()
