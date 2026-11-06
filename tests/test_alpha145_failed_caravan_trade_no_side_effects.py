"""Alpha145：失败的商队交易不得顺手改写旧存档里的其他字段。"""
from copy import deepcopy
from types import SimpleNamespace

from economy import TradeService


def make_player(gold=5):
    return SimpleNamespace(
        gold=gold,
        inventory=["草药"],
        economy_state={
            "caravans": {
                "旧商队": {
                    "gold": "异常银两",
                    "capacity": "异常容量",
                    "inventory": {"铁剑": 2, "木材": "异常库存", "草药": -3},
                }
            },
            "market": {},
            "regional_market": {},
            "events": {},
        },
    )


def test_failed_purchase_does_not_sanitize_caravan_state_as_a_side_effect():
    player = make_player(gold=1)
    before = deepcopy(player.economy_state)
    before_gold = player.gold
    before_inventory = list(player.inventory)

    ok, _ = TradeService.buy_from_caravan(player, "旧商队", "铁剑", 1, 20)

    assert not ok
    assert player.gold == before_gold
    assert player.inventory == before_inventory
    assert player.economy_state == before


def test_failed_sale_does_not_sanitize_caravan_state_as_a_side_effect():
    player = make_player(gold=5)
    player.economy_state["caravans"]["旧商队"].update(
        gold=0, capacity=0, inventory={"铁剑": 2, "木材": "异常库存"}
    )
    before = deepcopy(player.economy_state)
    before_gold = player.gold
    before_inventory = list(player.inventory)

    ok, _ = TradeService.sell_to_caravan(player, "旧商队", "草药", 1, 8)

    assert not ok
    assert player.gold == before_gold
    assert player.inventory == before_inventory
    assert player.economy_state == before


def test_successful_trade_still_normalizes_legacy_caravan_values():
    player = make_player(gold=100)
    caravan = player.economy_state["caravans"]["旧商队"]
    caravan.update(gold=10, capacity=8, inventory={"铁剑": "2", "木材": "异常库存"})

    ok, _ = TradeService.buy_from_caravan(player, "旧商队", "铁剑", 1, 20)

    assert ok
    assert caravan["inventory"] == {"铁剑": 1, "木材": 0}
    assert caravan["gold"] == 30
