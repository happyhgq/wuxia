"""Alpha95：危机影响采购、缺料停产、补货后恢复的端到端回归。"""
import json
import unittest

import engine
from economy import EconomyManager


class Alpha95CrisisProductionCycleTests(unittest.TestCase):
    def make_manager(self, penalty=20):
        manager = EconomyManager({
            "tick": 0,
            "npc_inventory": {
                "原料供应者": {"铁矿石": 10},
                "制作铁匠": {"铁矿石": 0, "铁剑": 0},
            },
            "npc_gold": {"原料供应者": 1000, "制作铁匠": 1000},
            "events": {"world_crises": {"mistwood": {"id": "test_crisis", "travel_penalty": penalty}}},
            "market": {"铁矿石": {"traded": 0, "last_price": 3, "supply": 20},
                       "铁剑": {"traded": 0, "last_price": 30, "supply": 20}},
        })
        manager.recipes = {
            "制作铁匠": {
                "inputs": {"铁矿石": 4}, "outputs": {"铁剑": 1},
                "supplier_routes": [{"item": "铁矿石", "suppliers": ["原料供应者"], "unit_price": 3,
                                     "max_per_tick": 4, "max_stock": 4, "interval": 1}],
                "interval": 1,
                "output_capacity": {"铁剑": 10},
            }
        }
        manager.gatherers = {"原料供应者": {"room_id": "supplier_room", "item": "铁矿石", "capacity": 20}}
        manager.world_rooms = {"supplier_room": {"zone": "mistwood"}}
        manager.resources = {}
        manager.caravan_config = {}
        return manager

    def test_crisis_blocks_production_then_relief_restores_full_cycle(self):
        manager = self.make_manager(20)
        initial_gold = sum(manager.state.npc_gold.values())

        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["制作铁匠"]["铁矿石"], 2)
        self.assertEqual(manager.state.npc_inventory["制作铁匠"]["铁剑"], 0)
        self.assertEqual(manager.state.npc_inventory["原料供应者"]["铁矿石"], 8)

        manager.state.events["world_crises"]["mistwood"]["travel_penalty"] = 0
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["制作铁匠"]["铁矿石"], 0)
        self.assertEqual(manager.state.npc_inventory["制作铁匠"]["铁剑"], 1)
        self.assertEqual(manager.state.npc_inventory["原料供应者"]["铁矿石"], 6)
        self.assertEqual(sum(manager.state.npc_gold.values()), initial_gold)
        self.assertEqual(manager.state.market["铁剑"]["supply"], 21)
        # 原料只在制作消耗时减少一次；采购只是 NPC 间转移库存。
        self.assertEqual(manager.state.market["铁矿石"]["supply"], 16)

    def test_long_cycle_keeps_inventory_money_and_market_bounded(self):
        manager = self.make_manager(20)
        initial_gold = sum(manager.state.npc_gold.values())
        initial_town = manager.state.town_gold
        for tick in range(60):
            if tick in (15, 35):
                manager.state.events["world_crises"]["mistwood"]["travel_penalty"] = 0
            elif tick in (25, 45):
                manager.state.events["world_crises"]["mistwood"]["travel_penalty"] = 20
            manager.update(1)
            for stock in manager.state.npc_inventory.values():
                for amount in stock.values():
                    self.assertGreaterEqual(amount, 0)
                    self.assertLessEqual(amount, 9999)
            for amount in manager.state.npc_gold.values():
                self.assertGreaterEqual(amount, 0)
                self.assertLessEqual(amount, 2_000_000_000)
            for row in manager.state.market.values():
                self.assertGreaterEqual(row.get("supply", 0), 0)
                self.assertLessEqual(row.get("supply", 0), 9999)
                self.assertGreaterEqual(row.get("traded", 0), 0)
        # 商税会把部分商户银两转入城镇资金池，因此以"NPC 钱包 + 城镇资金池"核对货币守恒；
        # 两者之间只发生转移，不应凭空增加或减少。
        self.assertEqual(
            sum(manager.state.npc_gold.values()) + manager.state.town_gold,
            initial_gold + initial_town,
        )
        json.dumps(manager.export_state(), ensure_ascii=False)
        self.assertEqual(engine.SAVE_VERSION, 12)

    def test_old_save_shape_without_crisis_data_still_updates(self):
        manager = self.make_manager(0)
        manager.state.events.pop("world_crises", None)
        manager.update(3)
        self.assertGreaterEqual(manager.state.npc_inventory["制作铁匠"]["铁剑"], 0)
        json.dumps(manager.export_state(), ensure_ascii=False)
        self.assertEqual(engine.SAVE_VERSION, 12)


if __name__ == "__main__":
    unittest.main()
