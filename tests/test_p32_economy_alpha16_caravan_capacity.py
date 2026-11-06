import unittest
from economy import EconomyManager


class Alpha16CaravanCapacityTests(unittest.TestCase):
    def test_caravan_gathering_respects_total_cargo_capacity(self):
        manager = EconomyManager({
            "resources": {"abandoned_iron_mine": {"remaining": 10, "last_tick": 0}},
            "caravans": {
                "测试商队": {
                    "position": 0,
                    "gold": 100,
                    "inventory": {"铁剑": 7},
                    "visits": 0,
                }
            },
        })
        manager.caravan_config = {
            "测试商队": {
                "route": ["blacksmith", "abandoned_iron_mine"],
                "gold": 100,
                "capacity": 8,
                "inventory": {"铁剑": 7},
            }
        }
        manager.resources = {"abandoned_iron_mine": {"capacity": 10, "item": "铁矿石"}}
        manager.gatherers = {}
        manager.recipes = {}
        manager.update(1)
        caravan = manager.state.caravans["测试商队"]
        self.assertEqual(sum(max(0, int(v)) for v in caravan["inventory"].values()), 8)
        self.assertEqual(caravan["inventory"]["铁矿石"], 1)
        self.assertEqual(manager.state.resources["abandoned_iron_mine"]["remaining"], 9)

    def test_full_caravan_does_not_consume_world_resources(self):
        manager = EconomyManager({
            "resources": {"abandoned_iron_mine": {"remaining": 10, "last_tick": 0}},
            "caravans": {"测试商队": {"position": 0, "gold": 100, "inventory": {"铁剑": 8}}},
        })
        manager.caravan_config = {"测试商队": {"route": ["blacksmith", "abandoned_iron_mine"], "capacity": 8, "gold": 100}}
        manager.resources = {"abandoned_iron_mine": {"capacity": 10, "item": "铁矿石"}}
        manager.gatherers = {}
        manager.recipes = {}
        manager.update(1)
        self.assertEqual(manager.state.resources["abandoned_iron_mine"]["remaining"], 10)
        self.assertEqual(manager.state.caravans["测试商队"]["inventory"].get("铁矿石", 0), 0)

    def test_default_caravan_configs_define_capacity(self):
        manager = EconomyManager()
        self.assertTrue(manager.caravan_config)
        for config in manager.caravan_config.values():
            self.assertGreater(int(config.get("capacity", 0)), 0)


if __name__ == "__main__":
    unittest.main()
