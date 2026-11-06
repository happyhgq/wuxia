"""Alpha217：长周期世界推进、存读档续跑的一致性回归审计。"""
import json
import random
from unittest.mock import patch

from player import Player


def _player():
    return Player("长周期一致性验收侠客", "散人")


def _snapshot(player):
    world_state = json.loads(json.dumps(player.world_state, ensure_ascii=False))
    # Loading deliberately marks the current room/zone as visited; compare durable simulation state,
    # not these idempotent onboarding flags that may be initialized during restoration.
    flags = world_state.get("flags", {})
    world_state["flags"] = {
        key: value for key, value in flags.items()
        if not key.startswith("visited:") and not key.startswith("visited_zone:")
    }
    return json.loads(json.dumps({
        "clock": player.get_quest_clock(),
        "world_state": world_state,
        "economy_state": player.economy_state,
        "active_quests": player.active_quests,
        "quest_states": player.quest_states,
        "completed_quests": player.completed_quests,
        "inventory": player.inventory,
        "gold": player.gold,
    }, ensure_ascii=False, sort_keys=True))


def test_long_world_tick_batch_matches_one_tick_at_a_time():
    batched, stepped = _player(), _player()
    with patch("economy.manager.time.time", return_value=1_800_000_000.0):
        random.seed(2172026)
        assert batched.tick_quest_clock(111) == 111
        random.seed(2172026)
        for _ in range(111):
            stepped.tick_quest_clock(1)

    assert _snapshot(batched) == _snapshot(stepped)


def test_save_load_and_continue_matches_uninterrupted_long_world_cycle(tmp_path, capsys):
    uninterrupted, resumed = _player(), _player()
    with patch("economy.manager.time.time", return_value=1_800_000_000.0):
        random.seed(2172027)
        uninterrupted.tick_quest_clock(60)
        random.seed(2172027)
        resumed.tick_quest_clock(60)

        path = tmp_path / "alpha217_v12_roundtrip.json"
        assert resumed.save_to_file(str(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["version"] == 12
        loaded = Player.load_from_file(str(path))
        capsys.readouterr()
        assert loaded is not None

        random.seed(2172028)
        uninterrupted.tick_quest_clock(51)
        random.seed(2172028)
        loaded.tick_quest_clock(51)

    assert _snapshot(loaded) == _snapshot(uninterrupted)
