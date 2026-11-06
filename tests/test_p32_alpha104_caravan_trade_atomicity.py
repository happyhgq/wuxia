"""Alpha104：商队交易必须同步影响玩家与商队，失败交易不得产生部分扣款。"""
from types import SimpleNamespace

from economy import TradeService


def make_player():
    return SimpleNamespace(
        gold=100,
        inventory=["草药", "草药", "木材"],
        economy_state={
            "caravans": {
                "村镇行商": {
                    "gold": 50,
                    "inventory": {"木剑": 2},
                    "capacity": 4,
                }
            },
            "market": {},
            "regional_market": {},
            "events": {},
        },
    )


def test_buy_from_caravan_updates_both_sides_atomically():
    player = make_player()
    ok, _ = TradeService.buy_from_caravan(player, "村镇行商", "木剑", 1, 20)
    assert ok
    caravan = player.economy_state["caravans"]["村镇行商"]
    assert player.gold == 80
    assert player.inventory.count("木剑") == 1
    assert caravan["inventory"]["木剑"] == 1
    assert caravan["gold"] == 70


def test_failed_purchase_does_not_partially_change_either_side():
    player = make_player()
    before_inventory = list(player.inventory)
    before_gold = player.gold
    before_caravan = {
        "gold": player.economy_state["caravans"]["村镇行商"]["gold"],
        "inventory": dict(player.economy_state["caravans"]["村镇行商"]["inventory"]),
    }
    ok, _ = TradeService.buy_from_caravan(player, "村镇行商", "木剑", 3, 20)
    assert not ok
    assert player.gold == before_gold
    assert player.inventory == before_inventory
    assert player.economy_state["caravans"]["村镇行商"]["gold"] == before_caravan["gold"]
    assert player.economy_state["caravans"]["村镇行商"]["inventory"] == before_caravan["inventory"]


def test_sale_updates_player_and_caravan_and_enforces_capacity():
    player = make_player()
    ok, _ = TradeService.sell_to_caravan(player, "村镇行商", "草药", 1, 8)
    assert ok
    caravan = player.economy_state["caravans"]["村镇行商"]
    assert player.gold == 108
    assert player.inventory.count("草药") == 1
    assert caravan["inventory"]["草药"] == 1
    assert caravan["gold"] == 42

    # 货舱当前占用 3/4，再卖 2 件会超出容量，必须整体拒绝。
    before = (player.gold, list(player.inventory), caravan["gold"], dict(caravan["inventory"]))
    ok, _ = TradeService.sell_to_caravan(player, "村镇行商", "草药", 2, 8)
    assert not ok
    assert (player.gold, list(player.inventory), caravan["gold"], dict(caravan["inventory"])) == before
