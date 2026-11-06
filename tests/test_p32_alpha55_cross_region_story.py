"""Alpha55：隐藏地点线索可推动跨区域世界事件和人物关系变化。"""
import unittest
from player import Player


class Alpha55CrossRegionStoryTests(unittest.TestCase):
    def test_hidden_cache_clue_leads_to_northfront_and_changes_relationships(self):
        player = Player("测试侠客")
        player.location = "sunken_cache"
        player.set_flag("explore:sunken_channel:cache_found", True)
        start_gold = player.gold
        ok, message, _ = player.trigger_world_event("sunken_cache_seal_review")
        self.assertTrue(ok, message)
        self.assertTrue(player.get_flag("world:sunken:old_seal_found"))
        self.assertEqual(player.gold, start_gold + 20)
        self.assertEqual(player.get_relation("万商会会长"), 3)
        self.assertTrue(player.can_trigger_world_event("northfront_old_manifest_review") is False)
        player.location = "northfront_wharf"
        self.assertTrue(player.can_trigger_world_event("northfront_old_manifest_review"))
        ok, message, _ = player.trigger_world_event("northfront_old_manifest_review")
        self.assertTrue(ok, message)
        self.assertTrue(player.get_flag("world:northfront:old_manifest_verified"))
        self.assertEqual(player.get_var("world:northfront:trade_route_recovered", 0), 1)
        self.assertEqual(player.get_relation("北境货栈掌柜"), 6)
        self.assertFalse(player.can_trigger_world_event("northfront_old_manifest_review"))

    def test_old_v12_world_state_without_new_event_flags_remains_valid(self):
        player = Player("旧档测试侠客")
        player.world_state = {"flags": {}, "variables": {"quest_clock": 12}}
        player.location = "sunken_cache"
        self.assertFalse(player.can_trigger_world_event("sunken_cache_seal_review"))
        player.set_flag("explore:sunken_channel:cache_found", True)
        self.assertTrue(player.can_trigger_world_event("sunken_cache_seal_review"))


if __name__ == "__main__":
    unittest.main()
