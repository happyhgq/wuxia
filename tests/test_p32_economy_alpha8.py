import unittest
from economy import EconomyManager, EconomyState


class EconomyAlpha8Tests(unittest.TestCase):
    def test_update_repairs_malformed_nested_legacy_state(self):
        manager = EconomyManager({
            "tick": "not-a-number",
            "resources": {"mistwood_stream": "broken"},
            "npc_inventory": {"药农": None, "铁匠": {"铁矿石": "bad"}},
            "npc_gold": {"药农": "bad", "铁匠": -20},
            "caravans": {"南路商队": {"position": "bad", "gold": "bad", "inventory": None, "visits": "bad"}},
            "market": {"草药": "broken"},
            "events": {"gather_progress": None, "production_progress": "broken"},
        })
        # Tick must repair nested state rather than crash on a save produced by an older or edited build.
        manager.update(1)
        exported = manager.export_state()
        self.assertEqual(exported["tick"], 1)
        self.assertIsInstance(exported["resources"], dict)
        self.assertIsInstance(exported["npc_inventory"]["药农"], dict)
        self.assertGreaterEqual(exported["npc_gold"]["铁匠"], 0)
        self.assertIsInstance(exported["market"]["草药"], dict)
        self.assertIsInstance(exported["events"]["gather_progress"], dict)
        self.assertIsInstance(exported["events"]["production_progress"], dict)

    def test_mine_repairs_corrupt_resource_row_and_clamps_quantity(self):
        manager = EconomyManager({"resources": {"mistwood_stream": "bad"}})
        manager.resources = {"mistwood_stream": {"capacity": 4, "yield_max": 2, "item": "铁矿石"}}
        ok, result = manager.mine("mistwood_stream", "invalid")
        self.assertTrue(ok)
        self.assertEqual(result, ("铁矿石", 1))
        self.assertEqual(manager.state.resources["mistwood_stream"]["remaining"], 3)

    def test_negative_steps_do_not_advance_economy(self):
        manager = EconomyManager({"tick": 7})
        manager.update(-5)
        self.assertEqual(manager.state.tick, 7)

    def test_non_dict_caravan_inventory_is_reset_before_trade_tick(self):
        manager = EconomyManager({"caravans": {"南路商队": {"position": 0, "gold": 500, "inventory": "bad"}}})
        manager.caravan_config = {"南路商队": {"route": ["elsewhere", "guiyun_south_gate"], "gold": 500, "inventory": {}}}
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {}
        manager.update(1)
        self.assertIsInstance(manager.state.caravans["南路商队"]["inventory"], dict)
        self.assertGreaterEqual(manager.state.caravans["南路商队"]["gold"], 0)


if __name__ == "__main__":
    unittest.main()
