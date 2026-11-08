"""Alpha261：任务依赖闭环审计与药铺委托对话一致性。"""
import contextlib
import io
import json
from pathlib import Path

import engine
from actions import (
    _resolve_npc_quest_name,
    handle_talk_and_ask,
)
from player import Player
from main import parse_command, _is_direct_quest_accept_command


def capture(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def _quest_dependencies(info):
    requires = info.get("requires") or {}
    deps = set()
    for flag in requires.get("flags", []) or []:
        if isinstance(flag, str) and flag.startswith("quest_completed:"):
            deps.add(flag.split(":", 1)[1])
    deps.update(requires.get("completed_quests", []) or [])
    return deps


def _set_flags_deep(value):
    flags = set()
    if isinstance(value, dict):
        if isinstance(value.get("set_flags"), dict):
            flags.update(k for k, enabled in value["set_flags"].items() if enabled)
        for child in value.values():
            flags.update(_set_flags_deep(child))
    elif isinstance(value, list):
        for child in value:
            flags.update(_set_flags_deep(child))
    return flags


def test_all_quest_dependencies_reference_existing_tasks_and_form_a_dag():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    events = json.loads(Path("data/world_events.json").read_text(encoding="utf-8"))
    producers = {}
    for qid, info in quests.items():
        for field in ("on_complete", "on_accept"):
            for flag in _set_flags_deep(info.get(field) or {}):
                producers.setdefault(flag, set()).add(qid)
    event_flags = set()
    for event in events.values():
        event_flags.update(_set_flags_deep(event))

    graph = {qid: _quest_dependencies(info) for qid, info in quests.items()}
    for qid, info in quests.items():
        requires = info.get("requires") or {}
        for flag in requires.get("flags", []) or []:
            if not isinstance(flag, str) or flag.startswith("quest_completed:"):
                continue
            if flag.startswith(("quest:", "case:", "sunken_ruins:", "world:", "northfront:")):
                assert flag in producers or flag in event_flags, (qid, flag)
                graph[qid].update(producers.get(flag, set()))
        assert graph[qid] <= set(quests), (qid, graph[qid] - set(quests))

    # 依赖边以“前置任务 -> 后续任务”表示；同一任务的多个条件只计一条边。
    forward = {qid: set() for qid in quests}
    for later, prerequisites in graph.items():
        for earlier in prerequisites:
            forward[earlier].add(later)
    state, stack = {}, []
    cycles = []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for later in forward[node]:
            if state.get(later) == 1:
                cycles.append(stack[stack.index(later):] + [later])
            elif state.get(later, 0) == 0:
                visit(later)
        stack.pop()
        state[node] = 2

    for qid in forward:
        if state.get(qid, 0) == 0:
            visit(qid)
    assert not cycles, cycles
    edges = {(earlier, later) for earlier, laters in forward.items() for later in laters}
    assert len(edges) == 66


def test_every_quest_giver_exists_and_is_placed_in_at_least_one_room():
    quests = json.loads(Path("data/quests.json").read_text(encoding="utf-8"))
    rooms = json.loads(Path("data/rooms.json").read_text(encoding="utf-8"))
    for qid, info in quests.items():
        giver = info.get("npc")
        turn_in = info.get("turn_in_npc") or giver
        assert giver in engine.NPCS, (qid, giver)
        assert turn_in in engine.NPCS, (qid, turn_in)
        assert any(giver in room.get("npcs", []) for room in rooms.values()), (qid, giver)
        assert any(turn_in in room.get("npcs", []) for room in rooms.values()), (qid, turn_in)


def test_village_road_reopening_chain_is_real_and_triggerable_from_village_head():
    quests = engine.QUESTS
    assert "村道回暖·药铺复业" in quests
    reopen = quests["村道回暖·药铺复业"]
    assert reopen["npc"] == "村长"
    assert reopen["turn_in_npc"] == "村长"
    assert "quest_completed:村道巡查·清理残匪" in reopen["requires"]["flags"]
    patrol = quests["村道巡查·清理残匪"]
    assert patrol["npc"] == "村长"
    assert "quest_completed:新手狩猎·野外除害" in patrol["requires"]["flags"]
    starter = quests["新手狩猎·野外除害"]
    assert starter["npc"] == "村长" and not starter.get("requires")
    rooms = engine.ROOMS
    assert "村长" in rooms["village_head_house"]["npcs"]
    assert "药铺老板" in rooms["medicine_shop"]["npcs"]


def test_herb_restock_is_locked_separately_from_available_starter_herb_quest():
    p = Player("药铺委托分层", "散人")
    p.location = "medicine_shop"
    out = capture(handle_talk_and_ask, p, ["药铺老板", "委托"])
    assert "【可接取委托】" in out
    assert "初入江湖·采药识草" in out
    assert "接取方式：交谈 药铺老板 接受委托 初入江湖·采药识草" in out
    assert "【当前不可接取】" in out
    assert "百草备货·补齐药材" in out
    assert out.index("【可接取委托】") < out.index("【当前不可接取】")


def test_herb_quest_accepts_title_without_middle_dot():
    p = Player("无间隔号接取", "散人")
    p.location = "medicine_shop"
    out = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托", "初入江湖采药识草"])
    assert "已接取任务" in out
    assert "新手采药·认识资源" in p.active_quests


def test_short_ambiguous_quest_name_lists_candidates_without_accepting():
    status, matches = _resolve_npc_quest_name("药", ["新手采药·认识资源", "百草备货·补齐药材"])
    assert status == "ambiguous"
    assert set(matches) == {"新手采药·认识资源", "百草备货·补齐药材"}


def test_unmatched_quest_name_suggests_the_canonical_title():
    p = Player("任务名纠错", "散人")
    p.location = "medicine_shop"
    out = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托", "初入江湖采药识草x"])
    assert "未找到任务" in out
    assert "初入江湖·采药识草" in out
    assert "新手采药·认识资源" not in p.active_quests


def test_busy_medicine_shop_owner_gives_short_reply_without_full_chat():
    p = Player("药铺忙碌交谈", "散人")
    p.location = "medicine_shop"
    p.set_npc_state("药铺老板", "busy", duration=20, reason="正在坐堂配药")
    before = p.get_relation("药铺老板")
    clock_before = p.get_quest_clock()
    out = capture(handle_talk_and_ask, p, ["药铺老板"])
    assert "状态：" not in out and "正在坐堂配药" in out
    assert "只匆匆应了一声" in out and "稍等" in out
    assert "【可接取委托】" not in out
    assert "关系变化" not in out
    assert p.get_relation("药铺老板") == before
    assert p.get_quest_clock() == clock_before


def test_busy_medicine_shop_owner_can_accept_quest():
    p = Player("药铺忙碌接取", "散人")
    p.location = "medicine_shop"
    p.set_npc_state("药铺老板", "busy", duration=20, reason="正在坐堂配药")
    out = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托", "初入江湖·采药识草"])
    assert "状态：" not in out
    assert "已接取任务" in out
    assert "新手采药·认识资源" in p.active_quests


def test_normal_relation_change_shows_before_and_after_status_and_value():
    p = Player("关系显示格式", "散人")
    p.location = "medicine_shop"
    out = capture(handle_talk_and_ask, p, ["药铺老板"])
    assert "关系变化：中立 +0 → 中立 +1" in out


def test_short_ambiguous_name_is_reported_in_npc_dialogue_without_accepting():
    p = Player("药铺简称歧义", "散人")
    p.location = "medicine_shop"
    out = capture(handle_talk_and_ask, p, ["药铺老板", "接受委托", "药"])
    assert "简称对应多项委托" in out
    assert "初入江湖·采药识草" in out
    assert "百草备货·补齐药材" in out
    assert not p.active_quests


def test_normalized_fullwidth_punctuation_and_whitespace_are_ignored():
    status, matches = _resolve_npc_quest_name("初入江湖，采药识草", ["新手采药·认识资源"])
    assert status == "matched"
    assert matches == ["新手采药·认识资源"]


def test_dialogue_choice_relation_change_uses_before_and_after_values():
    p = Player("关系选项显示", "散人")
    p.location = "medicine_shop"
    out = capture(handle_talk_and_ask, p, ["药铺老板", "买药"])
    assert "关系变化：中立 +0 → 中立 +2" in out


def test_standalone_accept_command_is_recognized_only_to_show_the_canonical_npc_syntax():
    cmd, args = parse_command("接受委托 初入江湖·采药识草")
    assert cmd == "接受委托"
    assert args == ["初入江湖·采药识草"]
    assert _is_direct_quest_accept_command(cmd, args)
