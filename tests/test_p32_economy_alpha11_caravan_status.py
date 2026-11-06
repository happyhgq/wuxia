import contextlib
import io
import os
import unittest

import engine
import main

BASE = os.path.dirname(os.path.dirname(__file__))


class DummyPlayer:
    def __init__(self, location='village_square', economy_state=None):
        self.location = location
        self.economy_state = economy_state or {}


class Alpha11CaravanStatusTests(unittest.TestCase):
    def test_command_aliases_and_dispatch_registration(self):
        self.assertEqual(main.parse_command('商队'), ('caravan', []))
        self.assertEqual(main.parse_command('商路'), ('caravan', []))
        self.assertTrue(main.command_will_be_handled('caravan', {}))

    def test_status_displays_active_caravan_and_next_schedules_in_chinese(self):
        player = DummyPlayer('village_square', {
            'tick': 10,
            'events': {
                'active_caravans': {'北路商队:village_square': {'name': '北路商队', 'room': 'village_square', 'until_tick': 12}},
                'caravan_appearance_progress': {'北路商队:village_square': 4},
                'caravan_global_schedule': {'next_tick': 18, 'last_room': 'village_square', 'last_caravan': '北路商队'},
            },
        })
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main.show_caravan_status(player)
        rendered = output.getvalue()
        self.assertIn('北路商队正在此地停留', rendered)
        self.assertIn('村中广场', rendered)
        self.assertIn('天衡广场', rendered)
        self.assertNotIn('village_square', rendered)
        self.assertNotIn('guiyun_central_square', rendered)
        self.assertIn('预计还需 8 个世界时刻到场', rendered)
        self.assertIn('共用商旅日程', rendered)
        self.assertNotIn('下一次预计在', rendered)


    def test_status_hides_expired_caravans_using_scene_and_trade_expiry_boundary(self):
        player = DummyPlayer('village_square', {
            'tick': 20,
            'events': {
                'active_caravans': {
                    '已离场商队:village_square': {'name': '已离场商队', 'room': 'village_square', 'until_tick': 20},
                    '仍在停留商队:village_square': {'name': '仍在停留商队', 'room': 'village_square', 'until_tick': 21},
                },
                'caravan_global_schedule': {'next_tick': 30},
            },
        })
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main.show_caravan_status(player)
        rendered = output.getvalue()
        self.assertNotIn('已离场商队正在此地停留', rendered)
        self.assertIn('仍在停留商队正在此地停留', rendered)
        self.assertIn('预计还停留 1 个世界时刻', rendered)

    def test_status_does_not_invent_independent_arrival_times_from_legacy_config(self):
        player = DummyPlayer('nowhere', {
            'tick': 100,
            'events': {
                'caravan_appearance_progress': {
                    '村镇行商:village_square': 20,
                    '南路商队:guiyun_central_square': 15,
                },
            },
        })
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main.show_caravan_status(player)
        rendered = output.getvalue()
        self.assertIn('全局商旅日程尚未建立', rendered)
        self.assertIn('共用商旅日程', rendered)
        self.assertNotIn('村镇行商：下一次预计在', rendered)
        self.assertNotIn('南路商队：下一次预计在', rendered)

    def test_status_handles_corrupt_economy_state(self):
        player = DummyPlayer('nowhere', {'events': 'broken', 'caravans': None})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main.show_caravan_status(player)
        self.assertIn('商队与商路动态', output.getvalue())


if __name__ == '__main__':
    unittest.main()
