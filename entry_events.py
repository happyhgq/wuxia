# -*- coding: utf-8 -*-
"""入口事件：成功进入新场景后，按 data/events.json 的静态条件触发一次。

只读筛选与写状态分离：eligible_events 不修改玩家与世界；trigger_entry_events
只在移动成功后写入既有 world_state.variables.entry_events，并执行受控效果。
"""

import engine
import world_time
from ui_output import BODY_WIDTH, safe_print as print, wrap_player_text

ENTRY_EVENTS_KEY = "entry_events"


def _events_table():
    events = getattr(engine, "EVENTS", None)
    if not isinstance(events, dict):
        data = getattr(engine, "GAME_DATA", {}) or {}
        events = data.get("events", {})
    return events if isinstance(events, dict) else {}


def _entry_records(player, create=False):
    world_state = getattr(player, "world_state", None)
    if not isinstance(world_state, dict):
        return {}
    variables = world_state.get("variables")
    if not isinstance(variables, dict):
        if not create:
            return {}
        variables = {}
        world_state["variables"] = variables
    records = variables.get(ENTRY_EVENTS_KEY)
    if not isinstance(records, dict):
        if not create:
            return {}
        records = {}
        variables[ENTRY_EVENTS_KEY] = records
    return records


def _hours_match(event, tick):
    """hour 条件为 [start, end]，左闭右开并支持跨夜；缺省表示不限时。"""
    hours = event.get("hours")
    if hours is None:
        return True
    if not (isinstance(hours, (list, tuple)) and len(hours) == 2):
        return False
    start, end = hours
    if isinstance(start, bool) or isinstance(end, bool):
        return False
    hour = world_time.world_hour(tick)
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _room_matches(event, room_id):
    rooms = event.get("rooms")
    zone = event.get("zone")
    if rooms is None and zone is None:
        return False
    room = engine.ROOMS.get(room_id)
    if not isinstance(room, dict):
        return False
    if rooms is not None:
        if not isinstance(rooms, (list, tuple)) or room_id not in rooms:
            return False
    if zone is not None and str(zone) != str(room.get("zone", "main")):
        return False
    return True


def _event_done(player, event_id, event, tick):
    record = _entry_records(player).get(event_id)
    count = 0
    if isinstance(record, dict):
        try:
            count = int(record.get("count", 0))
        except (TypeError, ValueError):
            count = 0
    if event.get("once", True) is not False and count >= 1:
        return True
    try:
        cooldown = int(event.get("cooldown", 0) or 0)
    except (TypeError, ValueError):
        cooldown = 0
    if cooldown > 0 and isinstance(record, dict):
        last_clock = record.get("last_clock")
        if isinstance(last_clock, int) and not isinstance(last_clock, bool) and tick - last_clock < cooldown:
            return True
    return False


def eligible_events(player, room_id):
    """只读返回当前可触发的事件 (id, data)，按 priority 降序、文件顺序稳定排序。"""
    if room_id not in engine.ROOMS:
        return []
    tick = player.get_quest_clock()
    candidates = []
    for index, (event_id, event) in enumerate(_events_table().items()):
        if not isinstance(event, dict):
            continue
        if not _room_matches(event, room_id):
            continue
        if not _hours_match(event, tick):
            continue
        if _event_done(player, event_id, event, tick):
            continue
        requires = event.get("requires")
        if requires and not engine.check_conditions(
            requires, getattr(player, "world_state", {}),
            getattr(player, "completed_quests", None), player,
        ):
            continue
        try:
            priority = int(event.get("priority", 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        candidates.append((priority, index, event_id, event))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [(event_id, event) for _priority, _index, event_id, event in candidates]


def _emit(event):
    title = str(event.get("title", "") or "").strip()
    text = str(event.get("text", "") or "").strip()
    if not text:
        return
    prefix = f"【{title}】" if title else ""
    print(wrap_player_text(engine.style(prefix + text, "hint"), width=BODY_WIDTH))


def trigger_entry_events(player, room_id):
    """移动成功后触发一条事件；返回事件 ID，没有可触发事件时返回 None。"""
    candidates = eligible_events(player, room_id)
    if not candidates:
        return None
    event_id, event = candidates[0]
    tick = player.get_quest_clock()
    records = _entry_records(player, create=True)
    record = records.get(event_id)
    try:
        count = int(record.get("count", 0)) if isinstance(record, dict) else 0
    except (TypeError, ValueError):
        count = 0
    records[event_id] = {"count": count + 1, "last_clock": tick}
    engine.apply_world_effects(player.world_state, event.get("effects"))
    _emit(event)
    return event_id
