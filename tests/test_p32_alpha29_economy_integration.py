import json
import os
import unittest

from economy import EconomyManager, TradeService

BASE = os.path.dirname(os.path.dirname(__file__))


class DummyPlayer:
    def __init__(self, inventory=None, capacity=100):
        self.inventory = list(inventory or [])
        self.inventory_capacity = capacity
        self.gold = 1000
        self.economy_state = {}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha29EconomyIntegrationTests(unittest.TestCase):
    def test_forage_uses_shared_finite_resource_stock(self):
        manager = EconomyManager({"resources": {"mistwood_stream": {"remaining": 2, "last_tick": 0}}})
        ok, result = manager.gather("mistwood_stream", 1)
        self.assertTrue(ok)
        self.assertEqual(result, ("草药", 1))
        self.assertEqual(manager.state.resources["mistwood_stream"]["remaining"], 1)
        ok, result = manager.gather("mistwood_stream", 5)
        self.assertTrue(ok)
        self.assertEqual(result, ("草药", 1))
        self.assertEqual(manager.state.resources["mistwood_stream"]["remaining"], 0)
        self.assertFalse(manager.gather("mistwood_stream")[0])

    def test_herbalist_consumes_the_same_finite_resource_pool(self):
        manager = EconomyManager({"resources": {"mistwood_stream": {"remaining": 1, "last_tick": 0}}})
        manager.caravan_config = {}
        manager.recipes = {}
        manager.gatherers = {"采药人阿芷": {
            "room_id": "mistwood_trail", "resource_room_id": "mistwood_stream",
            "item": "草药", "interval": 1, "amount": 2, "capacity": 10,
        }}
        manager.update(1)
        self.assertEqual(manager.state.resources["mistwood_stream"]["remaining"], 0)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 1)

    def test_player_inventory_capacity_blocks_caravan_purchase_atomically(self):
        player = DummyPlayer(["木材", "铁矿石"], capacity=2)
        player.economy_state = {"caravans": {"北路商队": {
            "gold": 500, "capacity": 8, "inventory": {"草药": 3}
        }}}
        before = dict(player.economy_state["caravans"]["北路商队"]["inventory"])
        ok, message = TradeService.buy_from_caravan(player, "北路商队", "草药", 1, 6)
        self.assertFalse(ok)
        self.assertIn("行囊已满", message)
        self.assertEqual(player.gold, 1000)
        self.assertEqual(player.inventory, ["木材", "铁矿石"])
        self.assertEqual(player.economy_state["caravans"]["北路商队"]["inventory"], before)

    def test_player_inventory_capacity_blocks_npc_purchase_atomically(self):
        player = DummyPlayer(["木材"], capacity=1)
        player.economy_state = {"npc_gold": {"药铺老板": 500}, "npc_inventory": {"药铺老板": {"疗伤药": 2}}}
        ok, message = TradeService.buy(player, "疗伤药", 1, 12, "药铺老板")
        self.assertFalse(ok)
        self.assertIn("行囊已满", message)
        self.assertEqual(player.gold, 1000)
        self.assertEqual(player.economy_state["npc_inventory"]["药铺老板"]["疗伤药"], 2)

    def test_resource_configurations_are_finite_and_reachable(self):
        with open(os.path.join(BASE, "data", "economy", "resources.json"), encoding="utf-8") as f:
            resources = json.load(f)
        with open(os.path.join(BASE, "data", "rooms.json"), encoding="utf-8") as f:
            rooms = json.load(f)
        for room_id, cfg in resources.items():
            self.assertIn(room_id, rooms)
            self.assertGreater(int(cfg.get("capacity", 0)), 0)
            self.assertGreater(int(cfg.get("regen_interval", 0)), 0)
            self.assertGreater(int(cfg.get("regen_amount", 0)), 0)
        self.assertEqual(resources["mistwood_stream"]["action"], "gather")
        self.assertEqual(resources["guiyun_medicine_garden"]["action"], "gather")
        self.assertEqual(resources["sunken_shrine"]["action"], "gather")

    def test_caravan_prices_respond_to_region_event_and_market_supply(self):
        player = DummyPlayer()
        player.economy_state = {"market": {"木材": {"supply": 0}}}
        base = TradeService.market_price(player, "木材", 10, "buy", 1.0, 1.0)
        regional = TradeService.market_price(player, "木材", 10, "buy", 1.2, 1.0)
        eventful = TradeService.market_price(player, "木材", 10, "buy", 1.0, 1.5)
        self.assertGreater(regional, base)
        self.assertGreater(eventful, base)
        player.economy_state["market"]["木材"]["supply"] = 9999
        abundant = TradeService.market_price(player, "木材", 10, "buy", 1.0, 1.0)
        self.assertLess(abundant, base)

    def test_market_events_start_and_expire_without_creating_goods_or_money(self):
        manager = EconomyManager()
        manager.caravan_config = {}
        manager.gatherers = {}
        manager.recipes = {}
        starting_gold = manager.state.town_gold
        manager.update(30)
        event = manager.state.events.get("market_event")
        self.assertIsInstance(event, dict)
        self.assertNotEqual(manager.state.events.get("market_event_rate"), 1.0)
        self.assertTrue(any("江湖行情" in message for message in manager.state.events.get("pending_world_announcements", [])))
        manager.update(10)
        self.assertNotIn("market_event", manager.state.events)
        self.assertEqual(manager.state.events.get("market_event_rate"), 1.0)
        self.assertEqual(manager.state.town_gold, starting_gold)

    def test_v12_style_old_economy_state_defaults_capacity_without_migration(self):
        manager = EconomyManager({"tick": 7, "resources": {}, "npc_inventory": {}})
        manager.update(1)
        restored = EconomyManager(manager.export_state())
        self.assertEqual(restored.state.tick, 8)
        self.assertGreaterEqual(restored.state.town_gold, 0)


if __name__ == "__main__":
    unittest.main()
