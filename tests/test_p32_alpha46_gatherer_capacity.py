"""Alpha46: NPC gatherer capacity is a hard limit, even when batch size is larger."""
import unittest
from economy import EconomyManager


class Alpha46GathererCapacityTests(unittest.TestCase):
    def make_manager(self, capacity, amount=3):
        manager = EconomyManager({})
        manager.resources = {
            "resource_point": {"action": "gather", "item": "草药", "capacity": 20,
                               "regen_interval": 8, "regen_amount": 2}
        }
        manager.gatherers = {
            "采集者": {"room_id": "room", "resource_room_id": "resource_point",
                       "item": "草药", "interval": 1, "amount": amount,
                       "capacity": capacity}
        }
        manager.recipes = {}
        manager.caravan_config = {}
        return manager

    def test_batch_size_cannot_raise_inventory_capacity(self):
        manager = self.make_manager(capacity=1, amount=3)
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 1)
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 1)

    def test_zero_capacity_prevents_npc_from_accumulating_stock(self):
        manager = self.make_manager(capacity=0, amount=3)
        manager.update(5)
        self.assertEqual(manager.state.npc_inventory.get("采集者", {}).get("草药", 0), 0)

    def test_existing_stock_above_new_capacity_is_clamped_before_gathering(self):
        manager = self.make_manager(capacity=2, amount=3)
        manager.state.npc_inventory = {"采集者": {"草药": 8}}
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 2)


if __name__ == "__main__":
    unittest.main()
