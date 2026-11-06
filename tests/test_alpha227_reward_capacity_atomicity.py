"""Alpha227：背包容量不足时奖励包必须整体失败，不能只发一部分。"""
from contextlib import redirect_stdout
from io import StringIO

import engine
from player import Player
from rewards import apply_reward_bundle


def test_reward_with_items_fails_atomically_when_inventory_is_full():
    player = Player("奖励容量验收", "散人")
    player.inventory = ["草药"] * 3
    player.inventory_capacity = 3
    before = (player.exp, player.gold, list(player.inventory))
    reward = {"exp": 25, "gold": 17, "items": [{"item": "疗伤药", "quantity": 1}]}
    with redirect_stdout(StringIO()):
        result = apply_reward_bundle(player, reward, source="容量测试", announce=True)
    assert result["ok"] is False
    assert "背包空间不足" in result["message"]
    assert (player.exp, player.gold, list(player.inventory)) == before


def test_reward_with_items_succeeds_at_exact_capacity():
    player = Player("奖励容量边界", "散人")
    player.inventory = ["草药"] * 2
    player.inventory_capacity = 3
    with redirect_stdout(StringIO()):
        result = apply_reward_bundle(player, {"gold": 3, "item": "疗伤药"}, announce=False)
    assert result["ok"] is True
    assert len(player.inventory) == 3
    assert player.inventory.count("疗伤药") == 1
