"""Alpha268：全体固定 NPC 忙碌状态、场景在场与日程倒计时专项审计。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import handle_talk_and_ask
from player import Player


def capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def test_all_fixed_npcs_remain_locatable_and_present_while_temporarily_busy():
    player = Player("全体NPC忙碌审计", "散人")
    assert len(engine.NPCS) == 77
    for npc_name in engine.NPCS:
        room_id = player.get_npc_home_location(npc_name)
        assert room_id in engine.ROOMS, npc_name
        player.set_npc_location(npc_name, room_id, source="alpha268_audit")
        player.location = room_id
        player.set_npc_state(npc_name, "busy", duration=3,
                             reason="正在处理事务", source="alpha268_audit")

        present = player.get_npcs_in_room(room_id)
        assert npc_name in present, npc_name
        before_location = player.get_npc_location(npc_name, refresh=False)
        output, result = capture(handle_talk_and_ask, player, [npc_name])

        assert result is False, npc_name
        assert "当前地点没有" not in output, (npc_name, output)
        assert "状态：" not in output, (npc_name, output)
        assert "正在处理事务" in output, (npc_name, output)
        assert "应了一声" in output or "应了你一声" in output, (npc_name, output)
        assert "说道" not in output, (npc_name, output)
        assert "无暇交谈" not in output, (npc_name, output)
        assert player.get_npc_location(npc_name, refresh=False) == before_location, npc_name
        assert npc_name in player.get_npcs_in_room(room_id), npc_name


def test_all_npc_schedule_locations_and_states_are_valid():
    data_path = Path(__file__).resolve().parents[1] / "data" / "npcs.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    assert len(data) == 77
    allowed = Player.NPC_STATE_ALLOWED
    busy_entries = []
    scheduled_npcs = set()
    for npc_name, info in data.items():
        for entry in info.get("daily_schedule", []) or []:
            scheduled_npcs.add(npc_name)
            location = entry.get("location")
            if location is None:
                # T2 人物离场用 location=null 表示不在场，不指向任何房间。
                assert info.get("schedule_tier") == "T2", (npc_name, entry)
            else:
                assert location in engine.ROOMS, (npc_name, entry)
            assert entry.get("state", "normal") in allowed, (npc_name, entry)
            if entry.get("state") == "busy":
                busy_entries.append((npc_name, entry))
    assert len(scheduled_npcs) == 22
    assert len(busy_entries) == 35


def test_scheduled_busy_npc_still_answers_normally():
    player = Player("日程忙碌交谈", "散人")
    # tick 0 = 卯时 06:00，正值守卫 06:00—12:00 的巡逻忙碌时段。
    player.world_state.setdefault("variables", {})["quest_clock"] = 0
    player.location = "village_south_street"
    player.set_npc_location("守卫", "village_south_street", source="test")
    assert player.get_npc_state("守卫") == "busy"
    output, result = capture(handle_talk_and_ask, player, ["守卫"])
    assert result is False
    assert "状态：" not in output
    assert "正在巡逻村口" in output
    assert "无暇交谈" not in output


def test_scheduled_busy_state_ends_at_schedule_boundary():
    player = Player("跨日忙碌边界", "散人")
    # 守卫 18:00—22:00 忙碌；22:00 对应 tick 16，此后应不再显示该忙碌状态。
    player.world_state.setdefault("variables", {})["quest_clock"] = 16
    player.location = "village_gate"
    assert player.get_npc_state("守卫") != "busy"


def test_all_faction_action_busy_reactions_preserve_npc_location():
    data_path = Path(__file__).resolve().parents[1] / "data" / "factions.json"
    factions = json.loads(data_path.read_text(encoding="utf-8"))
    player = Player("势力行动忙碌审计", "散人")
    checked = 0
    for faction_name, faction in factions.items():
        for action_index, action in enumerate(faction.get("actions", []) or []):
            reactions = action.get("npc_reactions", []) or []
            if not reactions:
                continue
            for reaction in reactions:
                npc_name = reaction.get("npc")
                assert npc_name in engine.NPCS, (faction_name, reaction)
                room_id = player.get_npc_home_location(npc_name)
                assert room_id in engine.ROOMS, npc_name
                player.set_npc_location(npc_name, room_id, source="alpha268_faction_audit")
                before = player.get_npc_location(npc_name, refresh=False)
                player._apply_npc_reactions([reaction], f"alpha268_faction:{faction_name}:{action_index}")
                assert player.get_npc_state(npc_name) == reaction["state"], (faction_name, reaction)
                assert player.get_npc_location(npc_name, refresh=False) == before, (faction_name, reaction)
                checked += 1
    assert checked == 5


def test_every_scheduled_busy_period_remains_interactable():
    data_path = Path(__file__).resolve().parents[1] / "data" / "npcs.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    checked = 0
    for npc_name, info in data.items():
        for entry in info.get("daily_schedule", []) or []:
            if entry.get("state") != "busy":
                continue
            room_id = entry.get("location")
            if room_id not in engine.ROOMS:
                # 忙碌日程必须发生在真实场景；离场条目应为 away。
                raise AssertionError((npc_name, entry))
            start = int(entry["start"]) % 24
            player = Player("日程忙碌全量审计", "散人")
            player.world_state.setdefault("variables", {})["quest_clock"] = (start - 6) % 24
            player.set_npc_location(npc_name, room_id, source="alpha268_schedule_audit")
            player.location = room_id
            assert player.get_npc_state(npc_name) == "busy", (npc_name, entry)
            assert npc_name in player.get_npcs_in_room(room_id), (npc_name, entry)
            output, result = capture(handle_talk_and_ask, player, [npc_name])
            assert result is False, (npc_name, entry)
            assert "状态：" not in output, (npc_name, entry, output)
            assert "应了一声" in output or "应了你一声" in output, (npc_name, entry, output)
            assert "【可接取委托】" not in output, (npc_name, entry, output)
            assert "无暇交谈" not in output, (npc_name, entry, output)
            assert "当前地点没有" not in output, (npc_name, entry, output)
            checked += 1
    assert checked == 35
