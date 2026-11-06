import unittest
from economy import EconomyManager, TradeService


class EconomyAlpha6Tests(unittest.TestCase):
    def test_caravan_only_delivers_ore_that_blacksmith_can_pay_for(self):
        manager = EconomyManager({
            "npc_inventory": {"铁匠": {"铁矿石": 0, "铁剑": 0}},
            "npc_gold": {"铁匠": 3},
            "caravans": {"北路商队": {"position": 1, "gold": 100,
                                     "inventory": {"铁矿石": 3, "铁剑": 0}, "visits": 0}},
        })
        manager.caravan_config = {"北路商队": {"route": ["blacksmith", "guiyun_south_gate"], "gold": 100, "inventory": {}}}
        manager.gatherers = {}
        manager.update(1)
        caravan = manager.state.caravans["北路商队"]
        smith_stock = manager.state.npc_inventory["铁匠"]
        self.assertEqual(smith_stock["铁矿石"], 1)
        self.assertEqual(caravan["inventory"]["铁矿石"], 2)
        self.assertEqual(caravan["gold"], 102)  # 铁匠支付2两，商队收到货款
        self.assertEqual(manager.state.npc_gold["铁匠"], 1)

    def test_caravan_does_not_transfer_ore_when_either_wallet_cannot_pay(self):
        manager = EconomyManager({
            "npc_inventory": {"铁匠": {"铁矿石": 0, "铁剑": 0}},
            "npc_gold": {"铁匠": 1},
            "caravans": {"北路商队": {"position": 1, "gold": 100,
                                     "inventory": {"铁矿石": 3, "铁剑": 0}, "visits": 0}},
        })
        manager.caravan_config = {"北路商队": {"route": ["blacksmith", "guiyun_south_gate"], "gold": 100, "inventory": {}}}
        manager.gatherers = {}
        manager.update(1)
        self.assertEqual(manager.state.npc_inventory["铁匠"]["铁矿石"], 0)
        self.assertEqual(manager.state.caravans["北路商队"]["inventory"]["铁矿石"], 3)
        self.assertEqual(manager.state.npc_gold["铁匠"], 1)

    def test_high_market_supply_reduces_player_sell_quote_more_than_buy_quote(self):
        class Player:
            economy_state = {"market": {"木材": {"supply": 35, "traded": 0, "last_price": 10}}}
        player = Player()
        buy = TradeService.market_price(player, "木材", 100, "buy", 1.0)
        sell = TradeService.market_price(player, "木材", 100, "sell", 1.0)
        self.assertLess(buy, 100)
        self.assertLess(sell, buy)

    def test_market_quote_handles_malformed_side_and_market_state(self):
        class Player:
            economy_state = {"market": {"木材": {"supply": "bad"}}}
        self.assertGreater(TradeService.market_price(Player(), "木材", 10, "unexpected"), 0)
        class LegacyPlayer:
            economy_state = None
        self.assertEqual(TradeService.market_price(LegacyPlayer(), "木材", 10, "buy"), 10)


if __name__ == "__main__":
    unittest.main()
