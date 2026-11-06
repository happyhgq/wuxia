"""Alpha144：世界时钟批量推进必须等价于相同次数的逐步推进。"""
import json
import random
from unittest.mock import patch

from player import Player


def _make_player(seed):
    random.seed(seed)
    return Player("世界推进验收侠客", "散人")


def _snapshot(player):
    return json.loads(json.dumps({
        "clock": player.get_quest_clock(),
        "world_state": player.world_state,
        "economy_state": player.economy_state,
        "active_quests": player.active_quests,
        "quest_states": player.quest_states,
    }, ensure_ascii=False, sort_keys=True))


def test_world_tick_batch_matches_stepped_advancement():
    batched = _make_player(1442026)
    stepped = _make_player(1442026)

    # 资源恢复记录含真实时间戳；固定时间源，才能比较模拟逻辑而非运行耗时。
    with patch("economy.manager.time.time", return_value=1_800_000_000.0):
        random.seed(1442029)
        batched.tick_quest_clock(12)
        random.seed(1442029)
        for _ in range(12):
            stepped.tick_quest_clock(1)

    assert _snapshot(batched) == _snapshot(stepped)


def test_world_tick_batch_advances_clock_by_exact_number_of_steps():
    player = _make_player(1442027)
    assert player.tick_quest_clock(25) == 25
    assert player.get_quest_clock() == 25


def test_zero_step_keeps_legacy_refresh_without_advancing_clock():
    player = _make_player(1442028)
    before_clock = player.get_quest_clock()
    before_economy_tick = player.economy_state.get("tick", 0)
    player.tick_quest_clock(0)
    assert player.get_quest_clock() == before_clock
    assert player.economy_state.get("tick", 0) == before_economy_tick
