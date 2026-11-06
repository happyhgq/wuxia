"""Alpha50 end-to-end trade-loop acceptance: player, NPC buyers and caravans."""
import unittest
from economy import EconomyManager, TradeService


class PlayerStub:
    def __init__(self, inventory=None, gold=100, economy_state=None):
        self.name = "测试侠客"
        self.location = "village_square"
        self.inventory = list(inventory or [])
        self.inventory_capacity = 30
        self.gold = gold
        self.economy_state = economy_state if economy_state is not None else EconomyManager().export_state()
        self.world_state = {"variables": {"quest_clock": 0}}


class Alpha50TradeLoopAcceptanceTests(unittest.TestCase):
    def test_player_sells_gathered_material_to_npc_and_state_survives_reload(self):
        state = EconomyManager().export_state()
        state["npc_gold"]["木匠老许"] = 100
        player = PlayerStub(["木材", "木材"], 20, state)
        ok, msg = TradeService.sell(player, "木材", 2, 2, "木匠老许")
        self.assertTrue(ok, msg)
        self.assertEqual(player.gold, 24)
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.economy_state["npc_gold"]["木匠老许"], 96)
        self.assertEqual(player.economy_state["npc_inventory"]["木匠老许"]["木材"], 2)
        resumed = EconomyManager(player.economy_state).export_state()
        self.assertEqual(resumed["npc_inventory"]["木匠老许"]["木材"], 2)
        self.assertEqual(resumed["npc_gold"]["木匠老许"], 96)

    def test_player_sells_material_to_caravan_with_conserved_money_and_stock(self):
        state = EconomyManager().export_state()
        state["caravans"] = {"测试商队": {"gold": 50, "capacity": 4, "inventory": {"草药": 1}}}
        player = PlayerStub(["木材", "木材"], 10, state)
        ok, msg = TradeService.sell_to_caravan(player, "测试商队", "木材", 2, 5)
        self.assertTrue(ok, msg)
        caravan = player.economy_state["caravans"]["测试商队"]
        self.assertEqual(player.gold, 20)
        self.assertEqual(caravan["gold"], 40)
        self.assertEqual(caravan["inventory"], {"草药": 1, "木材": 2})
        self.assertEqual(player.inventory, [])
        self.assertEqual(player.gold + caravan["gold"], 60)

    def test_caravan_cannot_buy_when_funds_or_cargo_capacity_is_insufficient(self):
        state = EconomyManager().export_state()
        state["caravans"] = {"测试商队": {"gold": 4, "capacity": 2, "inventory": {"草药": 2}}}
        player = PlayerStub(["木材"], 10, state)
        before = (player.gold, list(player.inventory), dict(player.economy_state["caravans"]["测试商队"]["inventory"]))
        ok, _ = TradeService.sell_to_caravan(player, "测试商队", "木材", 1, 5)
        self.assertFalse(ok)
        self.assertEqual((player.gold, player.inventory, player.economy_state["caravans"]["测试商队"]["inventory"]), before)
        player.economy_state["caravans"]["测试商队"]["gold"] = 100
        ok, _ = TradeService.sell_to_caravan(player, "测试商队", "木材", 1, 5)
        self.assertFalse(ok)
        self.assertEqual(player.inventory, ["木材"])
        self.assertEqual(player.gold, 10)

    def test_invalid_trade_never_mutates_any_party(self):
        state = EconomyManager().export_state()
        state["caravans"] = {"测试商队": {"gold": 50, "capacity": 5, "inventory": {"木材": 2}}}
        player = PlayerStub(["草药"], 10, state)
        before = (player.gold, list(player.inventory), player.economy_state["caravans"]["测试商队"]["gold"], dict(player.economy_state["caravans"]["测试商队"]["inventory"]))
        ok, _ = TradeService.sell_to_caravan(player, "测试商队", "草药", 1, 0)
        self.assertFalse(ok)
        after = (player.gold, player.inventory, player.economy_state["caravans"]["测试商队"]["gold"], player.economy_state["caravans"]["测试商队"]["inventory"])
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
