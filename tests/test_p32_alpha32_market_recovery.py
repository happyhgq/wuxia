import unittest
from economy import EconomyManager


class Alpha32MarketRecoveryTests(unittest.TestCase):
    def test_low_market_supply_recovers_gradually_without_creating_items(self):
        manager = EconomyManager({
            "market": {"测试品甲": {"traded": 12, "last_price": 8, "supply": 0}},
            "npc_inventory": {},
        })
        manager.update(9)
        self.assertEqual(manager.state.market["测试品甲"]["supply"], 0)
        manager.update(1)
        self.assertEqual(manager.state.market["测试品甲"]["supply"], 1)
        self.assertFalse(any("测试品甲" in stock for stock in manager.state.npc_inventory.values()))
        self.assertEqual(manager.state.market["测试品甲"]["traded"], 12)

    def test_high_market_supply_returns_toward_normal(self):
        manager = EconomyManager({
            "market": {"测试品乙": {"traded": 30, "last_price": 6, "supply": 40}},
        })
        manager.update(20)
        self.assertEqual(manager.state.market["测试品乙"]["supply"], 38)

    def test_market_supply_bounds_hold_during_long_simulation(self):
        manager = EconomyManager({
            "market": {
                "铁矿石": {"traded": 2_000_000_000, "last_price": 999999, "supply": 999999},
                "草药": {"traded": -5, "last_price": -1, "supply": -100},
            }
        })
        manager.update(6000)
        for row in manager.state.market.values():
            self.assertGreaterEqual(row["supply"], 0)
            self.assertLessEqual(row["supply"], 9999)
            self.assertGreaterEqual(row["traded"], 0)
            self.assertLessEqual(row["traded"], 2_000_000_000)
            self.assertGreaterEqual(row["last_price"], 0)
            self.assertLessEqual(row["last_price"], 1_000_000)

    def test_export_restore_keeps_market_recovery_behavior(self):
        manager = EconomyManager({"market": {"测试品丙": {"traded": 2, "last_price": 5, "supply": 10}}})
        manager.update(5)
        restored = EconomyManager(manager.export_state())
        restored.update(5)
        self.assertEqual(restored.state.market["测试品丙"]["supply"], 11)
        self.assertEqual(restored.state.tick, 10)


if __name__ == "__main__":
    unittest.main()
