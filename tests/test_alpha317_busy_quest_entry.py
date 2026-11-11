"""Alpha317：忙碌状态只能省略寒暄，不能吞掉委托入口或伪造发布人。"""
import contextlib
import io

import engine
from actions import handle_talk_and_ask, _quests_for_npc, _quest_title
from player import Player
from ui_output import _ANSI_RE


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return _ANSI_RE.sub("", stream.getvalue()), result


def room_of(npc_name):
    for room_id, info in engine.ROOMS.items():
        if npc_name in (info.get("npcs") or []):
            return room_id
    return engine.NPCS.get(npc_name, {}).get("home") or "village_square"


def make_player(npc_name, busy):
    player = Player("忙碌委托入口回归", "散人")
    player.set_var("quest_clock", 6)
    player.set_npc_location(npc_name, room_of(npc_name), source="alpha317")
    player.set_npc_state(
        npc_name,
        "busy" if busy else "normal",
        duration=99,
        reason="正在处理手头的事",
        source="alpha317",
    )
    player.location = room_of(npc_name)
    return player


def force_ready(player, quest_name):
    info = engine.QUESTS.get(quest_name, {})
    player.active_quests[quest_name] = 1
    stages = info.get("stages") or []
    if stages:
        player.quest_states[quest_name] = {
            "stage": len(stages) - 1,
            "progress": int(stages[-1].get("required_cnt", 1) or 1),
        }
    else:
        player.quest_states[quest_name] = {
            "stage": 0,
            "progress": int(info.get("required_cnt", 1) or 1),
        }


def quest_panel(output):
    """提取委托面板行；面板之间以空行分隔。"""
    panel = []
    collecting = False
    for line in output.splitlines():
        text = line.strip()
        if text in ("【可交付委托】", "【进行中委托】", "【可接取委托】"):
            panel.append(text)
            collecting = True
            continue
        if not text:
            collecting = False
            continue
        if collecting:
            panel.append(text)
    return panel


def test_busy_talk_matches_normal_quest_panel_for_every_quest_giver():
    givers = {}
    for quest_name, info in engine.QUESTS.items():
        if isinstance(info, dict) and info.get("npc"):
            givers.setdefault(info["npc"], []).append(quest_name)
    assert len(givers) == 36
    checked = 0
    for npc_name in sorted(givers):
        quest_name = _quests_for_npc(npc_name)[0]
        normal = make_player(npc_name, busy=False)
        busy = make_player(npc_name, busy=True)
        force_ready(normal, quest_name)
        force_ready(busy, quest_name)
        normal_out, _ = capture(handle_talk_and_ask, normal, [npc_name])
        busy_out, _ = capture(handle_talk_and_ask, busy, [npc_name])
        assert "当前地点没有" not in busy_out, npc_name
        assert quest_panel(normal_out) == quest_panel(busy_out), (npc_name, quest_panel(normal_out), quest_panel(busy_out))
        if _quest_title(quest_name) in normal_out:
            assert _quest_title(quest_name) in busy_out, npc_name
            checked += 1
    assert checked >= 30


def test_busy_turn_in_npc_never_offers_someone_elses_quest():
    npc_name = "万商会会长"
    player = make_player(npc_name, busy=True)
    player.set_flag("quest:jianghu_chessboard:started", True)
    capture(handle_talk_and_ask, player, [npc_name, "接受委托", _quest_title("残缺货单")])
    assert "残缺货单" not in player.active_quests
    output, _ = capture(handle_talk_and_ask, player, [npc_name])
    assert "接取方式：交谈 万商会会长 接受委托 残缺货单·拼合缺页" not in output
    assert "接取方式：交谈 万商会会长 接受委托 仓外伏击·护住实证" in output


def test_busy_turn_in_npc_still_lists_accepted_cross_delivery():
    npc_name = "万商会会长"
    player = make_player(npc_name, busy=True)
    player.active_quests["残缺货单"] = 1
    player.quest_states["残缺货单"] = {"stage": 0, "progress": 0}
    output, result = capture(handle_talk_and_ask, player, [npc_name])
    assert result is False
    assert "【进行中委托】" in output
    assert "残缺货单·拼合缺页" in output
    assert "接取方式" not in output


def cross_delivery_pairs():
    pairs = []
    for quest_name, info in engine.QUESTS.items():
        if not isinstance(info, dict):
            continue
        giver = info.get("npc")
        turn_in = info.get("turn_in_npc") or giver
        if giver and turn_in and turn_in != giver:
            pairs.append((quest_name, giver, turn_in))
    return pairs


def test_normal_talk_lists_accepted_cross_delivery_same_as_busy():
    pairs = cross_delivery_pairs()
    assert len(pairs) == 6
    for quest_name, _giver, turn_in in pairs:
        normal = make_player(turn_in, busy=False)
        busy = make_player(turn_in, busy=True)
        force_ready(normal, quest_name)
        force_ready(busy, quest_name)
        normal_out, _ = capture(handle_talk_and_ask, normal, [turn_in])
        busy_out, _ = capture(handle_talk_and_ask, busy, [turn_in])
        assert quest_panel(normal_out) == quest_panel(busy_out), quest_name
        assert _quest_title(quest_name) in normal_out, quest_name

