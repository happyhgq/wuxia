"""Alpha97：商队成交真实反馈到停靠地区的区域行情。"""
import unittest
from economy import EconomyManager


class Alpha97RegionalCaravanMarketTests(unittest.TestCase):
    def make_manager(self, state, caravan_cfg, rooms, gatherers=None, recipes=None):
        manager = EconomyManager(state)
        manager.caravan_config = caravan_cfg
        manager.resources = {}
        manager.recipes = recipes or {}
        manager.gatherers = gatherers or {}
        manager.world_rooms = rooms
        return manager

    def test_town_sale_increases_only_the_stop_region_supply(self):
        manager = self.make_manager(
            {"tick": 0, "caravans": {"行商": {"position": 0, "gold": 100, "inventory": {"草药": 2}, "capacity": 8}},
             "town_gold": 1000, "market": {"草药": {"supply": 20, "traded": 0, "last_price": 5}},
             "regional_market": {"city": {"草药": {"supply": 20, "traded": 0, "last_price": 5}},
                                "forest": {"草药": {"supply": 20, "traded": 0, "last_price": 5}}}},
            {"行商": {"route": ["safe_stop", "guiyun_south_gate"], "gold": 100, "inventory": {"草药": 2},
                     "capacity": 8, "sale_prices": {"草药": 8}}},
            {"safe_stop": {"zone": "forest"}, "guiyun_south_gate": {"zone": "city"}})
        manager.update(1)
        self.assertEqual(manager.state.regional_market["city"]["草药"]["supply"], 22)
        self.assertEqual(manager.state.regional_market["city"]["草药"]["traded"], 2)
        self.assertEqual(manager.state.regional_market["city"]["草药"]["last_price"], 8)
        self.assertEqual(manager.state.regional_market["forest"]["草药"]["supply"], 20)

    def test_caravan_purchase_reduces_supplier_region_supply(self):
        manager = self.make_manager(
            {"tick": 0, "caravans": {"行商": {"position": 1, "gold": 100, "inventory": {}, "capacity": 8}},
             "npc_inventory": {"采药人": {"草药": 4}}, "npc_gold": {"采药人": 1000},
             "market": {"草药": {"supply": 20, "traded": 0, "last_price": 5}},
             "regional_market": {"forest": {"草药": {"supply": 20, "traded": 0, "last_price": 5}}}},
            {"行商": {"route": ["supplier_room", "town"], "gold": 100, "inventory": {}, "capacity": 8}},
            {"supplier_room": {"zone": "forest"}, "town": {"zone": "city"}},
            {"采药人": {"room_id": "supplier_room", "item": "草药", "capacity": 10}})
        manager.update(1)
        self.assertEqual(manager.state.regional_market["forest"]["草药"]["supply"], 16)
        self.assertEqual(manager.state.regional_market["forest"]["草药"]["traded"], 4)
        self.assertEqual(manager.state.regional_market.get("city", {}).get("草药", {}).get("supply", 20), 20)

    def test_regional_market_values_remain_bounded(self):
        manager = self.make_manager(
            {"tick": 0, "caravans": {"行商": {"position": 0, "gold": 100, "inventory": {"草药": 8}, "capacity": 8}},
             "town_gold": 100000, "regional_market": {"city": {"草药": {"supply": 9998, "traded": 1_999_999_999}}}},
            {"行商": {"route": ["safe_stop", "guiyun_south_gate"], "gold": 100, "inventory": {"草药": 8},
                     "capacity": 8, "sale_prices": {"草药": 8}}},
            {"safe_stop": {"zone": "forest"}, "guiyun_south_gate": {"zone": "city"}})
        manager.update(1)
        row = manager.state.regional_market["city"]["草药"]
        self.assertLessEqual(row["supply"], 9999)
        self.assertLessEqual(row["traded"], 2_000_000_000)


if __name__ == "__main__":
    unittest.main()
