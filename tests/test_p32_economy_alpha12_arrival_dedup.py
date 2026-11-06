import unittest
from economy import EconomyManager


class Alpha12ArrivalDedupTests(unittest.TestCase):
    def test_route_and_schedule_same_tick_emit_only_one_travel_message(self):
        manager = EconomyManager({})
        manager.caravan_config = {
            "测试商队": {
                "route": ["ordinary_stop", "village_square"],
                "appearances": [{"room": "village_square", "interval": 1}],
                "gold": 10,
                "inventory": {},
            }
        }
        manager.update(1)
        pending = manager.state.events["pending_world_announcements"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0], "【商旅消息】测试商队带来沿途货物，正在村中广场停留。")
        self.assertEqual(manager.state.events["caravan_last_arrival_tick"]["测试商队:village_square"], 1)

    def test_caravan_stays_three_world_ticks_then_expires(self):
        manager = EconomyManager({})
        manager.caravan_config = {
            "测试商队": {
                "route": ["ordinary_stop", "second_stop"],
                "appearances": [{"room": "village_square", "interval": 1}],
                "gold": 10,
                "inventory": {},
            }
        }
        manager.update(1)
        manager.caravan_config["测试商队"]["appearances"] = []
        active = manager.state.events["active_caravans"]["测试商队:village_square"]
        self.assertEqual(active["until_tick"], 4)
        manager.update(2)
        self.assertIn("测试商队:village_square", manager.state.events["active_caravans"])
        manager.update(1)
        self.assertNotIn("测试商队:village_square", manager.state.events["active_caravans"])

    def test_arrival_dedup_survives_export_and_restore(self):
        manager = EconomyManager({})
        manager.caravan_config = {
            "测试商队": {
                "route": ["ordinary_stop", "second_stop"],
                "appearances": [{"room": "guiyun_central_square", "interval": 1}],
                "gold": 10,
                "inventory": {},
            }
        }
        manager.update(1)
        state = manager.export_state()
        restored = EconomyManager(state)
        self.assertEqual(restored.state.events["caravan_last_arrival_tick"]["测试商队:guiyun_central_square"], 1)
        self.assertEqual(len(restored.state.events["pending_world_announcements"]), len(state["events"]["pending_world_announcements"]))


if __name__ == "__main__":
    unittest.main()
