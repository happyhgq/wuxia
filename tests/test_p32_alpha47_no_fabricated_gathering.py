"""Cross-system safety: NPC gathering cannot create goods without a matching finite resource pool."""
import unittest
from economy import EconomyManager


class Alpha47NoFabricatedGatheringTests(unittest.TestCase):
    def _manager(self, resource_cfg, resource_room_id="source", item="草药"):
        manager = EconomyManager({})
        manager.resources = {resource_room_id: resource_cfg} if resource_cfg is not None else {}
        manager.gatherers = {
            "采集者": {
                "room_id": "room", "resource_room_id": resource_room_id,
                "item": item, "interval": 1, "amount": 3, "capacity": 10,
            }
        }
        manager.recipes = {}
        manager.caravan_config = {}
        return manager

    def test_missing_resource_reference_does_not_generate_inventory(self):
        manager = self._manager(None)
        manager.update(5)
        self.assertEqual(manager.state.npc_inventory.get("采集者", {}).get("草药", 0), 0)

    def test_item_mismatch_does_not_consume_other_resource_or_create_goods(self):
        manager = self._manager({"item": "铁矿石", "capacity": 8, "regen_interval": 5, "regen_amount": 2})
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory.get("采集者", {}).get("草药", 0), 0)
        self.assertEqual(manager.state.resources.get("source", {}).get("remaining", 8), 8)

    def test_matching_resource_is_consumed_and_stock_stays_within_capacity(self):
        manager = self._manager({"item": "草药", "action": "gather", "capacity": 2, "regen_interval": 5, "regen_amount": 1})
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 2)
        self.assertEqual(manager.state.resources["source"]["remaining"], 0)

    def test_matching_item_but_wrong_action_does_not_allow_gathering(self):
        manager = self._manager({"item": "草药", "action": "chop", "capacity": 8, "regen_interval": 5, "regen_amount": 2})
        manager.update(3)
        self.assertEqual(manager.state.npc_inventory.get("采集者", {}).get("草药", 0), 0)
        self.assertEqual(manager.state.resources.get("source", {}).get("remaining", 8), 8)

    def test_woodcutter_only_uses_a_chop_resource_node(self):
        manager = self._manager({"item": "木材", "action": "gather", "capacity": 8, "regen_interval": 5, "regen_amount": 2}, item="木材")
        manager.update(3)
        self.assertEqual(manager.state.npc_inventory.get("采集者", {}).get("木材", 0), 0)


if __name__ == "__main__":
    unittest.main()
