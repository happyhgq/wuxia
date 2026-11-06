import json, os, unittest
from economy import EconomyManager, TradeService
BASE=os.path.dirname(os.path.dirname(__file__))
class DummyPlayer:
    def __init__(self):
        self.gold=500; self.inventory=['雾露草']*2; self.economy_state={}; self.world_state={'variables':{'quest_clock':0}}
class Alpha15LongSimulationTests(unittest.TestCase):
    def test_gatherer_is_real_npc_at_real_room_and_tradeable(self):
        with open(os.path.join(BASE,'data','economy','gatherers.json'),encoding='utf-8') as f: cfg=json.load(f)
        with open(os.path.join(BASE,'data','npcs.json'),encoding='utf-8') as f: npcs=json.load(f)
        with open(os.path.join(BASE,'data','rooms.json'),encoding='utf-8') as f: rooms=json.load(f)
        self.assertIn('守祠残僧',npcs); self.assertIn('雾露草',npcs['守祠残僧']['shop'])
        self.assertIn('守祠残僧',rooms[cfg['守祠残僧']['room_id']]['npcs'])
        manager=EconomyManager({'npc_gold':{'守祠残僧':500}}); manager.caravan_config={}; manager.update(8)
        self.assertEqual(manager.state.npc_inventory['守祠残僧']['雾露草'],2)
        player=DummyPlayer(); player.economy_state=manager.export_state()
        ok,msg=TradeService.sell(player,'雾露草',2,4,'守祠残僧'); self.assertTrue(ok,msg)
        self.assertEqual(player.economy_state['npc_inventory']['守祠残僧']['雾露草'],4)
        ok,msg=TradeService.buy(player,'雾露草',1,8,'守祠残僧'); self.assertTrue(ok,msg)
        self.assertEqual(player.economy_state['npc_inventory']['守祠残僧']['雾露草'],3)
    def test_thousand_tick_simulation_keeps_economy_bounded_and_nonnegative(self):
        manager=EconomyManager({'resources':{'abandoned_iron_mine':{'remaining':20,'last_tick':0}},'npc_inventory':{'铁匠':{'铁矿石':10,'铁剑':0},'百炼铁铺铁匠':{'铁矿石':10,'铁剑':0}},'npc_gold':{'铁匠':1000,'百炼铁铺铁匠':1000,'采药人阿芷':500,'守祠残僧':500}})
        manager.update(1000)
        self.assertEqual(manager.state.tick,1000)
        self.assertLessEqual(manager.state.npc_inventory['采药人阿芷']['草药'],16)
        self.assertLessEqual(manager.state.npc_inventory['守祠残僧']['雾露草'],8)
        self.assertLessEqual(manager.state.npc_inventory['铁匠']['铁剑'],8)
        self.assertLessEqual(manager.state.npc_inventory['百炼铁铺铁匠']['铁剑'],8)
        for stock in manager.state.npc_inventory.values():
            for count in stock.values(): self.assertGreaterEqual(int(count),0)
        for caravan in manager.state.caravans.values():
            self.assertGreaterEqual(caravan['gold'],0)
            self.assertTrue(all(int(v)>=0 for v in caravan['inventory'].values()))
        self.assertGreaterEqual(manager.state.town_gold,0)
if __name__=='__main__': unittest.main()
