import unittest
from economy import EconomyManager
from actions import _resource_stock_line


class Alpha38CaravanRecoveryTests(unittest.TestCase):
    def test_loaded_caravan_cargo_is_repaired_to_capacity_without_negative_items(self):
        manager = EconomyManager({
            "caravans": {
                "测试商队": {
                    "position": 0,
                    "gold": 9_000_000_000,
                    "capacity": 8,
                    "visits": -2,
                    "inventory": {"木材": 5, "草药": 6, "铁剑": -3},
                }
            }
        })
        manager.caravan_config = {
            "测试商队": {"route": ["起点", "终点"], "capacity": 8, "gold": 500}
        }
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.update(1)
        caravan = manager.state.caravans["测试商队"]
        self.assertLessEqual(sum(caravan["inventory"].values()), 8)
        self.assertEqual(caravan["inventory"], {"木材": 5, "草药": 3})
        self.assertEqual(caravan["gold"], 2_000_000_000)
        self.assertGreaterEqual(caravan["visits"], 0)
        self.assertTrue(all(v >= 0 for v in caravan["inventory"].values()))

    def test_gathering_resource_hint_lists_both_supported_commands(self):
        line = _resource_stock_line("mistwood_stream", {})
        self.assertIn("输入“搜索”发现", line)
        self.assertIn("输入“采集”获取草药", line)
        self.assertIn("草药", line)

    def test_empty_configured_caravan_inventory_stays_empty_and_safe(self):
        manager = EconomyManager({"caravans": {"测试商队": {"inventory": ["损坏"], "gold": "坏数据"}}})
        manager.caravan_config = {"测试商队": {"route": ["起点", "终点"], "capacity": 4, "gold": 100}}
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.update(1)
        caravan = manager.state.caravans["测试商队"]
        self.assertEqual(caravan["inventory"], {})
        self.assertGreaterEqual(caravan["gold"], 0)


if __name__ == "__main__":
    unittest.main()
