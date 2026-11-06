"""Integrated P3.2 acceptance checks for NPC ecology, trade, maps and V12 compatibility."""
import json
import os
import unittest
from collections import deque

from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


def load_json(relative):
    with open(os.path.join(BASE, relative), encoding="utf-8") as f:
        return json.load(f)


class Alpha48IntegratedAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rooms = load_json("data/rooms.json")
        cls.npcs = load_json("data/npcs.json")
        cls.resources = load_json("data/economy/resources.json")
        cls.gatherers = load_json("data/economy/gatherers.json")
        cls.recipes = load_json("data/economy/recipes.json")
        cls.caravans = load_json("data/economy/caravans.json")

    def test_resource_and_npc_ecology_references_are_consistent(self):
        for npc_id, cfg in self.gatherers.items():
            with self.subTest(npc=npc_id):
                self.assertIn(npc_id, self.npcs)
                self.assertIn(cfg["room_id"], self.rooms)
                self.assertIn(cfg["resource_room_id"], self.resources)
                node = self.resources[cfg["resource_room_id"]]
                self.assertEqual(cfg["item"], node["item"])
                inferred = {"木材": "chop", "铁矿石": "mine"}.get(cfg["item"], "gather")
                self.assertEqual(cfg.get("action", inferred), node.get("action", "mine"))
                self.assertGreaterEqual(int(cfg["capacity"]), 0)

    def test_economic_chain_references_real_npcs_and_rooms(self):
        for npc_id, recipe in self.recipes.items():
            with self.subTest(recipe=npc_id):
                self.assertIn(npc_id, self.npcs)
                room = recipe.get("room_id")
                if room:
                    self.assertIn(room, self.rooms)
                for route in recipe.get("supplier_routes", []):
                    for supplier in route.get("suppliers", []):
                        self.assertIn(supplier, self.gatherers)
        for caravan_id, cfg in self.caravans.items():
            with self.subTest(caravan=caravan_id):
                self.assertGreaterEqual(int(cfg.get("capacity", 0)), 1)
                self.assertTrue(cfg.get("route"))
                for room in cfg["route"]:
                    self.assertIn(room, self.rooms)
                for appearance in cfg.get("appearances", []):
                    self.assertIn(appearance["room"], self.rooms)

    def test_all_resource_nodes_are_reachable_and_have_action_hints(self):
        seen = {"village_gate"}
        queue = deque(seen)
        while queue:
            current = queue.popleft()
            targets = list(self.rooms[current].get("exits", {}).values())
            targets.extend(entry.get("target") for entry in self.rooms[current].get("hidden_exits", {}).values() if isinstance(entry, dict))
            for target in targets:
                self.assertIn(target, self.rooms)
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        self.assertEqual(set(self.rooms), seen)
        for room_id, cfg in self.resources.items():
            with self.subTest(room=room_id):
                self.assertIn(room_id, self.rooms)
                desc = self.rooms[room_id].get("desc", "")
                action = cfg.get("action", "mine")
                hint = {"chop": "伐木", "gather": "搜索", "mine": "采矿"}[action]
                self.assertIn(hint, desc)

    def test_long_run_keeps_resource_inventory_and_wallet_limits(self):
        manager = EconomyManager()
        manager.update(1200)
        state = manager.export_state()
        self.assertEqual(state["tick"], 1200)
        for room_id, cfg in self.resources.items():
            remaining = state["resources"][room_id]["remaining"]
            self.assertGreaterEqual(remaining, 0)
            self.assertLessEqual(remaining, cfg["capacity"])
        for npc_id, cfg in self.gatherers.items():
            amount = state["npc_inventory"].get(npc_id, {}).get(cfg["item"], 0)
            self.assertGreaterEqual(amount, 0)
            self.assertLessEqual(amount, cfg["capacity"])
        for caravan_id, cfg in self.caravans.items():
            caravan = state["caravans"][caravan_id]
            self.assertGreaterEqual(caravan["gold"], 0)
            self.assertLessEqual(sum(max(0, int(v)) for v in caravan["inventory"].values()), cfg["capacity"])
        for amount in state["npc_gold"].values():
            self.assertGreaterEqual(amount, 0)
            self.assertLessEqual(amount, 2_000_000_000)

    def test_v12_save_version_is_not_changed_for_this_update(self):
        import engine
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == "__main__":
    unittest.main()
