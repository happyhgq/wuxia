# -*- coding: utf-8 -*-
"""NPC 行为层：把日程与即时动作折算成统一的五态微行为。

本模块只做纯计算，不读存档、不写世界状态、不移动人物。daily_schedule
是 T1/T2 的硬规则；这里只给未被日程覆盖的人物选择微行为，或在写 tick
根据实际动作记录行为，不参与场景只读展示。
"""

import npc_utility

BEHAVIORS = ("idle", "working", "resting", "moving", "interacting")

_SCHEDULE_STATE_BEHAVIOR = {
    "normal": "idle",
    "busy": "working",
    "away": "resting",
    "injured": "resting",
    "fear": "interacting",
}

_ACTION_BEHAVIOR = {
    "patrol": "moving",
    "meet_npc": "moving",
    "seek_player": "moving",
    "move": "moving",
    "rest": "resting",
    "sleep": "resting",
    "work": "working",
    "craft": "working",
    "forge": "working",
    "trade": "working",
    "talk": "interacting",
    "interact": "interacting",
}

_SCENE_KEYWORDS = (
    ("working", ("巡", "值", "守", "忙", "工作", "打理", "看摊")),
    ("resting", ("歇", "睡", "休", "养")),
)


def choose_behavior(npc, world_time, context=None):
    """纯函数：返回 idle/working/resting/moving/interacting 之一。

    日程覆盖时只做状态映射，调用方不得据此覆盖日程展示；未覆盖时按
    即时动作、场景状态依次判断，默认 idle。
    """
    info = npc if isinstance(npc, dict) else {}
    context = context if isinstance(context, dict) else {}
    entry = npc_utility.active_schedule_entry(info.get("daily_schedule"), world_time)
    if entry is not None:
        state = str(entry.get("state", "normal") or "normal")
        return _SCHEDULE_STATE_BEHAVIOR.get(state, "idle")
    if context.get("interacting") is True:
        return "interacting"
    action = str(context.get("action", "") or "")
    behavior = _ACTION_BEHAVIOR.get(action)
    if behavior:
        return behavior
    if context.get("moving") is True:
        return "moving"
    status = str(info.get("scene_status", "") or "")
    for name, tokens in _SCENE_KEYWORDS:
        if any(token in status for token in tokens):
            return name
    return "idle"
