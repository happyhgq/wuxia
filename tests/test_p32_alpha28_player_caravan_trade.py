import contextlib
import io
import unittest

import actions
from economy import EconomyManager, TradeService


class DummyPlayer:
    def __init__(self, state=None):
        self.name = "测试侠客"
        self.location = "village_square"
        self.gold = 1000
        self.inventory = ["木材", "铁矿石"]
        self.economy_state = state or {}
        self.world_state = {"variables": {"quest_clock": 1}}
        self.saved = False

    def save_to_file(self):
        self.saved = True

    def get_npcs_in_room(self, room_id):
        return []


class Alpha28PlayerCaravanTradeTests(unittest.TestCase):
    def make_player(self):
        state = EconomyManager().export_state()
        state["tick"] = 1
        state["caravans"] = {
            "北路商队": {
                "position": 0, "gold": 500, "capacity": 8,
                "inventory": {"木材": 3, "铁矿石": 2}, "visits": 1,
            }
        }
        state["events"]["active_caravans"] = {
            "北路商队:village_square": {
                "name": "北路商队", "room": "village_square", "until_tick": 4,
            }
        }
        return DummyPlayer(state)

    def test_player_can_buy_and_sell_real_caravan_stock(self):
        player = self.make_player()
        ok, message = TradeService.buy_from_caravan(player, "北路商队", "木材", 2, 10)
        self.assertTrue(ok, message)
        self.assertEqual(player.inventory.count("木材"), 3)
        self.assertEqual(player.economy_state["caravans"]["北路商队"]["inventory"]["木材"], 1)
        self.assertEqual(player.gold, 980)
        ok, message = TradeService.sell_to_caravan(player, "北路商队", "铁矿石", 1, 8)
        self.assertTrue(ok, message)
        self.assertEqual(player.inventory.count("铁矿石"), 0)
        self.assertEqual(player.economy_state["caravans"]["北路商队"]["inventory"]["铁矿石"], 3)
        self.assertEqual(player.gold, 988)

    def test_caravan_trade_rejects_funds_stock_and_capacity_atomically(self):
        player = self.make_player()
        player.gold = 0
        before = list(player.inventory)
        ok, _ = TradeService.buy_from_caravan(player, "北路商队", "木材", 1, 10)
        self.assertFalse(ok)
        self.assertEqual(player.inventory, before)
        self.assertEqual(player.economy_state["caravans"]["北路商队"]["inventory"]["木材"], 3)
        player.gold = 100
        caravan = player.economy_state["caravans"]["北路商队"]
        caravan["capacity"] = 3
        caravan["inventory"] = {"木材": 3}
        before = list(player.inventory)
        ok, _ = TradeService.sell_to_caravan(player, "北路商队", "铁矿石", 1, 8)
        self.assertFalse(ok)
        self.assertEqual(player.inventory, before)
        self.assertEqual(player.gold, 100)

    def test_commands_use_arrived_caravan_and_persist_player_trade(self):
        player = self.make_player()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(actions.handle_trading(player, "shop", []))
            self.assertTrue(actions.handle_trading(player, "buy", ["木材", "1"]))
            self.assertTrue(actions.handle_trading(player, "sell", ["铁矿石", "1"]))
        output = out.getvalue()
        self.assertIn("北路商队的行商货单", output)
        self.assertIn("购入【木材】", output)
        self.assertIn("售出【铁矿石】", output)
        self.assertTrue(player.saved)
        self.assertEqual(player.economy_state["caravans"]["北路商队"]["inventory"]["木材"], 2)
        self.assertEqual(player.economy_state["caravans"]["北路商队"]["inventory"]["铁矿石"], 3)

    def test_chinese_caravan_manifest_alias_routes_to_list_command(self):
        import main
        command, _ = main.parse_command("货单")
        self.assertEqual(command, "list")
        command, _ = main.parse_command("卖 木材 2")
        self.assertEqual(command, "sell")

    def test_old_caravan_state_without_capacity_uses_safe_default(self):
        player = self.make_player()
        caravan = player.economy_state["caravans"]["北路商队"]
        caravan.pop("capacity")
        ok, _ = TradeService.sell_to_caravan(player, "北路商队", "铁矿石", 1, 5)
        self.assertTrue(ok)
        self.assertEqual(caravan["capacity"], 8)


if __name__ == "__main__":
    unittest.main()
