"""Regression for economy state export/reload across a long-running world."""
import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha49EconomyResumeIntegrityTests(unittest.TestCase):
    def test_export_reload_continue_keeps_world_state_bounded(self):
        manager = EconomyManager()
        manager.update(2500)
        snapshot = manager.export_state()
        resumed = EconomyManager(snapshot)
        resumed.update(2500)
        state = resumed.export_state()

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
        self.assertLessEqual(len(state["trade_history"]), 100)
        self.assertLessEqual(len(state["events"].get("pending_world_announcements", [])), 100)

    def test_corrupted_legacy_economy_fields_are_normalized_on_update(self):
        manager = EconomyManager({
            "tick": "12", "town_gold": "-50", "npc_gold": {"old_npc": "-8"},
            "npc_inventory": {"old_npc": {"草药": "-4", "木材": "999999"}},
            "market": {"草药": {"supply": "-3", "traded": "bad", "last_price": "99999999"}},
            "regional_market": {"旧区域": {"草药": {"supply": "bad"}}},
            "events": [], "caravans": {"旧商队": "broken"}, "resources": {"坏资源点": "broken"},
        })
        manager.update(1)
        state = manager.export_state()
        self.assertEqual(state["tick"], 13)
        self.assertEqual(state["town_gold"], 0)
        self.assertTrue(all(int(v) >= 0 for v in state["npc_gold"].values()))
        self.assertTrue(all(int(v) >= 0 for row in state["npc_inventory"].values() for v in row.values()))
        self.assertTrue(all(int(row["supply"]) >= 0 for row in state["market"].values()))
        self.assertTrue(all(int(row["last_price"]) <= 1_000_000 for row in state["market"].values()))


if __name__ == "__main__":
    unittest.main()
