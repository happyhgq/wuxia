import unittest
from economy import TradeService

class DummyPlayer:
    def __init__(self):
        self.gold = 100
        self.inventory = ['铁矿石', '铁矿石', '草药']
        self.economy_state = {}
        self.world_state = {'variables': {'quest_clock': 7}}

class EconomyAlpha4Tests(unittest.TestCase):
    def test_player_sale_becomes_real_npc_stock(self):
        p = DummyPlayer(); ok, _ = TradeService.sell(p, '铁矿石', 2, 4, '铁匠')
        self.assertTrue(ok); self.assertEqual(p.economy_state['npc_inventory']['铁匠']['铁矿石'], 2)
        self.assertEqual(p.gold, 108)
    def test_npc_stock_is_consumed_when_player_buys(self):
        p = DummyPlayer(); p.economy_state = {'npc_inventory': {'铁匠': {'铁剑': 2}}}
        ok, _ = TradeService.buy(p, '铁剑', 1, 30, '铁匠')
        self.assertTrue(ok); self.assertEqual(p.economy_state['npc_inventory']['铁匠']['铁剑'], 1)
        self.assertEqual(p.gold, 70)
    def test_npc_cannot_sell_more_than_economic_stock(self):
        p = DummyPlayer(); p.economy_state = {'npc_inventory': {'铁匠': {'铁剑': 1}}}
        before_gold, before_inventory = p.gold, list(p.inventory)
        ok, message = TradeService.buy(p, '铁剑', 2, 30, '铁匠')
        self.assertFalse(ok); self.assertIn('库存不足', message)
        self.assertEqual(p.gold, before_gold); self.assertEqual(p.inventory, before_inventory)
    def test_sell_then_buy_round_trip_preserves_item_accounting(self):
        p = DummyPlayer(); ok, _ = TradeService.sell(p, '草药', 1, 3, '药农')
        self.assertTrue(ok); self.assertEqual(p.economy_state['npc_inventory']['药农']['草药'], 1)
        ok, _ = TradeService.buy(p, '草药', 1, 5, '药农')
        self.assertTrue(ok); self.assertEqual(p.economy_state['npc_inventory']['药农']['草药'], 0)
        self.assertEqual(p.inventory.count('草药'), 1); self.assertEqual(len(p.economy_state['trade_history']), 2)

if __name__ == '__main__': unittest.main()
