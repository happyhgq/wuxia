import contextlib
import io
import json
import os
import tempfile
import unittest

import engine
from player import Player

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")


def load_data(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as handle:
        return json.load(handle)


class Phase37To39StoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quests = load_data("quests.json")
        cls.events = load_data("world_events.json")
        cls.npcs = load_data("npcs.json")
        cls.items = load_data("items.json")

    def test_mistwood_quest_unlocks_northfront_followup_event(self):
        quest = self.quests["雾隐失药案"]
        event_id = "mistwood_herb_supply_northbound"
        event = self.events[event_id]
        self.assertIn("quest:mistwood_herbs:resolved", quest["on_complete"]["set_flags"])
        self.assertIn("quest:mistwood_herbs:resolved", event["requires"]["flags"])
        self.assertEqual(event["region"], "northfront_town")
        self.assertIn(event["rewards"]["item"], self.items)
        for npc in event["rewards"].get("relations", {}):
            self.assertIn(npc, self.npcs)
        for entry in event["effects"].get("npc_information", []):
            self.assertIn(entry["npc"], self.npcs)

        p = Player("药材线索验收", "散人")
        p.location = "northfront_street"
        self.assertFalse(p.can_trigger_world_event(event_id), "未完成前置任务不得触发后续事件")
        p.set_flag("quest:mistwood_herbs:resolved", True)
        self.assertTrue(p.can_trigger_world_event(event_id))
        start_gold = p.gold
        ok, message, result = p.trigger_world_event(event_id)
        self.assertTrue(ok, message)
        self.assertIsNotNone(result)
        self.assertEqual(p.gold, start_gold + event["rewards"]["gold"])
        self.assertTrue(p.get_flag("world:northfront:mistwood_supply_delivered"))
        self.assertFalse(p.can_trigger_world_event(event_id), "一次性事件完成后不得重复触发")
        gold_after = p.gold
        ok_again, _, _ = p.trigger_world_event(event_id)
        self.assertFalse(ok_again)
        self.assertEqual(p.gold, gold_after)

    def test_followup_event_is_region_locked(self):
        p = Player("区域锁定验收", "散人")
        p.location = "mistwood_trail"
        p.set_flag("quest:mistwood_herbs:resolved", True)
        self.assertFalse(p.can_trigger_world_event("mistwood_herb_supply_northbound"))
        p.location = "northfront_street"
        self.assertTrue(p.can_trigger_world_event("mistwood_herb_supply_northbound"))

    def test_followup_event_state_survives_v12_save_round_trip(self):
        self.assertEqual(engine.SAVE_VERSION, 12)
        p = Player("事件存档验收", "散人")
        p.location = "northfront_street"
        p.set_flag("quest:mistwood_herbs:resolved", True)
        ok, message, _ = p.trigger_world_event("mistwood_herb_supply_northbound")
        self.assertTrue(ok, message)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "save.json")
            p.save_to_file(path)
            with contextlib.redirect_stdout(io.StringIO()):
                loaded = Player.load_from_file(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.get_world_event_state("mistwood_herb_supply_northbound").get("count"), 1)
            self.assertTrue(loaded.get_flag("world:northfront:mistwood_supply_delivered"))
            self.assertFalse(loaded.can_trigger_world_event("mistwood_herb_supply_northbound"))
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            self.assertEqual(raw.get("version"), 12)
            self.assertNotIn("world_events", raw)


    def test_three_region_transfer_chain_requires_both_prior_outcomes(self):
        event_id = "guiyun_trade_transfer_chain_trace"
        event = self.events[event_id]
        self.assertEqual(event["region"], "guiyun_city")
        self.assertIn("world:trade_network:three_region_audited", event["requires"]["flags"])
        self.assertIn("world:northfront:mistwood_supply_delivered", event["requires"]["flags"])
        self.assertIn(event["rewards"]["item"], self.items)
        for entry in event["effects"]["npc_information"]:
            self.assertIn(entry["npc"], self.npcs)

        p = Player("三地转运链验收", "散人")
        p.location = "guiyun_yamen_hall"
        p.set_flag("world:trade_network:three_region_audited", True)
        self.assertFalse(p.can_trigger_world_event(event_id), "缺少雾林药材交付结果时不得解锁")
        p.set_flag("world:northfront:mistwood_supply_delivered", True)
        self.assertTrue(p.can_trigger_world_event(event_id))
        start_gold = p.gold
        ok, message, _ = p.trigger_world_event(event_id)
        self.assertTrue(ok, message)
        self.assertEqual(p.gold, start_gold + event["rewards"]["gold"])
        self.assertTrue(p.get_flag("world:trade_network:transfer_chain_traced"))
        self.assertTrue(p.get_flag("world:trade_network:followup_open"))
        self.assertEqual(p.get_var("trade_network:transfer_chain_evidence"), 1)
        self.assertFalse(p.can_trigger_world_event(event_id))
        gold_after = p.gold
        ok_again, _, _ = p.trigger_world_event(event_id)
        self.assertFalse(ok_again)
        self.assertEqual(p.gold, gold_after)

    def test_three_region_transfer_chain_save_load_keeps_evidence_and_one_time_state(self):
        p = Player("转运链存档验收", "散人")
        p.location = "guiyun_yamen_hall"
        p.set_flag("world:trade_network:three_region_audited", True)
        p.set_flag("world:northfront:mistwood_supply_delivered", True)
        ok, message, _ = p.trigger_world_event("guiyun_trade_transfer_chain_trace")
        self.assertTrue(ok, message)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "save.json")
            p.save_to_file(path)
            with contextlib.redirect_stdout(io.StringIO()):
                loaded = Player.load_from_file(path)
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.get_flag("world:trade_network:transfer_chain_traced"))
            self.assertEqual(loaded.get_var("trade_network:transfer_chain_evidence"), 1)
            self.assertEqual(loaded.get_world_event_state("guiyun_trade_transfer_chain_trace").get("count"), 1)
            self.assertFalse(loaded.can_trigger_world_event("guiyun_trade_transfer_chain_trace"))
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            self.assertEqual(raw.get("version"), 12)
            self.assertNotIn("world_events", raw)


if __name__ == "__main__":
    unittest.main()
