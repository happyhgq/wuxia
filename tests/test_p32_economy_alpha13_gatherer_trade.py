import json
import os
import unittest
from economy import EconomyManager, TradeService

BASE = os.path.dirname(os.path.dirname(__file__))


class DummyPlayer:
    def __init__(self):
        self.gold = 0
        self.inventory = ["草药", "草药"]
        self.economy_state = {}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha13GathererTradeTests(unittest.TestCase):
    def test_gatherer_is_a_real_npc_at_its_actual_room(self):
        with open(os.path.join(BASE, "data", "economy", "gatherers.json"), encoding="utf-8") as f:
            gatherers = json.load(f)
        with open(os.path.join(BASE, "data", "npcs.json"), encoding="utf-8") as f:
            npcs = json.load(f)
        with open(os.path.join(BASE, "data", "rooms.json"), encoding="utf-8") as f:
            rooms = json.load(f)
        self.assertIn("采药人阿芷", npcs)
        self.assertIn("采药人阿芷", gatherers)
        room_id = gatherers["采药人阿芷"]["room_id"]
        self.assertIn("采药人阿芷", rooms[room_id].get("npcs", []))
        self.assertIn("草药", npcs["采药人阿芷"].get("shop", []))

    def test_gatherer_produces_real_stock_and_player_can_sell_to_her(self):
        manager = EconomyManager({})
        manager.caravan_config = {}
        manager.update(3)
        player = DummyPlayer()
        player.economy_state = manager.export_state()
        ok, message = TradeService.sell(player, "草药", 2, 4, "采药人阿芷")
        self.assertTrue(ok, message)
        self.assertEqual(player.gold, 8)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_inventory"]["采药人阿芷"]["草药"], 2)
        self.assertEqual(player.economy_state["npc_inventory"]["药铺老板"]["草药"], 2)

    def test_south_caravan_buys_from_actual_gatherer_at_trail_stop(self):
        manager = EconomyManager({
            "npc_inventory": {"采药人阿芷": {"草药": 5}},
            "caravans": {"南路商队": {"position": 0, "gold": 100, "inventory": {"草药": 0}, "visits": 0}},
        })
        manager.update(1)
        caravan = manager.state.caravans["南路商队"]
        self.assertEqual(caravan["inventory"]["草药"], 3)
        self.assertEqual(caravan["gold"], 69)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 0)
        self.assertEqual(manager.state.npc_gold["采药人阿芷"], 1033)


if __name__ == "__main__":
    unittest.main()
