import json
import os
import unittest
from economy import EconomyManager, TradeService

BASE = os.path.dirname(os.path.dirname(__file__))

class DummyPlayer:
    def __init__(self):
        self.gold = 1000
        self.inventory = []
        self.economy_state = {}
        self.world_state = {"variables": {"quest_clock": 0}}

class Alpha21MiningLoggingLoopTests(unittest.TestCase):
    def test_mining_and_logging_are_separate_data_driven_actions(self):
        manager = EconomyManager()
        ok, (item, amount) = manager.mine("abandoned_iron_mine", 3)
        self.assertTrue(ok)
        self.assertEqual(item, "铁矿石")
        self.assertEqual(amount, 3)
        self.assertFalse(manager.chop("abandoned_iron_mine")[0])
        ok, (item, amount) = manager.chop("mistwood_trail", 3)
        self.assertTrue(ok)
        self.assertEqual(item, "木材")
        self.assertEqual(amount, 3)
        self.assertFalse(manager.mine("mistwood_trail")[0])

    def test_logging_command_aliases_are_registered_for_dispatch(self):
        import main
        room = {"exits": {}}
        for alias in ("伐木", "砍树", "采伐", "chop", "logging"):
            cmd, _ = main.parse_command(alias)
            self.assertEqual(cmd, "chop", alias)
            self.assertTrue(main.command_will_be_handled(cmd, room), alias)

    def test_lumberjack_is_real_npc_and_consumes_shared_forest_resource(self):
        with open(os.path.join(BASE, "data", "npcs.json"), encoding="utf-8") as f:
            npcs = json.load(f)
        with open(os.path.join(BASE, "data", "rooms.json"), encoding="utf-8") as f:
            rooms = json.load(f)
        with open(os.path.join(BASE, "data", "economy", "gatherers.json"), encoding="utf-8") as f:
            gatherers = json.load(f)
        self.assertIn("樵夫老周", npcs)
        self.assertIn("樵夫老周", rooms["mistwood_trail"]["npcs"])
        manager = EconomyManager({"resources": {"mistwood_trail": {"remaining": 2, "last_tick": 0}}})
        manager.caravan_config = {}
        manager.gatherers = {"樵夫老周": gatherers["樵夫老周"]}
        manager.update(4)
        self.assertEqual(manager.state.npc_inventory["樵夫老周"].get("木材", 0), 2)
        self.assertEqual(manager.state.resources["mistwood_trail"]["remaining"], 0)

    def test_herbalist_recipe_consumes_real_herbs(self):
        manager = EconomyManager({"npc_inventory": {"药铺老板": {"草药": 3, "疗伤药": 0}}})
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.update(6)
        stock = manager.state.npc_inventory["药铺老板"]
        self.assertEqual(stock["草药"], 0)
        self.assertEqual(stock["疗伤药"], 1)

    def test_player_can_sell_wood_into_shared_npc_inventory_and_capacity_is_atomic(self):
        player = DummyPlayer()
        player.inventory = ["木材"] * 3
        player.economy_state = {"npc_gold": {"樵夫老周": 100}, "npc_inventory": {"樵夫老周": {"木材": 9998}}}
        ok, _ = TradeService.sell(player, "木材", 2, 6, "樵夫老周")
        self.assertFalse(ok)
        self.assertEqual(player.inventory.count("木材"), 3)
        self.assertEqual(player.gold, 1000)
        self.assertEqual(player.economy_state["npc_inventory"]["樵夫老周"]["木材"], 9998)

    def test_caravan_cannot_overload_when_buying_finished_goods(self):
        manager = EconomyManager({"npc_inventory": {"铁匠": {"铁剑": 5}}, "npc_gold": {"铁匠": 500}})
        manager.gatherers = {}
        manager.caravan_config = {"测试商队": {"route": ["blacksmith", "guiyun_forge"], "capacity": 8, "gold": 500, "inventory": {"木材": 7}}}
        manager.update(1)
        caravan = manager.state.caravans["测试商队"]
        self.assertEqual(sum(max(0, int(v)) for v in caravan["inventory"].values()), 8)
        self.assertEqual(caravan["inventory"].get("铁剑", 0), 1)

    def test_caravan_buys_only_real_pharmacy_production_stock(self):
        manager = EconomyManager({"npc_inventory": {"药铺老板": {"草药": 0, "疗伤药": 2}}, "npc_gold": {"药铺老板": 100}})
        manager.gatherers = {}
        manager.caravan_config = {"药材商队": {"route": ["mistwood_trail", "medicine_shop"], "capacity": 8, "gold": 100, "inventory": {}}}
        manager.update(1)
        caravan = manager.state.caravans["药材商队"]
        self.assertEqual(caravan["inventory"].get("疗伤药", 0), 2)
        self.assertEqual(manager.state.npc_inventory["药铺老板"]["疗伤药"], 0)
        self.assertEqual(caravan["gold"], 76)
        self.assertEqual(manager.state.npc_gold["药铺老板"], 124)

    def test_market_supply_and_trade_counters_stay_bounded(self):
        player = DummyPlayer()
        player.inventory = ["木材"]
        player.economy_state = {"npc_gold": {"樵夫老周": 100}, "npc_inventory": {"樵夫老周": {"木材": 0}}, "market": {"木材": {"traded": 2_000_000_000, "supply": 9999, "last_price": 6}}}
        ok, _ = TradeService.sell(player, "木材", 1, 6, "樵夫老周")
        self.assertTrue(ok)
        market = player.economy_state["market"]["木材"]
        self.assertLessEqual(market["supply"], 9999)
        self.assertLessEqual(market["traded"], 2_000_000_000)

    def test_resource_regeneration_and_state_roundtrip_remain_bounded(self):
        manager = EconomyManager()
        manager.chop("mistwood_trail", 3)
        exported = manager.export_state()
        restored = EconomyManager(exported)
        restored.update(600)
        resource = restored.state.resources["mistwood_trail"]
        self.assertGreaterEqual(resource["remaining"], 0)
        self.assertLessEqual(resource["remaining"], 30)
        self.assertEqual(restored.state.tick, 600)

    def test_economy_configuration_references_real_game_content(self):
        def load(relative):
            with open(os.path.join(BASE, relative), encoding="utf-8") as f:
                return json.load(f)
        rooms = load("data/rooms.json")
        npcs = load("data/npcs.json")
        items = load("data/items.json")
        resources = load("data/economy/resources.json")
        gatherers = load("data/economy/gatherers.json")
        recipes = load("data/economy/recipes.json")
        caravans = load("data/economy/caravans.json")
        for room_id, cfg in resources.items():
            self.assertIn(room_id, rooms)
            self.assertIn(cfg["item"], items)
        for npc_id, cfg in gatherers.items():
            self.assertIn(npc_id, npcs)
            self.assertIn(cfg["room_id"], rooms)
            self.assertIn(cfg["item"], items)
            if cfg.get("resource_room_id"):
                self.assertIn(cfg["resource_room_id"], resources)
        for npc_id, recipe in recipes.items():
            self.assertIn(npc_id, npcs)
            for item in list(recipe.get("inputs", {})) + list(recipe.get("outputs", {})):
                self.assertIn(item, items)
            if recipe.get("room_id"):
                self.assertIn(recipe["room_id"], rooms)
        for caravan in caravans.values():
            self.assertGreater(caravan.get("capacity", 0), 0)
            for stop in caravan.get("route", []):
                self.assertIn(stop, rooms)

    def test_corrupt_trade_containers_fail_safely_without_losing_items(self):
        player = DummyPlayer()
        player.inventory = ["木材"]
        player.economy_state = {"npc_inventory": {"樵夫老周": ["损坏"]}, "npc_gold": {"樵夫老周": 100}}
        ok, _ = TradeService.sell(player, "木材", 1, 5, "樵夫老周")
        self.assertFalse(ok)
        self.assertEqual(player.inventory, ["木材"])
        self.assertEqual(player.gold, 1000)

    def test_ten_thousand_tick_economy_stress_keeps_caps_and_balances(self):
        manager = EconomyManager()
        manager.update(10000)
        state = manager.export_state()
        self.assertEqual(state["tick"], 10000)
        for room_id, row in state["resources"].items():
            if isinstance(row, dict):
                cap = manager.resources.get(room_id, {}).get("capacity", 10**9)
                self.assertGreaterEqual(int(row.get("remaining", 0)), 0)
                self.assertLessEqual(int(row.get("remaining", 0)), cap)
        for stock in state["npc_inventory"].values():
            for amount in stock.values():
                self.assertGreaterEqual(int(amount), 0)
        for caravan_id, caravan in state["caravans"].items():
            self.assertGreaterEqual(int(caravan.get("gold", 0)), 0)
            cargo = sum(max(0, int(v)) for v in caravan.get("inventory", {}).values())
            self.assertLessEqual(cargo, manager.caravan_config[caravan_id].get("capacity", 8))
        self.assertGreaterEqual(int(state["town_gold"]), 0)

if __name__ == "__main__":
    unittest.main()
