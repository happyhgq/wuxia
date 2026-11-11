"""Alpha59：客栈场景与住宿、用餐、茶饮、风声服务。"""
import contextlib
import io
import json
import os
import unittest
from actions import handle_inn_service, look
from player import Player
from main import CMD_MAP, command_will_be_handled

BASE = os.path.dirname(os.path.dirname(__file__))

class Alpha59InnTests(unittest.TestCase):
    def test_inn_scenes_have_richer_description_and_service_hints(self):
        with open(os.path.join(BASE, 'data', 'rooms.json'), encoding='utf-8') as f:
            rooms = json.load(f)
        for room_id, phrases in {
            'inn': ('后厨', '客房', '行商'),
            'guiyun_yunlai_inn': ('客房', '掌柜', '小二'),
            'guiyun_restaurant_hall': ('热菜香气', '镖师', '消息'),
        }.items():
            for phrase in phrases:
                self.assertIn(phrase, rooms[room_id]['desc'])
        p = Player('客栈测试')
        p.location = 'inn'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            look(p)
        self.assertIn('客栈服务', out.getvalue())
        self.assertIn('听消息', out.getvalue())

    def test_inn_commands_are_recognized(self):
        for command in ('住店', '住宿', '吃饭', '打尖', '喝茶', '听消息'):
            self.assertIn(command, CMD_MAP)
            self.assertTrue(command_will_be_handled(CMD_MAP[command], {}))

    def test_stay_costs_money_and_restores_hp_mp_without_stale_warning(self):
        p = Player('住宿测试')
        p.location = 'inn'
        p.hp, p.mp, p.gold = 20, 5, 50
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_inn_service(p, '住店')
        self.assertEqual((p.hp, p.mp, p.gold), (p.max_hp, p.max_mp, 38))
        self.assertNotIn('不会自动保存', out.getvalue())

    def test_meal_tea_and_rumor_effects_and_insufficient_funds(self):
        p = Player('服务测试')
        p.location = 'guiyun_yunlai_inn'
        p.hp, p.mp, p.gold = 50, 10, 20
        with contextlib.redirect_stdout(io.StringIO()):
            handle_inn_service(p, '吃饭')
        self.assertEqual((p.hp, p.mp, p.gold), (68, 18, 16))
        with contextlib.redirect_stdout(io.StringIO()):
            handle_inn_service(p, '喝茶')
        self.assertEqual((p.mp, p.gold), (30, 14))
        with contextlib.redirect_stdout(io.StringIO()):
            handle_inn_service(p, '听消息')
        self.assertEqual(p.gold, 11)
        self.assertTrue(p.get_player_information())
        p.gold = 0
        hp, mp = p.hp, p.mp
        with contextlib.redirect_stdout(io.StringIO()):
            handle_inn_service(p, '吃饭')
        self.assertEqual((p.hp, p.mp), (hp, mp))

    def test_inn_services_are_not_available_outside_inns(self):
        p = Player('地点测试')
        p.location = 'village_gate'
        p.gold = 50
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_inn_service(p, '住店')
        self.assertEqual(p.gold, 50)
        self.assertIn('没有可供住宿', out.getvalue())

if __name__ == '__main__':
    unittest.main()

class Alpha60InnRumorTests(unittest.TestCase):
    def test_each_inn_has_distinct_local_rumors(self):
        p = Player('风声测试')
        p.gold = 30
        heard = {}
        for room_id in ('inn', 'guiyun_yunlai_inn', 'guiyun_restaurant_hall'):
            p.location = room_id
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                handle_inn_service(p, '听消息')
            heard[room_id] = out.getvalue()
        info = p.get_player_information()
        topics = set(info.keys())
        self.assertTrue(any('青石村风声' in topic for topic in topics))
        self.assertTrue(any('归云城风声' in topic for topic in topics))
        self.assertTrue(any('醉仙楼风声' in topic for topic in topics))
        self.assertEqual(p.gold, 21)

    def test_rumors_rotate_independently_by_inn_and_persist_progress(self):
        p = Player('轮换测试')
        p.location = 'inn'
        p.gold = 30
        outputs = []
        for _ in range(2):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                handle_inn_service(p, '听消息')
            outputs.append(out.getvalue())
        self.assertNotEqual(outputs[0], outputs[1])
        progress = p.world_state['variables']['inn_rumor_progress']
        self.assertEqual(progress['inn'], 2)
        self.assertNotIn('guiyun_yunlai_inn', progress)

    def test_no_money_does_not_advance_rumor_progress(self):
        p = Player('缺钱测试')
        p.location = 'guiyun_restaurant_hall'
        p.gold = 2
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            handle_inn_service(p, '听消息')
        self.assertEqual(p.gold, 2)
        self.assertNotIn('inn_rumor_progress', p.world_state.get('variables', {}))
        self.assertIn('至少要 3 两', out.getvalue())
