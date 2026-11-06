"""Alpha228 后续修复：损坏的经济流水字段不能让奖励在发放一半时异常退出。"""
from contextlib import redirect_stdout
from io import StringIO

from player import Player
from rewards import apply_reward_bundle


def test_invalid_gold_ledger_counter_does_not_interrupt_gold_reward_halfway():
    player = Player("流水异常银两测试", "散人")
    player.economy_state = {
        "events": {"economic_flow_ledger": {"player_reward_gold_created": "bad"}}
    }
    before_gold = player.gold

    with redirect_stdout(StringIO()):
        result = apply_reward_bundle(player, {"gold": 10}, announce=False)

    assert result["ok"] is True
    assert player.gold == before_gold + 10
    ledger = player.economy_state["events"]["economic_flow_ledger"]
    assert ledger["player_reward_gold_created"] == 10


def test_invalid_item_ledger_and_item_total_do_not_interrupt_item_reward():
    player = Player("流水异常物品测试", "散人")
    player.economy_state = {
        "events": {
            "economic_flow_ledger": {
                "player_reward_item_units_created": "bad",
                "player_reward_items_created": {"疗伤药": "bad"},
            },
            "economic_flow_history": None,
        }
    }
    before_inventory = list(player.inventory)

    with redirect_stdout(StringIO()):
        result = apply_reward_bundle(player, {"item": "疗伤药"}, announce=False)

    assert result["ok"] is True
    assert player.inventory == before_inventory + ["疗伤药"]
    ledger = player.economy_state["events"]["economic_flow_ledger"]
    assert ledger["player_reward_item_units_created"] == 1
    assert ledger["player_reward_items_created"]["疗伤药"] == 1
    assert isinstance(player.economy_state["events"]["economic_flow_history"], list)


def test_invalid_saved_world_clock_is_treated_as_zero_for_reward_history():
    player = Player("时钟异常流水测试", "散人")
    player.world_state.setdefault("variables", {})["quest_clock"] = "bad"

    with redirect_stdout(StringIO()):
        result = apply_reward_bundle(player, {"gold": 1, "item": "疗伤药"}, announce=False)

    assert result["ok"] is True
    rows = player.economy_state["events"]["economic_flow_history"]
    assert len(rows) == 2
    assert all(row["tick"] == 0 for row in rows)
