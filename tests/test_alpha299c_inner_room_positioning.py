# -*- coding: utf-8 -*-
"""Alpha299c：三间 T1 内室的定位、数据字段、描写与 UI 必须一致。"""

import contextlib
import io
import re
from unittest.mock import patch

import pytest

import engine
from actions import handle_talk_and_ask, handle_trading, look
from player import Player
from world_time import world_hour

# room_id, 内室主人, 父房, 内→父出口, 夜间整点 tick（tick 0 = 06:00）
INNER_ROOMS = (
    ("blacksmith_inner", "铁匠", "blacksmith", "外", 16),
    ("apothecary_backyard", "药铺老板", "medicine_shop", "前", 15),
    ("village_chief_room", "村长", "village_head_house", "外", 16),
)
OPPOSITE = {"外": "内", "前": "后", "内": "外", "后": "前"}
WORKSHOP_WORDS = ("铁砧", "炉火", "铁腥", "风箱", "淬火")
LIFE_ELEMENTS = ("床", "榻", "桌", "凳", "碗", "筷", "灯", "衣", "窗纸", "门帘", "茶", "被褥", "箱", "帘")


def _covers(entry, hour):
    start, end = int(entry["start"]) % 24, int(entry["end"]) % 24
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _player_at(room_id, tick):
    player = Player("内室验收", "散人")
    player.location = room_id
    player.set_var("quest_clock", tick)
    player.refresh_npc_schedules()
    return player


def _capture(fn, *args, **kwargs):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args, **kwargs)
    return stream.getvalue(), result


def _plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text).replace("\n", "").replace(" ", "")


@pytest.mark.parametrize("room_id,npc,parent,direction,tick", INNER_ROOMS)
def test_inner_room_data_fields_match_the_life_rest_positioning(room_id, npc, parent, direction, tick):
    room = engine.ROOMS[room_id]
    assert room.get("safe_zone") is True
    assert room.get("safe") is True
    assert room.get("map_hidden") is True
    assert isinstance(room.get("night_desc"), str) and room["night_desc"].strip()
    assert isinstance(room.get("night_hours"), list) and len(room["night_hours"]) == 2
    assert room.get("npcs") == [npc]

    # 父房出口双向，且内室用与父房相反的方向回到父房。
    assert room["exits"][direction] == parent
    assert engine.ROOMS[parent]["exits"][OPPOSITE[direction]] == room_id

    hour = world_hour(tick)
    entries = [
        entry for entry in engine.NPCS[npc].get("daily_schedule", [])
        if entry.get("location") == room_id and _covers(entry, hour)
    ]
    assert entries, f"{npc} 在 {hour} 点应位于 {room_id}"
    assert entries[0].get("state") == "normal"
    assert "在住处休息" not in str(entries[0].get("reason", ""))


def test_only_blacksmith_inner_closes_its_counter():
    assert engine.ROOMS["blacksmith_inner"].get("trade_closed") is True
    assert "内堂已打烊，只接交付与交谈" in engine.ROOMS["blacksmith_inner"]["trade_closed_text"]
    for room_id, *_ in INNER_ROOMS:
        if room_id != "blacksmith_inner":
            assert engine.ROOMS[room_id].get("trade_closed") is not True


@pytest.mark.parametrize("room_id,npc,parent,direction,tick", INNER_ROOMS)
def test_descriptions_read_as_living_space_not_workshop(room_id, npc, parent, direction, tick):
    room = engine.ROOMS[room_id]
    desc, night_desc = room["desc"], room["night_desc"]
    for text in (desc, night_desc):
        for word in WORKSHOP_WORDS:
            assert word not in text, f"{room_id} 描写不应出现铺面工作词：{word}"
        assert sum(1 for token in LIFE_ELEMENTS if token in text) >= 2
    # 夜间文案更收束，不是白天工作文案的复述。
    assert len(night_desc) < len(desc)


@pytest.mark.parametrize("room_id,npc,parent,direction,tick", INNER_ROOMS)
def test_night_look_switches_to_night_desc_and_live_npc_status(room_id, npc, parent, direction, tick):
    player = _player_at(room_id, tick)
    output, _ = _capture(look, player)
    plain = _plain(output)

    assert "【区域局势】安全" in plain
    assert "危险度" not in output
    assert "紧张" not in output
    assert _plain(player.get_npc_daily_activity(npc)["reason"]) in plain
    assert "在住处休息" not in output

    assert _plain(engine.ROOMS[room_id]["night_desc"]) in plain
    assert _plain(engine.ROOMS[room_id]["desc"]) not in plain


@pytest.mark.parametrize("room_id,npc,parent,direction,tick", INNER_ROOMS)
def test_daytime_look_uses_day_desc(room_id, npc, parent, direction, tick):
    player = _player_at(room_id, 3)  # tick 3 = 09:00
    output, _ = _capture(look, player)
    plain = _plain(output)
    assert "【区域局势】安全" in plain
    assert _plain(engine.ROOMS[room_id]["desc"]) in plain
    assert _plain(engine.ROOMS[room_id]["night_desc"]) not in plain


@pytest.mark.parametrize("room_id,npc,parent,direction,tick", INNER_ROOMS)
def test_night_npc_can_talk_and_hand_in_quests(room_id, npc, parent, direction, tick):
    player = _player_at(room_id, tick)
    assert npc in player.get_npcs_in_room(room_id)
    assert player.get_npc_location(npc, refresh=False) == room_id

    talk_output, _ = _capture(handle_talk_and_ask, player, [npc])
    assert f"【{engine.NPCS[npc].get('title', npc)}】" not in talk_output
    assert "关系：" not in talk_output and "状态：" not in talk_output
    assert "说道" in talk_output or "回应" in talk_output or "可接取委托" in talk_output
    assert "暂时不在状态" not in talk_output

    quest_id = f"alpha299c_{room_id}_delivery"
    quest = {
        "title": "夜话回执",
        "npc": npc,
        "turn_in_npc": npc,
        "target_type": "talk",
        "target_name": npc,
        "required_cnt": 1,
        "reward": {"exp": 1, "gold": 1},
        "desc": "内室验收用委托。",
    }
    player.active_quests[quest_id] = 1
    player.quest_states[quest_id] = {"stage": 0, "progress": 1}
    with patch.dict(engine.QUESTS, {quest_id: quest}), \
         patch.object(Player, "save_to_file", lambda self, filename=None: True):
        deliver_output, _ = _capture(handle_talk_and_ask, player, [npc, "交付委托", "夜话回执"])
    assert "恭喜完成任务【夜话回执】" in deliver_output
    assert quest_id in player.completed_quests
    assert quest_id not in player.active_quests


def test_blacksmith_inner_closed_counter_only_blocks_trade():
    player = _player_at("blacksmith_inner", 16)
    output, result = _capture(handle_trading, player, "sell", ["草药", "1"])
    assert result is False
    assert "内堂已打烊，只接交付与交谈" in output
