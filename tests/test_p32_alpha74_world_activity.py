"""Alpha74：NPC 世界活动记录必须对应真实资源、库存与交易变化。"""
import unittest
from economy import EconomyManager


class Alpha74WorldActivityTests(unittest.TestCase):
    def test_long_run_records_real_gathering_production_and_trade(self):
        manager = EconomyManager()
        manager.update(360)
        rows = manager.recent_world_activity(100)
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 100)
        kinds = {row.get("kind") for row in rows}
        self.assertIn("采集", kinds)
        self.assertIn("制作", kinds)
        self.assertIn("交易", kinds)
        for row in rows:
            self.assertGreater(int(row.get("tick", -1)), 0)
            self.assertGreater(int(row.get("amount", 0)), 0)
            self.assertTrue(row.get("actor"))
            self.assertTrue(row.get("item"))
            self.assertNotIn("confrontation", str(row))

    def test_activity_history_is_bounded_after_very_long_run(self):
        manager = EconomyManager()
        manager.update(1200)
        rows = manager.state.events.get("world_activity", [])
        self.assertLessEqual(len(rows), 100)
        self.assertEqual(len(manager.recent_world_activity(1000)), len(rows))

    def test_activity_history_survives_export_and_reload(self):
        manager = EconomyManager()
        manager.update(120)
        before = manager.recent_world_activity(10)
        self.assertTrue(before)
        reloaded = EconomyManager(manager.export_state())
        self.assertEqual(reloaded.recent_world_activity(10), before)
        reloaded.update(30)
        self.assertGreaterEqual(reloaded.state.tick, 150)

    def test_invalid_legacy_activity_shape_is_repaired(self):
        manager = EconomyManager({"events": {"world_activity": "broken"}})
        manager.update(20)
        self.assertIsInstance(manager.state.events.get("world_activity"), list)
        self.assertLessEqual(len(manager.recent_world_activity(100)), 100)

    def test_activity_query_returns_copies_and_respects_limit(self):
        manager = EconomyManager()
        manager.update(100)
        rows = manager.recent_world_activity(3)
        self.assertLessEqual(len(rows), 3)
        if rows:
            rows[0]["actor"] = "外部修改"
            self.assertNotEqual(manager.recent_world_activity(3)[0].get("actor"), "外部修改")


if __name__ == "__main__":
    unittest.main()
