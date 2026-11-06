"""Alpha80：制作受库存/原料阻塞后保留就绪状态，条件恢复时及时续产。"""
import unittest
from economy.manager import EconomyManager


class Alpha80ReadyProductionTests(unittest.TestCase):
    def _manager(self, stock):
        manager = EconomyManager({
            "tick": 6,
            "events": {"production_progress": {}},
            "market": {},
            "npc_inventory": {"作坊师傅": dict(stock)},
            "npc_gold": {},
            "resources": {},
        })
        manager.gatherers = {}
        manager.resources = {}
        manager.caravan_config = {}
        manager.recipes = {
            "作坊师傅": {
                "room_id": "test_workshop",
                "interval": 1,
                "inputs": {"铁矿石": 2},
                "outputs": {"铁剑": 1},
                "output_capacity": {"铁剑": 1},
            }
        }
        return manager

    def test_full_output_stock_keeps_production_ready(self):
        manager = self._manager({"铁矿石": 4, "铁剑": 1})
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"], {"铁矿石": 4, "铁剑": 1})
        self.assertEqual(manager.state.events["production_progress"]["作坊师傅"], 1)

        # 商队售出成品后腾出容量；下一次世界推进即可制作，不必再等完整周期。
        manager.state.npc_inventory["作坊师傅"]["铁剑"] = 0
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"]["铁矿石"], 2)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"]["铁剑"], 1)
        self.assertEqual(manager.state.events["production_progress"]["作坊师傅"], 0)

    def test_missing_inputs_keeps_ready_state_without_creating_goods(self):
        manager = self._manager({"铁矿石": 1, "铁剑": 0})
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"]["铁矿石"], 1)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"]["铁剑"], 0)
        self.assertEqual(manager.state.events["production_progress"]["作坊师傅"], 1)

        manager.state.npc_inventory["作坊师傅"]["铁矿石"] = 2
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"]["铁矿石"], 0)
        self.assertEqual(manager.state.npc_inventory["作坊师傅"]["铁剑"], 1)


if __name__ == "__main__":
    unittest.main()
