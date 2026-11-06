import unittest
from economy import EconomyManager


class Alpha94CrisisSupplyLinkTests(unittest.TestCase):
    def make_manager(self, travel_penalty=0):
        manager = EconomyManager({
            "tick": 0,
            "npc_inventory": {
                "原料供应者": {"铁矿石": 10},
                "制作铁匠": {"铁矿石": 0},
            },
            "npc_gold": {"原料供应者": 1000, "制作铁匠": 1000},
            "events": {"world_crises": {"mistwood": {"id": "test_crisis", "travel_penalty": travel_penalty}}},
        })
        manager.recipes = {
            "制作铁匠": {
                "inputs": {"铁矿石": 2}, "outputs": {"铁剑": 1},
                "supplier_routes": [{"item": "铁矿石", "suppliers": ["原料供应者"], "unit_price": 3,
                                     "max_per_tick": 3, "max_stock": 5, "interval": 1}],
                "interval": 100,
            }
        }
        manager.gatherers = {"原料供应者": {"room_id": "supplier_room", "item": "铁矿石"}}
        manager.world_rooms = {"supplier_room": {"zone": "mistwood"}}
        manager.resources = {}
        manager.caravan_config = {}
        return manager

    def test_crisis_reduces_actual_npc_procurement_and_stock_transfer(self):
        normal = self.make_manager(0)
        disrupted = self.make_manager(20)
        normal.update(1)
        disrupted.update(1)
        normal_bought = normal.state.npc_inventory["制作铁匠"]["铁矿石"]
        disrupted_bought = disrupted.state.npc_inventory["制作铁匠"]["铁矿石"]
        self.assertEqual(normal_bought, 2)
        self.assertEqual(disrupted_bought, 1)
        self.assertEqual(normal.state.npc_inventory["原料供应者"]["铁矿石"], 8)
        self.assertEqual(disrupted.state.npc_inventory["原料供应者"]["铁矿石"], 9)

    def test_supply_recovers_automatically_when_crisis_penalty_is_removed(self):
        manager = self.make_manager(20)
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["制作铁匠"]["铁矿石"], 1)
        manager.state.events["world_crises"]["mistwood"]["travel_penalty"] = 0
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["制作铁匠"]["铁矿石"], 2)

    def test_v12_save_version_unchanged_and_state_serializable(self):
        import json
        import engine
        manager = self.make_manager(20)
        manager.update(1)
        json.dumps(manager.export_state(), ensure_ascii=False)
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == "__main__":
    unittest.main()
