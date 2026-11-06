"""Alpha77：NPC 采集职业遵守配置工时，并兼容无工时的旧配置。"""
import unittest
from economy.manager import EconomyManager


class Alpha77NpcWorkHoursTests(unittest.TestCase):
    def _manager(self, tick, work_hours):
        manager = EconomyManager({"tick": tick, "resources": {"field": {"remaining": 20, "last_tick": tick}}, "events": {}, "npc_inventory": {"采集者": {"草药": 0}}})
        manager.resources = {"field": {"item": "草药", "action": "gather", "capacity": 20, "regen_interval": 9999, "regen_amount": 0}}
        manager.gatherers = {"采集者": {"room_id": "field", "resource_room_id": "field", "item": "草药", "action": "gather", "interval": 1, "amount": 1, "capacity": 10, "work_hours": work_hours}}
        manager.recipes = {}
        manager.caravan_config = {}
        return manager

    def test_worker_does_not_gather_outside_configured_hours(self):
        manager = self._manager(18, [6, 17])
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 0)
        self.assertEqual(manager.state.resources["field"]["remaining"], 20)

    def test_worker_gathers_during_configured_hours(self):
        manager = self._manager(6, [6, 17])
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 1)
        self.assertEqual(manager.state.resources["field"]["remaining"], 19)

    def test_legacy_config_without_work_hours_keeps_old_behavior(self):
        manager = self._manager(2, None)
        manager.gatherers["采集者"].pop("work_hours")
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采集者"]["草药"], 1)


if __name__ == "__main__":
    unittest.main()
