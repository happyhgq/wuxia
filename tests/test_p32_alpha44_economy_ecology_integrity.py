"""Alpha44: verify that NPC gatherers are discoverable traders and economy data stays connected."""
import json
import os
import unittest
from economy import EconomyManager, TradeService

BASE = os.path.dirname(os.path.dirname(__file__))


def load_json(*parts):
    with open(os.path.join(BASE, *parts), encoding="utf-8") as f:
        return json.load(f)


class PlayerStub:
    def __init__(self):
        self.location = "abandoned_iron_mine"
        self.gold = 100
        self.inventory = []
        self.inventory_capacity = 20
        self.economy_state = {
            "npc_inventory": {"矿工顾三": {"铁矿石": 4}},
            "npc_gold": {"矿工顾三": 20},
            "market": {},
        }
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha44EconomyEcologyIntegrityTests(unittest.TestCase):
    def test_gatherer_npcs_are_present_in_their_room_and_can_trade_their_resource(self):
        npcs = load_json("data", "npcs.json")
        rooms = load_json("data", "rooms.json")
        resources = load_json("data", "economy", "resources.json")
        gatherers = load_json("data", "economy", "gatherers.json")
        for npc_id, cfg in gatherers.items():
            with self.subTest(npc=npc_id):
                self.assertIn(npc_id, npcs)
                self.assertIn(cfg["room_id"], rooms)
                self.assertIn(npc_id, rooms[cfg["room_id"]].get("npcs", []))
                self.assertIn(cfg["resource_room_id"], resources)
                self.assertEqual(resources[cfg["resource_room_id"]].get("item"), cfg["item"])
                self.assertIn(cfg["item"], npcs[npc_id].get("shop", []))

    def test_player_can_buy_real_ore_from_miner_stock(self):
        npcs = load_json("data", "npcs.json")
        self.assertIn("铁矿石", npcs["矿工顾三"].get("shop", []))
        player = PlayerStub()
        ok, message = TradeService.buy(player, "铁矿石", 2, 3, "矿工顾三")
        self.assertTrue(ok, message)
        self.assertEqual(player.inventory.count("铁矿石"), 2)
        self.assertEqual(player.gold, 94)
        self.assertEqual(player.economy_state["npc_inventory"]["矿工顾三"]["铁矿石"], 2)
        self.assertEqual(player.economy_state["npc_gold"]["矿工顾三"], 26)

    def test_recipe_inputs_outputs_and_supplier_routes_reference_real_data(self):
        npcs = load_json("data", "npcs.json")
        rooms = load_json("data", "rooms.json")
        items = load_json("data", "items.json")
        recipes = load_json("data", "economy", "recipes.json")
        # Item data is commonly keyed by Chinese item name; support list-shaped data too.
        item_names = set(items) if isinstance(items, dict) else {
            str(row.get("name", row.get("名称", ""))) for row in items if isinstance(row, dict)
        }
        for npc_id, recipe in recipes.items():
            with self.subTest(recipe=npc_id):
                self.assertIn(npc_id, npcs)
                if recipe.get("room_id"):
                    self.assertIn(recipe["room_id"], rooms)
                for item_name in list(recipe.get("inputs", {})) + list(recipe.get("outputs", {})):
                    self.assertIn(item_name, item_names)
                for route in recipe.get("supplier_routes", []):
                    self.assertGreater(int(route.get("interval", 5)), 0)
                    self.assertGreater(int(route.get("max_per_tick", 1)), 0)
                    self.assertGreater(int(route.get("max_stock", 1)), 0)
                    for supplier in route.get("suppliers", []):
                        self.assertIn(supplier, npcs)
                        self.assertIn(supplier, load_json("data", "economy", "gatherers.json"))

    def test_legacy_save_without_miner_stock_remains_supported(self):
        manager = EconomyManager({"npc_inventory": {}, "npc_gold": {}})
        manager.update(15)
        state = manager.export_state()
        self.assertIsInstance(state.get("npc_inventory"), dict)
        self.assertLessEqual(state.get("npc_inventory", {}).get("矿工顾三", {}).get("铁矿石", 0), 10)


if __name__ == "__main__":
    unittest.main()
