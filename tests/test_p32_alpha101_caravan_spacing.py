"""Alpha102：商队分级间隔、停留时长和全局错峰验收。"""
import json
from pathlib import Path

from economy import EconomyManager

ROOT = Path(__file__).resolve().parents[1]


def test_caravan_tiers_have_longer_intervals_and_distinct_cargo_scale():
    configs = json.loads((ROOT / "data/economy/caravans.json").read_text(encoding="utf-8"))
    expected = {
        "村镇行商": ("small", [30, 45], [3, 5], 30),
        "南路商队": ("medium", [60, 90], [6, 8], 50),
        "北路商队": ("large", [120, 180], [8, 12], 90),
    }
    for name, (tier, interval, stay, capacity) in expected.items():
        cfg = configs[name]
        assert cfg["tier"] == tier
        assert cfg["arrival_interval"] == interval
        assert cfg["stay_ticks"] == stay
        assert cfg["capacity"] >= capacity
    assert configs["北路商队"]["gold"] > configs["南路商队"]["gold"] > configs["村镇行商"]["gold"]
    assert len({tuple(configs[name]["inventory"].keys()) for name in configs}) == 3


def test_global_schedule_keeps_arrivals_spaced_and_only_one_square_occupied():
    manager = EconomyManager({})
    arrivals = []
    for _ in range(1, 801):
        manager.update(1)
        for message in manager.state.events.get("pending_world_announcements", []):
            if message.startswith("【商旅消息】"):
                arrivals.append((manager.state.tick, message))
        manager.state.events["pending_world_announcements"] = []
        active = [row for row in manager.state.events.get("active_caravans", {}).values()
                  if isinstance(row, dict) and row.get("room") in ("village_square", "guiyun_central_square")
                  and int(row.get("until_tick", -1)) > manager.state.tick]
        assert len(active) <= 1
    assert len(arrivals) >= 5
    ticks = [tick for tick, _ in arrivals]
    assert min(b - a for a, b in zip(ticks, ticks[1:])) >= 30
    assert len({"村中广场" if "村中广场" in msg else "天衡广场" for _, msg in arrivals}) == 2


def test_large_caravan_stays_longer_than_small_caravan():
    configs = json.loads((ROOT / "data/economy/caravans.json").read_text(encoding="utf-8"))
    assert configs["北路商队"]["stay_ticks"][0] > configs["村镇行商"]["stay_ticks"][1]
