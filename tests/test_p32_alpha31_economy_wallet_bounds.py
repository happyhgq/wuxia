import unittest
from economy import TradeService, EconomyManager


class Player:
    def __init__(self, gold=100, inventory=None, economy_state=None):
        self.gold = gold
        self.inventory = list(inventory or [])
        self.inventory_capacity = 100
        self.economy_state = economy_state if economy_state is not None else {}
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha31EconomyWalletBoundsTests(unittest.TestCase):
    def test_purchase_is_rejected_when_npc_wallet_cannot_receive_full_payment(self):
        player = Player(gold=100, economy_state={
            "npc_inventory": {"铁匠": {"铁剑": 1}},
            "npc_gold": {"铁匠": 2_000_000_000},
        })
        ok, _ = TradeService.buy(player, "铁剑", 1, 30, "铁匠")
        self.assertFalse(ok)
        self.assertEqual(player.gold, 100)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_inventory"]["铁匠"]["铁剑"], 1)
        self.assertEqual(player.economy_state["npc_gold"]["铁匠"], 2_000_000_000)

    def test_corrupt_npc_wallet_does_not_break_purchase(self):
        player = Player(gold=100, economy_state={
            "npc_inventory": {"铁匠": {"铁剑": 1}},
            "npc_gold": {"铁匠": "broken"},
        })
        ok, _ = TradeService.buy(player, "铁剑", 1, 30, "铁匠")
        self.assertTrue(ok)
        self.assertEqual(player.economy_state["npc_gold"]["铁匠"], 1030)

    def test_npc_stock_is_sanitized_and_respects_configured_caps(self):
        manager = EconomyManager({
            "npc_inventory": {
                "采药人阿芷": {"草药": 99999, "木材": "bad", "铁矿石": -3},
                "铁匠": {"铁剑": 999},
            }
        })
        manager.update(0)
        stock = manager.state.npc_inventory
        self.assertEqual(stock["采药人阿芷"]["草药"], 16)
        self.assertEqual(stock["采药人阿芷"]["木材"], 0)
        self.assertEqual(stock["采药人阿芷"]["铁矿石"], 0)
        self.assertEqual(stock["铁匠"]["铁剑"], 8)

    def test_failed_purchase_keeps_wallet_and_inventory(self):
        player = Player(gold=10, economy_state={
            "npc_inventory": {"铁匠": {"铁剑": 1}},
            "npc_gold": {"铁匠": 50},
        })
        before = dict(player.economy_state["npc_gold"])
        ok, _ = TradeService.buy(player, "铁剑", 1, 30, "铁匠")
        self.assertFalse(ok)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_gold"], before)


if __name__ == "__main__":
    unittest.main()
