import unittest
from economy import EconomyManager


class Alpha37NpcSupplyChainTests(unittest.TestCase):
    def _manager(self, supplier_stock=5, buyer_gold=100, supplier_gold=10):
        manager = EconomyManager({
            "npc_inventory": {"采药人阿芷": {"草药": supplier_stock}},
            "npc_gold": {"药铺老板": buyer_gold, "采药人阿芷": supplier_gold},
            "market": {"草药": {"traded": 0, "last_price": 3, "supply": 20}},
        })
        manager.resources = {}
        manager.gatherers = {}
        manager.caravan_config = {}
        manager.recipes = {
            "药铺老板": {
                "interval": 1,
                "inputs": {"草药": 2},
                "outputs": {"疗伤药": 1},
                "output_capacity": {"疗伤药": 4},
                "supplier_routes": [{
                    "item": "草药", "suppliers": ["采药人阿芷"],
                    "unit_price": 3, "max_per_tick": 2, "max_stock": 2,
                }],
            }
        }
        return manager

    def test_real_npc_purchase_funds_material_and_production_are_linked(self):
        manager = self._manager()
        manager.update(1)
        state = manager.state
        self.assertEqual(state.npc_inventory["采药人阿芷"]["草药"], 3)
        self.assertEqual(state.npc_inventory["药铺老板"]["草药"], 0)
        self.assertEqual(state.npc_inventory["药铺老板"]["疗伤药"], 1)
        self.assertEqual(state.npc_gold["药铺老板"], 94)
        self.assertEqual(state.npc_gold["采药人阿芷"], 16)
        self.assertEqual(state.market["草药"]["traded"], 2)

    def test_no_supplier_stock_means_no_fabricated_material_or_product(self):
        manager = self._manager(supplier_stock=0)
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["药铺老板"].get("草药", 0), 0)
        self.assertNotIn("疗伤药", manager.state.npc_inventory["药铺老板"])
        self.assertEqual(manager.state.npc_gold["药铺老板"], 100)

    def test_supplier_purchase_respects_buyer_wallet(self):
        manager = self._manager(buyer_gold=2)
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 5)
        self.assertEqual(manager.state.npc_inventory["药铺老板"].get("疗伤药", 0), 0)
        self.assertEqual(manager.state.npc_gold["药铺老板"], 2)

    def test_supplier_wallet_cap_does_not_destroy_buyer_money(self):
        manager = self._manager(supplier_gold=2_000_000_000)
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["采药人阿芷"]["草药"], 5)
        self.assertEqual(manager.state.npc_gold["药铺老板"], 100)
        self.assertEqual(manager.state.npc_gold["采药人阿芷"], 2_000_000_000)

    def test_supply_chain_survives_export_restore(self):
        manager = self._manager()
        manager.update(1)
        restored = EconomyManager(manager.export_state())
        restored.resources = {}
        restored.gatherers = {}
        restored.caravan_config = {}
        restored.recipes = manager.recipes
        restored.update(20)
        self.assertGreaterEqual(restored.state.npc_gold["药铺老板"], 0)
        self.assertLessEqual(restored.state.npc_gold["药铺老板"], 2_000_000_000)
        self.assertGreaterEqual(restored.state.npc_inventory["采药人阿芷"]["草药"], 0)
        self.assertLessEqual(restored.state.npc_inventory["药铺老板"].get("疗伤药", 0), 4)


if __name__ == "__main__":
    unittest.main()
