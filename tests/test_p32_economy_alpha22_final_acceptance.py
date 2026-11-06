import unittest
from economy import EconomyManager


class Alpha22FinalAcceptanceTests(unittest.TestCase):
    def test_long_run_world_announcements_remain_bounded(self):
        manager = EconomyManager()
        manager.update(10_000)
        events = manager.export_state()["events"]
        pending = events.get("pending_world_announcements", [])
        self.assertLessEqual(len(pending), 100)
        self.assertTrue(all(isinstance(message, str) and message.strip() for message in pending))
        self.assertEqual(manager.state.tick, 10_000)

    def test_arrival_deduplication_still_works_with_bounded_queue(self):
        manager = EconomyManager()
        manager.caravan_config = {
            "测试商队": {
                "route": ["guiyun_central_square", "village_square"],
                "appearances": [{"room": "village_square", "interval": 1}],
                "capacity": 8,
                "gold": 100,
                "inventory": {},
            }
        }
        manager.gatherers = {}
        manager.update(1)
        pending = manager.state.events["pending_world_announcements"]
        self.assertLessEqual(len(pending), 3)
        self.assertTrue(any("测试商队" in message for message in pending))

    def test_mining_and_logging_resource_caps_survive_long_run(self):
        manager = EconomyManager()
        self.assertTrue(manager.mine("abandoned_iron_mine", 3)[0])
        self.assertTrue(manager.chop("mistwood_trail", 3)[0])
        manager.update(10_000)
        state = manager.export_state()
        self.assertLessEqual(state["resources"]["abandoned_iron_mine"]["remaining"], 24)
        self.assertLessEqual(state["resources"]["mistwood_trail"]["remaining"], 30)
        self.assertGreaterEqual(state["resources"]["abandoned_iron_mine"]["remaining"], 0)
        self.assertGreaterEqual(state["resources"]["mistwood_trail"]["remaining"], 0)


if __name__ == "__main__":
    unittest.main()
