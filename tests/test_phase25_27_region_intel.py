import contextlib
import io
import json
import os
import unittest

import actions
import engine
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)

class Phase25To27RegionIntelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rooms = load("rooms.json")
        cls.events = load("world_events.json")
        cls.npcs = load("npcs.json")
        cls.items = load("items.json")

    def player_at(self, zone):
        p = Player("区域情报验收", "散人")
        p.location = next(rid for rid, info in self.rooms.items() if info.get("zone") == zone)
        return p

    def test_region_query_accepts_chinese_name_and_lists_branch_event(self):
        p = self.player_at("guiyun_city")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            actions.handle_region_ecology(p, ["归云城"])
        text = out.getvalue()
        self.assertIn("区域局势：归云城", text)
        self.assertIn("安全度：", text)
        self.assertIn("三地商路账册会审", text)

    def test_all_regions_query_does_not_claim_remote_events_are_currently_available(self):
        p = self.player_at("main")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            actions.handle_region_ecology(p, ["全部"])
        text = out.getvalue()
        self.assertIn("区域局势：归云城", text)
        self.assertIn("需前往该区域核查", text)

    def test_three_region_event_requires_both_case_chains_and_is_once_only(self):
        p = self.player_at("guiyun_city")
        event_id = "three_region_trade_audit"
        self.assertIn(event_id, self.events)
        info = self.events[event_id]
        self.assertEqual(info["region"], "guiyun_city")
        for entry in info["effects"]["npc_information"]:
            self.assertIn(entry["npc"], self.npcs)
        self.assertIn(info["rewards"]["item"], self.items)
        self.assertFalse(p.can_trigger_world_event(event_id))
        p.set_flag("quest:sunken_caravan:resolved", True)
        self.assertFalse(p.can_trigger_world_event(event_id))
        p.set_flag("quest:northfront_missing_cargo:resolved", True)
        self.assertTrue(p.can_trigger_world_event(event_id))
        before = p.gold
        ok, message, result = p.trigger_world_event(event_id)
        self.assertTrue(ok, message)
        self.assertTrue(p.get_flag("world:trade_network:three_region_audited"))
        self.assertGreaterEqual(p.gold, before + info["rewards"]["gold"])
        ok_again, _, _ = p.trigger_world_event(event_id)
        self.assertFalse(ok_again)
        self.assertEqual(p.get_world_event_state(event_id).get("count"), 1)

    def test_old_v12_state_can_use_cross_region_event_without_new_top_level_fields(self):
        p = self.player_at("guiyun_city")
        self.assertEqual(engine.SAVE_VERSION, 12)
        p.world_state.setdefault("variables", {}).pop("world_events", None)
        p.set_flag("quest:sunken_caravan:resolved", True)
        p.set_flag("quest:northfront_missing_cargo:resolved", True)
        self.assertTrue(p.can_trigger_world_event("three_region_trade_audit"))
        self.assertNotIn("world_events", p.world_state)

if __name__ == "__main__":
    unittest.main()
