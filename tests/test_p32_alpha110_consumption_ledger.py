"""Alpha110：实际使用消耗品与装备强化必须计入经济退出流水。"""
from types import SimpleNamespace

import engine
from actions import apply_consumable
from economy.flow import record_player_consumption


def _player(inventory=None):
    return SimpleNamespace(
        inventory=list(inventory or []), gold=100,
        economy_state={"events": {}},
        world_state={"variables": {"quest_clock": 9}},
        hp=20, max_hp=100, mp=10, max_mp=100,
    )


def test_consumable_use_records_item_as_consumed_only_after_removal():
    consumable = next((name for name, data in engine.ITEMS.items()
                       if data.get("type") == "consumable"), None)
    assert consumable
    player = _player([consumable])
    assert apply_consumable(player, consumable) is True
    ledger = player.economy_state["events"]["economic_flow_ledger"]
    assert ledger["player_consumed_item_units"] == 1
    assert ledger["player_consumed_items"] == {consumable: 1}
    assert player.inventory == []
    assert player.economy_state["events"]["economic_flow_history"][-1]["source"] == "使用消耗品"


def test_forge_cost_recording_counts_real_material_and_gold_sinks():
    player = _player(["铁矿石", "铁矿石"])
    record_player_consumption(player, "铁矿石", 2, source="装备强化", gold=30)
    ledger = player.economy_state["events"]["economic_flow_ledger"]
    assert ledger["player_consumed_item_units"] == 2
    assert ledger["player_consumed_items"]["铁矿石"] == 2
    assert ledger["player_gold_removed_from_circulation"] == 30


def test_consumption_history_is_bounded_and_nonpositive_values_are_ignored():
    player = _player()
    events = player.economy_state["events"]
    events["economic_flow_history"] = [{"tick": i} for i in range(100)]
    record_player_consumption(player, "铁矿石", 0, source="无效消耗", gold=-2)
    assert "economic_flow_ledger" not in events
    record_player_consumption(player, "铁矿石", 1, source="实际消耗")
    assert len(events["economic_flow_history"]) == 100
    assert events["economic_flow_history"][-1]["source"] == "实际消耗"
