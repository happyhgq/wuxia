"""Alpha111：商队向铁匠交付铁矿石时，银两必须只从买方转给卖方。"""
from economy import EconomyManager


def test_caravan_ore_delivery_transfers_money_instead_of_destroying_both_sides():
    manager = EconomyManager()
    state = manager.state
    npc_id = "铁匠"
    state.npc_gold[npc_id] = 100
    state.npc_inventory[npc_id] = {"铁矿石": 0, "铁剑": 0}
    state.npc_inventory["百炼铁铺铁匠"] = {"铁矿石": 0, "铁剑": 0}
    state.caravans["北路商队"] = {
        "position": 1, "gold": 100, "inventory": {"铁矿石": 10},
        "capacity": 90, "visits": 0, "travel_progress": 0,
    }
    before_total = state.npc_gold[npc_id] + state.caravans["北路商队"]["gold"]

    manager.update(1)

    caravan = state.caravans["北路商队"]
    after_total = state.npc_gold[npc_id] + caravan["gold"]
    assert state.npc_inventory[npc_id]["铁矿石"] == 10
    assert caravan["inventory"].get("铁矿石", 0) == 0
    assert state.npc_gold[npc_id] == 80
    assert caravan["gold"] == 113  # 收到20两货款，另支付7两正常停靠开销
    assert after_total == before_total - 7


def test_ore_delivery_does_not_create_or_destroy_money_when_buyer_cannot_pay():
    manager = EconomyManager()
    state = manager.state
    npc_id = "铁匠"
    state.npc_gold[npc_id] = 1
    state.npc_inventory[npc_id] = {"铁矿石": 0, "铁剑": 0}
    state.npc_inventory["百炼铁铺铁匠"] = {"铁矿石": 0, "铁剑": 0}
    state.caravans["北路商队"] = {
        "position": 1, "gold": 100, "inventory": {"铁矿石": 10},
        "capacity": 90, "visits": 0, "travel_progress": 0,
    }
    manager.update(1)
    assert state.npc_inventory[npc_id]["铁矿石"] == 0
    assert state.caravans["北路商队"]["inventory"]["铁矿石"] == 10
    assert state.npc_gold[npc_id] == 1
    assert state.caravans["北路商队"]["gold"] == 93  # 未成交，仅支付7两正常停靠开销
