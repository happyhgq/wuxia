"""Alpha65：青石村居民全天作息与场景活动提示。"""
import json
from pathlib import Path

from player import Player

BASE = Path(__file__).resolve().parents[1]


def test_qingshi_residents_have_complete_daily_coverage_and_valid_locations():
    npcs = json.loads((BASE / "data" / "npcs.json").read_text(encoding="utf-8"))
    rooms = json.loads((BASE / "data" / "rooms.json").read_text(encoding="utf-8"))
    for name in ("菜贩孙婶", "挑水老邱", "农家阿禾", "铁匠学徒小石"):
        npc = npcs[name]
        for hour in range(24):
            active = []
            for entry in npc.get("daily_schedule", []):
                start, end = int(entry["start"]) % 24, int(entry["end"]) % 24
                if (start <= hour < end) if start < end else (hour >= start or hour < end):
                    active.append(entry)
            assert len(active) <= 1, f"{name} 在 {hour} 时辰有重叠日程"
            if active:
                assert active[0].get("location") in rooms
                assert active[0].get("reason", "").strip()
        assert npc.get("home_room") in rooms


def test_activity_and_location_refresh_across_day_night_boundary():
    player = Player("测试侠客")
    for hour, expected_activity_room, expected_current_room in (
        (6, "village_south_street", "public_well"),
        (21, "old_qiu_residence", "old_qiu_residence"),
        (16, "old_qiu_residence", "old_qiu_residence"),
    ):
        # tick 0 = 卯时 06:00；按现实钟点反推 tick，验证统一换算。
        player.set_var("quest_clock", (hour - 6) % 24)
        activity = player.get_npc_daily_activity("挑水老邱")
        assert activity["location"] == expected_activity_room
        assert activity["reason"]
        assert player.get_npc_location("挑水老邱") == expected_current_room


def test_apprentice_is_present_at_blacksmith_during_work_and_rest_hours():
    player = Player("测试侠客")
    player.set_var("quest_clock", 3)
    assert player.get_npc_location("铁匠学徒小石") == "blacksmith"
    assert "铁匠学徒小石" in player.get_npcs_in_room("blacksmith")
    activity = player.get_npc_daily_activity("铁匠学徒小石")
    assert "生火" in activity["reason"]
    player.set_var("quest_clock", 16)
    assert player.get_npc_location("铁匠学徒小石") == "blacksmith"
    assert "歇息" in player.get_npc_daily_activity("铁匠学徒小石")["reason"]


def test_village_woodcutter_supplies_carpenter_and_supports_real_production():
    from economy import EconomyManager

    manager = EconomyManager({
        "npc_inventory": {"樵夫老周": {"木材": 6}},
        "npc_gold": {"樵夫老周": 20, "木匠老许": 100},
    })
    manager.caravan_config = {}
    manager.gatherers = {}
    manager.resources = {}
    # 木匠采购间隔 12 个工时；工时左闭右开后需要跨过交班时辰凑满整轮。
    manager.update(24)
    state = manager.state
    # 木匠只采购真实库存中的木材；扣款、入账、原料消耗和成品产出必须一致。
    assert state.npc_inventory["樵夫老周"]["木材"] < 6
    assert state.npc_gold["樵夫老周"] > 20
    assert state.npc_gold["木匠老许"] < 100
    assert state.npc_inventory["木匠老许"].get("木剑", 0) >= 1
    assert state.market.get("木材", {}).get("traded", 0) >= 1
