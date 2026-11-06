"""Alpha76：交谈可反映已发生的真实营生，不制造虚假交易。"""
import unittest
from actions import _npc_economy_context


class Alpha76NpcEconomyDialogueTests(unittest.TestCase):
    def test_matching_npc_gets_grounded_recent_activity(self):
        state = {"events": {"world_activity": [{
            "tick": 42, "kind": "采集", "actor": "采药人阿芷", "action": "采集",
            "item": "草药", "amount": 2, "room_id": "mistwood_trail", "detail": "库存增加"
        }]}}
        text = _npc_economy_context("采药人阿芷", state, "mistwood_trail")
        self.assertIn("采集了2份草药", text)
        self.assertNotIn("world_activity", text)

    def test_same_room_can_surface_recent_world_activity(self):
        state = {"events": {"world_activity": [{
            "actor": "商队伙计", "action": "采购", "item": "木材", "amount": 3,
            "room_id": "village_square"
        }]}}
        text = _npc_economy_context("村中商贩", state, "village_square")
        self.assertIn("商队伙计", text)
        self.assertIn("3份木材", text)

    def test_empty_or_malformed_state_is_silent(self):
        self.assertEqual(_npc_economy_context("某人", {}, "room"), "")
        self.assertEqual(_npc_economy_context("某人", {"events": {"world_activity": "broken"}}, "room"), "")

    def test_no_activity_from_unrelated_room_is_not_invented(self):
        state = {"events": {"world_activity": [{
            "actor": "远方樵夫", "action": "伐木", "item": "木材", "amount": 4,
            "room_id": "mistwood_trail"
        }]}}
        self.assertEqual(_npc_economy_context("城中捕头", state, "guiyun_city_gate"), "")


if __name__ == "__main__":
    unittest.main()
