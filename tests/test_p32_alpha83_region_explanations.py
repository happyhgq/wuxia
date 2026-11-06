import unittest
from unittest.mock import patch
import actions

class FakePlayer:
    location = "room"
    def get_region_ecology(self, zone=None):
        return {"name":"测试区域", "level":"calm", "security":32, "commerce":38, "travel":48, "danger":"high", "tension":0}
    def list_world_events(self, zone=None): return []

class Alpha83RegionExplanationTests(unittest.TestCase):
    def test_region_report_explains_metrics_as_gameplay_effects(self):
        import io
        from contextlib import redirect_stdout
        p=FakePlayer()
        with patch.object(actions.engine, "WORLD_REGIONS", {"main":{"name":"测试区域","faction_exposure":[]}}), \
             patch.object(actions.engine, "ROOMS", {"room":{"zone":"main"}}), \
             redirect_stdout(io.StringIO()) as out:
            actions.handle_region_ecology(p, [])
        text=out.getvalue()
        self.assertIn("治安偏差", text)
        self.assertIn("商贸往来处于一般水平", text)
        self.assertIn("道路通行条件一般", text)
        self.assertIn("安全度：32/100", text)

if __name__ == '__main__': unittest.main()
