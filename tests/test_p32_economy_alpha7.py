import unittest
from economy import EconomyManager, EconomyState, TradeService


class EconomyAlpha7Tests(unittest.TestCase):
    def test_corrupt_legacy_tick_and_town_fund_use_safe_defaults(self):
        state = EconomyState({"tick": "broken", "town_gold": "NaN", "market": []})
        self.assertEqual(state.tick, 0)
        self.assertEqual(state.town_gold, 5000)
        self.assertEqual(state.market, {})
        restored = EconomyState(state.to_dict())
        self.assertEqual(restored.town_gold, 5000)

    def test_town_sales_pay_only_from_available_funds_and_keep_unsold_goods(self):
        manager = EconomyManager({
            "town_gold": 90,
            "caravans": {"测试商队": {"position": 1, "gold": 10,
                "inventory": {"铁剑": 3}, "visits": 0}},
        })
        manager.caravan_config = {"测试商队": {"route": ["guiyun_south_gate", "blacksmith"], "gold": 10, "inventory": {}}}
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {}
        manager.update(1)
        caravan = manager.state.caravans["测试商队"]
        self.assertEqual(caravan["gold"], 100)
        self.assertEqual(caravan["inventory"]["铁剑"], 1)
        self.assertEqual(manager.state.town_gold, 0)
        self.assertEqual(manager.state.market["铁剑"]["traded"], 2)
        self.assertEqual(manager.state.market["铁剑"]["supply"], 22)

    def test_town_with_empty_wallet_does_not_create_caravan_gold(self):
        manager = EconomyManager({
            "town_gold": 0,
            "caravans": {"测试商队": {"position": 1, "gold": 10,
                "inventory": {"草药": 4}, "visits": 0}},
        })
        manager.caravan_config = {"测试商队": {"route": ["guiyun_south_gate", "blacksmith"], "gold": 10, "inventory": {}}}
        manager.resources = {}
        manager.recipes = {}
        manager.gatherers = {}
        manager.update(1)
        caravan = manager.state.caravans["测试商队"]
        self.assertEqual(caravan["gold"], 10)
        self.assertEqual(caravan["inventory"]["草药"], 4)
        self.assertEqual(manager.state.town_gold, 0)

    def test_trade_rejects_invalid_wallet_without_mutating_player_inventory(self):
        class Player:
            gold = 10
            inventory = ["铁矿石"]
            economy_state = {"npc_gold": {"铁匠": "invalid"}, "npc_inventory": {}}
            world_state = {"variables": {"quest_clock": 0}}
        player = Player()
        before = list(player.inventory)
        ok, _ = TradeService.sell(player, "铁矿石", 1, 5, "铁匠")
        self.assertFalse(ok)
        self.assertEqual(player.inventory, before)
        self.assertEqual(player.gold, 10)


if __name__ == "__main__":
    unittest.main()
