"""Alpha52 integrated NPC resource -> workshop -> caravan economy acceptance."""
import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha52FullEconomyCycleTests(unittest.TestCase):
    def _data(self, filename):
        with open(os.path.join(BASE, "data", "economy", filename), encoding="utf-8") as f:
            return json.load(f)

    def _assert_bounded(self, state):
        resources = self._data("resources.json")
        gatherers = self._data("gatherers.json")
        recipes = self._data("recipes.json")
        caravans = self._data("caravans.json")
        for room, cfg in resources.items():
            self.assertGreaterEqual(state["resources"][room]["remaining"], 0)
            self.assertLessEqual(state["resources"][room]["remaining"], cfg["capacity"])
        for npc, cfg in gatherers.items():
            quantity = state["npc_inventory"].get(npc, {}).get(cfg["item"], 0)
            self.assertGreaterEqual(quantity, 0)
            self.assertLessEqual(quantity, cfg["capacity"])
        for npc, recipe in recipes.items():
            stock = state["npc_inventory"].get(npc, {})
            for item, cap in recipe.get("output_capacity", {}).items():
                self.assertGreaterEqual(stock.get(item, 0), 0)
                self.assertLessEqual(stock.get(item, 0), cap)
        for caravan_id, cfg in caravans.items():
            caravan = state["caravans"][caravan_id]
            self.assertGreaterEqual(caravan["gold"], 0)
            self.assertLessEqual(caravan["gold"], 2_000_000_000)
            self.assertLessEqual(sum(max(0, int(v)) for v in caravan["inventory"].values()), cfg["capacity"])

    def test_all_three_npc_production_chains_trade_and_survive_resume(self):
        manager = EconomyManager()
        manager.update(2500)
        first = manager.export_state()
        # Each chain must have produced and sold goods into the shared caravan/market economy.
        for item in ("疗伤药", "木剑", "铁剑"):
            self.assertGreater(first["market"].get(item, {}).get("traded", 0), 0, item)
        self.assertGreater(first["npc_gold"].get("药铺老板", 0), 0)
        self.assertGreater(first["npc_gold"].get("木匠老许", 0), 0)
        self.assertGreater(first["npc_gold"].get("百炼铁铺铁匠", 0), 0)
        self._assert_bounded(first)

        resumed = EconomyManager(first)
        resumed.update(2500)
        final = resumed.export_state()
        self.assertEqual(final["tick"], 5000)
        for item in ("疗伤药", "木剑", "铁剑"):
            self.assertGreaterEqual(final["market"].get(item, {}).get("traded", 0), first["market"].get(item, {}).get("traded", 0))
        self._assert_bounded(final)
        self.assertLessEqual(len(final.get("trade_history", [])), 100)
        self.assertLessEqual(len(final.get("events", {}).get("pending_world_announcements", [])), 100)

    def test_workshop_cannot_make_products_without_real_inputs(self):
        manager = EconomyManager({
            "tick": 0,
            "npc_inventory": {
                "药铺老板": {"草药": 0, "疗伤药": 0},
                "木匠老许": {"木材": 0, "木剑": 0},
                "百炼铁铺铁匠": {"铁矿石": 0, "铁剑": 0},
            },
            "npc_gold": {"药铺老板": 100, "木匠老许": 100, "百炼铁铺铁匠": 100},
        })
        # Disable gathering and supplier routes so this specifically checks the recipe guard.
        manager.gatherers = {}
        manager.recipes = {
            npc: {"interval": 1, "inputs": inputs, "outputs": outputs, "output_capacity": caps}
            for npc, inputs, outputs, caps in (
                ("药铺老板", {"草药": 3}, {"疗伤药": 1}, {"疗伤药": 12}),
                ("木匠老许", {"木材": 3}, {"木剑": 1}, {"木剑": 8}),
                ("百炼铁铺铁匠", {"铁矿石": 5}, {"铁剑": 1}, {"铁剑": 8}),
            )
        }
        manager.caravan_config = {}
        manager.update(20)
        state = manager.export_state()
        self.assertEqual(state["npc_inventory"]["药铺老板"]["疗伤药"], 0)
        self.assertEqual(state["npc_inventory"]["木匠老许"]["木剑"], 0)
        self.assertEqual(state["npc_inventory"]["百炼铁铺铁匠"]["铁剑"], 0)


if __name__ == "__main__":
    unittest.main()
