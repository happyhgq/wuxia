"""Long-cycle regression for the integrated NPC/resource/caravan economy."""
import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha47LongCycleIntegrityTests(unittest.TestCase):
    def test_five_thousand_ticks_preserve_stock_capacity_and_wallet_bounds(self):
        manager = EconomyManager()
        manager.update(5000)
        state = manager.export_state()
        with open(os.path.join(BASE, "data", "economy", "resources.json"), encoding="utf-8") as f:
            resources = json.load(f)
        with open(os.path.join(BASE, "data", "economy", "gatherers.json"), encoding="utf-8") as f:
            gatherers = json.load(f)
        with open(os.path.join(BASE, "data", "economy", "recipes.json"), encoding="utf-8") as f:
            recipes = json.load(f)
        with open(os.path.join(BASE, "data", "economy", "caravans.json"), encoding="utf-8") as f:
            caravans = json.load(f)

        self.assertEqual(state["tick"], 5000)
        for room_id, cfg in resources.items():
            row = state["resources"][room_id]
            self.assertGreaterEqual(row["remaining"], 0)
            self.assertLessEqual(row["remaining"], cfg["capacity"])
        for npc_id, cfg in gatherers.items():
            amount = state["npc_inventory"].get(npc_id, {}).get(cfg["item"], 0)
            self.assertGreaterEqual(amount, 0)
            self.assertLessEqual(amount, cfg["capacity"])
        for npc_id, recipe in recipes.items():
            stock = state["npc_inventory"].get(npc_id, {})
            for item, capacity in recipe.get("output_capacity", {}).items():
                self.assertGreaterEqual(stock.get(item, 0), 0)
                self.assertLessEqual(stock.get(item, 0), capacity)
        for caravan_id, cfg in caravans.items():
            caravan = state["caravans"][caravan_id]
            self.assertGreaterEqual(caravan["gold"], 0)
            self.assertLessEqual(caravan["gold"], 2_000_000_000)
            self.assertLessEqual(sum(max(0, int(v)) for v in caravan["inventory"].values()), cfg["capacity"])
        for wallet in state["npc_gold"].values():
            self.assertGreaterEqual(wallet, 0)
            self.assertLessEqual(wallet, 2_000_000_000)

    def test_missing_or_mismatched_resource_pool_does_not_create_goods(self):
        for resource_cfg, item in ((None, "草药"), ({"item": "铁矿石", "capacity": 5}, "草药")):
            manager = EconomyManager({})
            manager.resources = {"source": resource_cfg} if resource_cfg is not None else {}
            manager.gatherers = {"测试采集者": {
                "room_id": "room", "resource_room_id": "source", "item": item,
                "interval": 1, "amount": 3, "capacity": 10,
            }}
            manager.recipes = {}
            manager.caravan_config = {}
            manager.update(3)
            self.assertEqual(manager.state.npc_inventory.get("测试采集者", {}).get(item, 0), 0)


if __name__ == "__main__":
    unittest.main()
