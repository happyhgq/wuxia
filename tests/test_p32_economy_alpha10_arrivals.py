import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))

class Alpha10CaravanArrivalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE, 'data', 'economy', 'caravans.json'), encoding='utf-8') as f:
            cls.config = json.load(f)
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            cls.rooms = json.load(f)

    def test_both_caravans_have_scheduled_square_stops(self):
        all_stops = {stop['room'] for cfg in self.config.values() for stop in cfg.get('appearances', [])}
        self.assertIn('village_square', all_stops)
        self.assertIn('guiyun_central_square', all_stops)
        self.assertEqual(self.rooms['village_square']['name'], '村中广场')
        self.assertEqual(self.rooms['guiyun_central_square']['name'], '天衡广场')

    def test_arrival_emits_one_concise_travel_message(self):
        manager = EconomyManager({})
        manager.caravan_config = {
            '测试商队': {'route': ['ordinary_stop', 'second_stop'], 'appearances': [{'room': 'village_square', 'interval': 2}], 'gold': 10, 'inventory': {}}
        }
        manager.update(2)
        pending = manager.state.events['pending_world_announcements']
        self.assertEqual(pending, ['【商旅消息】测试商队带来沿途货物，正在村中广场停留。'])
        self.assertEqual(manager.state.events['active_caravans']['测试商队:village_square']['room'], 'village_square')
        self.assertGreaterEqual(manager.state.events['active_caravans']['测试商队:village_square']['until_tick'], manager.state.tick)
        manager.update(1)
        # 没有再次到达广场的 Tick 不得重复广播。
        self.assertEqual(len(manager.state.events['pending_world_announcements']), len(pending))

    def test_mining_command_does_not_force_an_immediate_save(self):
        with open(os.path.join(BASE, 'main.py'), encoding='utf-8') as f:
            source = f.read()
        start = source.index('            elif cmd == "mine":')
        end = source.index('            elif cmd == "search":', start)
        mining_branch = source[start:end]
        self.assertNotIn('player.save_to_file()', mining_branch)
        self.assertIn('输入“保存”存档', mining_branch)

    def test_arrival_queue_can_be_drained_without_affecting_caravan_state(self):
        manager = EconomyManager({})
        manager.caravan_config = {
            '测试商队': {'route': ['ordinary_stop', 'second_stop'], 'appearances': [{'room': 'guiyun_central_square', 'interval': 2}], 'gold': 10, 'inventory': {}}
        }
        manager.update(2)
        state = manager.export_state()
        state['events']['pending_world_announcements'].clear()
        self.assertEqual(state['caravans']['测试商队']['visits'], 2)
        self.assertEqual(state['events']['pending_world_announcements'], [])

if __name__ == '__main__':
    unittest.main()
