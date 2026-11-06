"""Alpha137：交易后的玩家与商队状态必须在 V12 存读档后保持一致。"""
from copy import deepcopy

from economy import TradeService
from player import Player


def make_player():
    player = Player("行商测试", "散人")
    player.gold = 200
    player.inventory = ["草药", "草药", "木材"]
    player.economy_state = {
        "tick": 17,
        "caravans": {
            "村镇行商": {
                "gold": 80,
                "inventory": {"铁剑": 2},
                "capacity": 6,
                "route": ["村中广场", "天衡广场"],
                "until_tick": 24,
            }
        },
        "resources": {"mistwood_stream": {"remaining": 3, "last_tick": 15}},
        "npc_inventory": {},
        "npc_gold": {},
        "market": {},
        "regional_market": {},
        "events": {},
        "trade_history": [],
    }
    return player


def test_trade_results_and_world_economy_survive_save_load(tmp_path):
    player = make_player()
    ok, _ = TradeService.sell_to_caravan(player, "村镇行商", "草药", 1, 8)
    assert ok
    ok, _ = TradeService.buy_from_caravan(player, "村镇行商", "铁剑", 1, 30)
    assert ok

    save_path = tmp_path / "continuity.json"
    assert player.save_to_file(str(save_path))
    restored = Player.load_from_file(str(save_path))
    assert restored is not None

    caravan = restored.economy_state["caravans"]["村镇行商"]
    assert restored.gold == 178
    assert restored.inventory.count("草药") == 1
    assert restored.inventory.count("铁剑") == 1
    assert caravan["gold"] == 102
    assert caravan["inventory"]["草药"] == 1
    assert caravan["inventory"]["铁剑"] == 1
    assert caravan["until_tick"] == 24
    assert restored.economy_state["tick"] == 17
    assert restored.economy_state["resources"]["mistwood_stream"]["remaining"] == 3
    assert len(restored.economy_state["trade_history"]) == 2


def test_failed_trade_after_load_keeps_economy_state_unchanged(tmp_path):
    player = make_player()
    save_path = tmp_path / "failed_trade.json"
    assert player.save_to_file(str(save_path))
    restored = Player.load_from_file(str(save_path))
    before_inventory = list(restored.inventory)
    before_gold = restored.gold
    before_state = deepcopy(restored.economy_state)

    ok, _ = TradeService.sell_to_caravan(restored, "村镇行商", "木材", 1, 100)
    assert not ok  # 商队资金不足，失败交易不能扣除玩家物品或改动双方资金。
    assert restored.inventory == before_inventory
    assert restored.gold == before_gold
    assert restored.economy_state == before_state
