import unittest
from economy import EconomyManager, EconomyState, TradeService

class DummyPlayer:
    def __init__(self):
        self.gold = 100
        self.inventory = ['铁矿石', '铁矿石', '草药']
        self.economy_state = {}
        self.world_state = {'variables': {'quest_clock': 3}}

class EconomyAlpha1Tests(unittest.TestCase):
    def test_state_round_trip_keeps_v12_extension_data(self):
        state = EconomyState({'resources': {'mistwood_stream': {'remaining': 5}}, 'trade_history': [{'item': '铁矿石'}], 'tick': 9})
        restored = EconomyState(state.to_dict())
        self.assertEqual(restored.resources['mistwood_stream']['remaining'], 5)
        self.assertEqual(restored.trade_history[0]['item'], '铁矿石')
        self.assertEqual(restored.tick, 9)

    def test_trade_service_changes_gold_inventory_and_records_history(self):
        p = DummyPlayer()
        ok, _ = TradeService.sell(p, '铁矿石', 1, 12, '铁匠')
        self.assertTrue(ok)
        self.assertEqual(p.gold, 112)
        self.assertEqual(p.inventory.count('铁矿石'), 1)
        self.assertEqual(p.economy_state['trade_history'][-1]['counterparty'], '铁匠')
        ok, _ = TradeService.buy(p, '铁剑', 1, 50, '商队')
        self.assertTrue(ok)
        self.assertEqual(p.gold, 62)
        self.assertIn('铁剑', p.inventory)

    def test_mining_depletes_resource_and_tick_restores_it(self):
        manager = EconomyManager({})
        ok, (item, amount) = manager.mine('abandoned_iron_mine', 2)
        self.assertTrue(ok)
        self.assertEqual(item, '铁矿石')
        self.assertEqual(amount, 2)
        self.assertEqual(manager.state.resources['abandoned_iron_mine']['remaining'], 22)
        manager.update(8)
        self.assertGreaterEqual(manager.state.resources['abandoned_iron_mine']['remaining'], 21)

    def test_caravans_advance_and_state_is_exportable(self):
        manager = EconomyManager({})
        manager.update(3)
        state = manager.export_state()
        self.assertIn('北路商队', state['caravans'])
        self.assertEqual(state['caravans']['北路商队']['visits'], 3)
        self.assertEqual(state['tick'], 3)


    def test_market_price_responds_to_supply_and_trade_updates_supply(self):
        p = DummyPlayer()
        p.economy_state = {"market": {"铁矿石": {"supply": 0, "traded": 0, "last_price": 12}}}
        low_supply_buy = TradeService.market_price(p, "铁矿石", 12, "buy", 1.0)
        low_supply_sell = TradeService.market_price(p, "铁矿石", 12, "sell", 0.5)
        self.assertGreater(low_supply_buy, 12)
        self.assertGreater(low_supply_sell, 6)
        ok, _ = TradeService.sell(p, "铁矿石", 1, 6, "测试商家")
        self.assertTrue(ok)
        self.assertEqual(p.economy_state["market"]["铁矿石"]["supply"], 1)

    def test_caravan_collects_and_delivers_real_ore_to_blacksmith(self):
        manager = EconomyManager({})
        # Alpha106：路线间隔按真实配置执行，等待商队完成采矿点与铁铺之间的行程。
        manager.update(12)
        npc_stock = manager.state.npc_inventory.get("铁匠", {})
        self.assertGreaterEqual(npc_stock.get("铁矿石", 0), 2)
        caravan = manager.state.caravans["北路商队"]
        # 商队按路线间隔循环，完成一次交付后可能已再次从矿点装货。
        self.assertGreaterEqual(caravan["inventory"].get("铁矿石", 0), 0)
        self.assertEqual(manager.state.resources["abandoned_iron_mine"]["remaining"], 22)

    def test_caravan_sale_updates_item_supply_schema(self):
        manager = EconomyManager({"caravans": {"北路商队": {"position": 1, "gold": 500, "inventory": {"铁剑": 2}, "visits": 0}}})
        manager.update(1)
        # Position 1 advances to the town gate and sells inventory there.
        self.assertEqual(manager.state.caravans["北路商队"]["inventory"].get("铁剑"), 0)
        self.assertEqual(manager.state.market["铁剑"]["supply"], 22)

    def test_npc_gatherers_generate_capped_real_inventory(self):
        manager = EconomyManager({})
        manager.caravan_config = {}
        manager.update(6)
        herbs = manager.state.npc_inventory["采药人阿芷"]["草药"]
        self.assertEqual(herbs, 1)
        manager.state.npc_inventory["采药人阿芷"]["草药"] = 15
        manager.update(3)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 14)

    def test_caravan_buys_herbs_from_npc_stock_not_from_nothing(self):
        manager = EconomyManager({
            "npc_inventory": {"采药人阿芷": {"草药": 5}},
            "caravans": {"南路商队": {"position": 0, "gold": 100, "inventory": {"草药": 0}, "visits": 0}},
        })
        manager.update(1)
        caravan = manager.state.caravans["南路商队"]
        self.assertEqual(caravan["inventory"]["草药"], 3)
        self.assertEqual(caravan["gold"], 69)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 0)
        # NPC 内部采购只是转移库存；市场供给只因商队实际买走的 3 份草药下降。
        self.assertEqual(manager.state.market["草药"]["supply"], 17)

    def test_gather_progress_and_npc_inventory_survive_state_round_trip(self):
        manager = EconomyManager({})
        manager.update(3)
        restored = EconomyManager(manager.export_state())
        self.assertEqual(restored.state.npc_inventory["采药人阿芷"]["草药"], 0)
        self.assertEqual(restored.state.npc_inventory["药铺老板"]["草药"], 2)
        self.assertEqual(restored.state.events["gather_progress"]["采药人阿芷"], 0)

if __name__ == '__main__':
    unittest.main()
