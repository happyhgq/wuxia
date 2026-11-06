import unittest
from economy import EconomyManager, TradeService

MAX_WALLET = 2_000_000_000


class DummyPlayer:
    def __init__(self, state=None, inventory=None, gold=1000):
        self.gold = gold
        self.inventory = list(inventory or [])
        self.inventory_capacity = 100
        self.economy_state = state or {}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha41EconomyCapIntegrityTests(unittest.TestCase):
    def test_player_cannot_sell_to_npc_with_invalid_wallet(self):
        player = DummyPlayer({"npc_inventory": {"木匠老许": {"木材": 0}},
                              "npc_gold": {"木匠老许": MAX_WALLET + 1}}, ["木材"], 100)
        ok, _ = TradeService.sell(player, "木材", 1, 5, "木匠老许")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, ["木材"])
        self.assertEqual(player.economy_state["npc_gold"]["木匠老许"], MAX_WALLET + 1)
        self.assertEqual(player.economy_state["npc_inventory"]["木匠老许"]["木材"], 0)

    def test_invalid_npc_wallet_is_not_silently_clamped_during_trade(self):
        player = DummyPlayer({"npc_inventory": {"木匠老许": {"木剑": 2}},
                              "npc_gold": {"木匠老许": MAX_WALLET + 1}}, [], 100)
        ok, _ = TradeService.buy(player, "木剑", 1, 6, "木匠老许")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_inventory"]["木匠老许"]["木剑"], 2)

    def test_caravan_does_not_take_recipe_goods_when_npc_wallet_is_full(self):
        manager = EconomyManager({
            "npc_inventory": {"木匠老许": {"木剑": 3}},
            "npc_gold": {"木匠老许": MAX_WALLET - 1},
            "caravans": {"测试商队": {"position": 0, "gold": 100, "capacity": 6,
                                       "inventory": {}, "visits": 0}},
        })
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {"木匠老许": {"room_id": "village_square", "outputs": {"木剑": 1},
                                        "trade_prices": {"木剑": 6}}}
        manager.caravan_config = {"测试商队": {"route": ["别处", "village_square"], "gold": 100,
                                               "capacity": 6, "sale_prices": {}}}
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["木匠老许"]["木剑"], 3)
        self.assertEqual(manager.state.caravans["测试商队"]["inventory"].get("木剑", 0), 0)
        self.assertLessEqual(manager.state.npc_gold["木匠老许"], MAX_WALLET)

    def test_gatherer_caravan_purchase_respects_npc_wallet_headroom(self):
        manager = EconomyManager({
            "npc_inventory": {"采药人阿芷": {"草药": 4}},
            "npc_gold": {"采药人阿芷": MAX_WALLET - 2},
            "caravans": {"测试商队": {"position": 0, "gold": 100, "capacity": 6,
                                       "inventory": {}, "visits": 0}},
        })
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {"采药人阿芷": {"room_id": "mistwood_trail", "item": "草药"}}
        manager.caravan_config = {"测试商队": {"route": ["别处", "mistwood_trail"], "gold": 100,
                                               "capacity": 6, "sale_prices": {}}}
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 4)
        self.assertEqual(manager.state.caravans["测试商队"]["inventory"].get("草药", 0), 0)
        self.assertLessEqual(manager.state.npc_gold["采药人阿芷"], MAX_WALLET)

    def test_town_purchase_does_not_overflow_caravan_wallet(self):
        manager = EconomyManager({
            "caravans": {"测试商队": {"position": 0, "gold": MAX_WALLET - 1, "capacity": 6,
                                       "inventory": {"木材": 2}, "visits": 0}},
            "town_gold": 100,
        })
        manager.resources = {}
        manager.gatherers = {}
        manager.recipes = {}
        manager.caravan_config = {"测试商队": {"route": ["别处", "guiyun_south_gate"], "gold": 100,
                                               "capacity": 6, "sale_prices": {"木材": 5}}}
        manager.update(1)
        self.assertEqual(manager.state.caravans["测试商队"]["inventory"].get("木材", 0), 2)
        self.assertEqual(manager.state.caravans["测试商队"]["gold"], MAX_WALLET - 1)
        self.assertEqual(manager.state.town_gold, 100)

    def test_real_world_loop_moves_wood_from_gatherer_to_carpenter_to_caravan(self):
        manager = EconomyManager()
        manager.update(500)
        state = manager.export_state()
        self.assertIn("木匠老许", state["npc_inventory"])
        # 商税会将商户周转银两转入城镇资金池，钱包余额不再是收入高低的稳定指标；
        # 改用真实采购记录验证樵夫→木匠这一段循环。
        self.assertGreater(state["npc_gold"].get("樵夫老周", 0), 0)
        self.assertGreater(state["npc_gold"].get("木匠老许", 0), 0)
        caravan = state["caravans"].get("村镇行商", {})
        # 真实循环中成品进入商队货舱后还可能继续卖到城镇；用活动记录验证采购，而非要求期末货舱必须留货。
        activities = state.get("events", {}).get("world_activity", [])
        self.assertTrue(any(row.get("actor") == "木匠老许" and row.get("action") == "采购原料"
                            and row.get("item") == "木材" and int(row.get("amount", 0)) > 0
                            for row in activities))
        self.assertTrue(any(row.get("actor") == "村镇行商" and row.get("action") == "采购成品"
                            and row.get("item") == "木剑" and int(row.get("amount", 0)) > 0
                            for row in activities))
        self.assertLessEqual(sum(max(0, int(v)) for v in caravan.get("inventory", {}).values()),
                             int(caravan.get("capacity", 0)))
        self.assertGreater(state["market"].get("木剑", {}).get("traded", 0), 0)

    def test_malformed_base_price_fails_safely(self):
        player = DummyPlayer({"market": {"木材": {"supply": 20}}})
        self.assertEqual(TradeService.market_price(player, "木材", "价格不明", "buy"), 0)

    def test_default_economy_remains_bounded_through_long_run_and_restore(self):
        manager = EconomyManager()
        manager.update(1200)
        state = manager.export_state()
        self.assertTrue(all(0 <= int(value) <= MAX_WALLET for value in state["npc_gold"].values()))
        self.assertLessEqual(int(state["town_gold"]), MAX_WALLET)
        for caravan_id, caravan in state["caravans"].items():
            self.assertGreaterEqual(int(caravan.get("gold", 0)), 0, caravan_id)
            self.assertLessEqual(int(caravan.get("gold", 0)), MAX_WALLET, caravan_id)
            self.assertLessEqual(sum(max(0, int(value)) for value in caravan.get("inventory", {}).values()),
                                 int(caravan.get("capacity", 0)), caravan_id)
        for npc_id, inventory in state["npc_inventory"].items():
            for item, quantity in inventory.items():
                self.assertGreaterEqual(int(quantity), 0, (npc_id, item))
                self.assertLessEqual(int(quantity), 9999, (npc_id, item))
        restored = EconomyManager(state)
        restored.update(100)
        self.assertEqual(restored.state.tick, 1300)
        self.assertTrue(all(0 <= int(value) <= MAX_WALLET for value in restored.state.npc_gold.values()))


if __name__ == "__main__":
    unittest.main()
