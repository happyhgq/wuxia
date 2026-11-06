"""Alpha73：日常交易防护与长周期经济运行验收。"""
import json
import os
import unittest
from economy import EconomyManager, TradeService

BASE = os.path.dirname(os.path.dirname(__file__))


class Player:
    def __init__(self):
        self.gold = 500
        self.inventory = ["草药", "木材", "铁矿石"]
        self.inventory_capacity = 30
        self.location = "wild_fields"
        self.economy_state = {}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha73RuntimeAuditTests(unittest.TestCase):
    def test_long_cycle_preserves_resource_caravan_and_wallet_bounds(self):
        manager = EconomyManager()
        manager.update(360)
        for room_id, cfg in manager.resources.items():
            row = manager.state.resources.get(room_id)
            if isinstance(row, dict):
                self.assertGreaterEqual(int(row.get("remaining", 0)), 0, room_id)
                self.assertLessEqual(int(row.get("remaining", 0)), max(0, int(cfg.get("capacity", 20))), room_id)
        for cid, cfg in manager.caravan_config.items():
            row = manager.state.caravans.get(cid, {})
            if not isinstance(row, dict):
                continue
            self.assertGreaterEqual(int(row.get("gold", 0)), 0, cid)
            self.assertLessEqual(int(row.get("gold", 0)), 2_000_000_000, cid)
            self.assertLessEqual(sum(max(0, int(v)) for v in row.get("inventory", {}).values()), max(0, int(cfg.get("capacity", 8))), cid)
        for npc_id, gold in manager.state.npc_gold.items():
            self.assertGreaterEqual(int(gold), 0, npc_id)
            self.assertLessEqual(int(gold), 2_000_000_000, npc_id)

    def test_export_and_reload_keeps_economic_state_valid(self):
        manager = EconomyManager()
        manager.update(120)
        reloaded = EconomyManager(manager.export_state())
        reloaded.update(120)
        self.assertEqual(reloaded.state.tick, 240)
        for row in reloaded.state.npc_inventory.values():
            for amount in row.values():
                self.assertGreaterEqual(int(amount), 0)
                self.assertLessEqual(int(amount), 9999)
        for caravan in reloaded.state.caravans.values():
            self.assertGreaterEqual(int(caravan.get("gold", 0)), 0)
            self.assertLessEqual(sum(max(0, int(v)) for v in caravan.get("inventory", {}).values()), int(caravan.get("capacity", 0)))

    def test_broken_player_inventory_returns_message_instead_of_crashing_npc_sale(self):
        player = Player()
        player.inventory = None
        ok, message = TradeService.sell(player, "草药", 1, 5, "药农")
        self.assertFalse(ok)
        self.assertIn("行囊数据异常", message)
        self.assertEqual(player.gold, 500)

    def test_broken_player_inventory_returns_message_instead_of_crashing_caravan_sale(self):
        player = Player()
        player.inventory = None
        player.economy_state = {"caravans": {"北路商队": {"gold": 500, "capacity": 8, "inventory": {}}}}
        ok, message = TradeService.sell_to_caravan(player, "北路商队", "草药", 1, 5)
        self.assertFalse(ok)
        self.assertIn("行囊数据异常", message)
        self.assertEqual(player.gold, 500)

    def test_failed_caravan_trade_is_atomic_when_wallet_or_cargo_is_insufficient(self):
        player = Player()
        player.economy_state = {"caravans": {"北路商队": {"gold": 1, "capacity": 3, "inventory": {"木材": 3}}}}
        before = (player.gold, list(player.inventory), dict(player.economy_state["caravans"]["北路商队"]["inventory"]))
        ok, _ = TradeService.sell_to_caravan(player, "北路商队", "草药", 1, 5)
        self.assertFalse(ok)
        self.assertEqual((player.gold, player.inventory, player.economy_state["caravans"]["北路商队"]["inventory"]), before)

    def test_caravan_buy_and_sell_round_trip_conserves_item_and_gold_accounting(self):
        player = Player()
        player.economy_state = {"caravans": {"北路商队": {"gold": 500, "capacity": 8, "inventory": {"布料": 2}}}}
        ok, _ = TradeService.sell_to_caravan(player, "北路商队", "草药", 1, 5)
        self.assertTrue(ok)
        caravan = player.economy_state["caravans"]["北路商队"]
        self.assertEqual(caravan["gold"], 495)
        self.assertEqual(caravan["inventory"]["草药"], 1)
        ok, _ = TradeService.buy_from_caravan(player, "北路商队", "布料", 1, 10)
        self.assertTrue(ok)
        self.assertEqual(player.gold, 495)
        self.assertEqual(caravan["gold"], 505)
        self.assertEqual(caravan["inventory"]["布料"], 1)

    def test_all_configured_economic_resources_have_valid_action_and_recovery(self):
        with open(os.path.join(BASE, "data", "economy", "resources.json"), encoding="utf-8") as f:
            resources = json.load(f)
        self.assertTrue(resources)
        for room_id, cfg in resources.items():
            with self.subTest(room=room_id):
                self.assertIn(cfg.get("action"), {"gather", "mine", "chop"})
                self.assertGreater(int(cfg.get("capacity", 0)), 0)
                self.assertGreater(int(cfg.get("regen_interval", 0)), 0)
                self.assertGreater(int(cfg.get("regen_amount", 0)), 0)
                self.assertGreaterEqual(int(cfg.get("yield_max", 1)), 1)


if __name__ == "__main__":
    unittest.main()
