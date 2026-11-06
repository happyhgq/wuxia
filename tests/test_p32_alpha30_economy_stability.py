import copy
import unittest

from economy import EconomyManager, TradeService


class DummyPlayer:
    def __init__(self, state=None, inventory=None, capacity=100):
        self.gold = 1000
        self.inventory = list(inventory or [])
        self.inventory_capacity = capacity
        self.economy_state = copy.deepcopy(state or {})
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha30EconomyStabilityTests(unittest.TestCase):
    def test_over_capacity_legacy_caravan_can_sell_goods_to_recover(self):
        player = DummyPlayer({"caravans": {"北路商队": {
            "gold": 100, "capacity": 2,
            "inventory": {"木材": 3, "铁矿石": 2}
        }}}, inventory=[])
        ok, message = TradeService.buy_from_caravan(player, "北路商队", "木材", 2, 10)
        self.assertTrue(ok, message)
        caravan = player.economy_state["caravans"]["北路商队"]
        self.assertEqual(caravan["inventory"]["木材"], 1)
        self.assertEqual(sum(caravan["inventory"].values()), 3)
        self.assertEqual(player.gold, 980)

    def test_corrupt_caravan_quantities_are_sanitized_before_trade(self):
        player = DummyPlayer({"caravans": {"测试商队": {
            "gold": "50", "capacity": "5",
            "inventory": {"木材": "2", "铁矿石": -4, "草药": "bad"}
        }}})
        ok, message = TradeService.buy_from_caravan(player, "测试商队", "木材", 1, 5)
        self.assertTrue(ok, message)
        stock = player.economy_state["caravans"]["测试商队"]["inventory"]
        self.assertEqual(stock, {"木材": 1, "铁矿石": 0, "草药": 0})
        self.assertEqual(player.gold, 995)

    def test_long_world_cycle_preserves_bounds_and_export_restore(self):
        state = {
            "tick": 0,
            "resources": {"mistwood_stream": {"remaining": 999, "last_tick": 0}},
            "npc_inventory": {
                "铁匠": {"铁矿石": 35, "铁剑": 0},
                "百炼铁铺铁匠": {"铁矿石": 25, "铁剑": 0},
                "药铺老板": {"草药": 30, "疗伤药": 0},
            },
            "npc_gold": {"铁匠": 1000, "百炼铁铺铁匠": 1000, "药铺老板": 1000},
            "town_gold": 5000,
        }
        manager = EconomyManager(state)
        manager.update(5000)
        exported = manager.export_state()
        restored = EconomyManager(copy.deepcopy(exported))
        restored.update(1000)
        final = restored.export_state()
        self.assertEqual(final["tick"], 6000)
        self.assertLessEqual(final["resources"]["mistwood_stream"]["remaining"], 18)
        self.assertGreaterEqual(final["resources"]["mistwood_stream"]["remaining"], 0)
        self.assertLessEqual(final["npc_inventory"]["铁匠"].get("铁剑", 0), 8)
        self.assertLessEqual(final["npc_inventory"]["百炼铁铺铁匠"].get("铁剑", 0), 8)
        self.assertLessEqual(final["npc_inventory"]["药铺老板"].get("疗伤药", 0), 12)
        self.assertLessEqual(len(final["trade_history"]), 100)
        for wallet in final["npc_gold"].values():
            self.assertGreaterEqual(wallet, 0)
        for caravan in final["caravans"].values():
            self.assertGreaterEqual(caravan["gold"], 0)
            self.assertLessEqual(sum(max(0, int(v)) for v in caravan["inventory"].values()), caravan["capacity"])
        self.assertLessEqual(len(final["events"].get("pending_world_announcements", [])), 100)

    def test_corrupt_resource_and_market_values_are_clamped_on_first_tick(self):
        manager = EconomyManager({
            "resources": {"mistwood_stream": {"remaining": 9999, "last_tick": 0}},
            "market": {"木材": {"supply": 999999, "traded": -5, "last_price": 99999999}},
        })
        manager.update(1)
        self.assertEqual(manager.state.resources["mistwood_stream"]["remaining"], 18)
        self.assertEqual(manager.state.market["木材"]["supply"], 9999)
        self.assertEqual(manager.state.market["木材"]["traded"], 0)
        self.assertEqual(manager.state.market["木材"]["last_price"], 1_000_000)

    def test_export_restore_does_not_duplicate_pending_arrivals(self):
        manager = EconomyManager()
        manager.update(40)
        snapshot = manager.export_state()
        restored = EconomyManager(copy.deepcopy(snapshot))
        self.assertEqual(restored.export_state()["events"].get("pending_world_announcements", []),
                         snapshot["events"].get("pending_world_announcements", []))
        self.assertEqual(restored.state.tick, manager.state.tick)


if __name__ == "__main__":
    unittest.main()
