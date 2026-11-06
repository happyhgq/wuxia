"""Alpha54: real economy config must connect NPC gathering to finite resource nodes."""
import json
import os
import unittest
from economy import EconomyManager

BASE = os.path.dirname(os.path.dirname(__file__))


class Alpha54EconomyResourceLinkageTests(unittest.TestCase):
    def _config(self, name):
        with open(os.path.join(BASE, "data", "economy", name), encoding="utf-8") as handle:
            return json.load(handle)

    def test_every_gatherer_has_a_matching_resource_action_and_item(self):
        resources = self._config("resources.json")
        gatherers = self._config("gatherers.json")
        inferred = {"木材": "chop", "铁矿石": "mine"}
        for npc_id, cfg in gatherers.items():
            with self.subTest(npc=npc_id):
                resource = resources[cfg["resource_room_id"]]
                self.assertEqual(resource["item"], cfg["item"])
                self.assertEqual(resource.get("action", inferred.get(resource["item"], "mine")), cfg["action"])

    def test_real_woodcutter_consumes_mistwood_resource(self):
        manager = EconomyManager({})
        # 隔离商队的采集行为，确认樵夫自身也会消耗同一资源点。
        manager.caravan_config = {}
        manager.update(4)
        state = manager.export_state()
        self.assertEqual(state["resources"]["mistwood_trail"]["remaining"], 28)
        self.assertEqual(state["npc_inventory"]["樵夫老周"]["木材"], 2)

    def test_resource_and_production_loop_survives_save_reload(self):
        manager = EconomyManager({})
        manager.update(100)
        before = manager.export_state()
        resumed = EconomyManager(before)
        resumed.update(100)
        state = resumed.export_state()
        self.assertEqual(state["tick"], 200)
        self.assertLessEqual(state["resources"]["mistwood_trail"]["remaining"], 30)
        self.assertGreaterEqual(state["resources"]["mistwood_trail"]["remaining"], 0)
        self.assertLessEqual(state["npc_inventory"]["樵夫老周"].get("木材", 0), 16)
        self.assertLessEqual(state["npc_inventory"]["木匠老许"].get("木剑", 0), 8)
        self.assertLessEqual(state["npc_inventory"]["百炼铁铺铁匠"].get("铁剑", 0), 8)
        self.assertLessEqual(state["npc_inventory"]["药铺老板"].get("疗伤药", 0), 12)


if __name__ == "__main__":
    unittest.main()
