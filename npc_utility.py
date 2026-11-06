# -*- coding: utf-8 -*-
"""NPC 效用行为层。

把日程、营生工时、关系、区域治安与个人需求折算成行动分数，选出一个
可解释的行动。本模块只做纯计算，不读写存档、不移动人物；真正的世界
状态变更由 Player 执行，便于单独测试和回退。

同一人物、行动与世界时刻的加分抖动是稳定哈希，因此同一存档重复模拟
会得到相同结果，不会因为随机数种子变化而漂移。
"""

from world_time import world_hour

DEFAULT_ALLOWED_ACTIONS = (
    "work", "routine", "rest", "meal", "socialize",
    "patrol", "meet_npc", "seek_player", "investigate",
)
DEFAULT_NEEDS = {"fatigue": 20, "social": 35, "hunger": 30}
DEFAULT_MEAL_HOURS = (12, 18)
NIGHT_START = 21
NIGHT_END = 6
BLOCKED_STATES = {"injured", "fear", "away"}
SCHEDULE_TIERS = {"T1", "T2", "T3"}


def _active_schedule_entry(schedule, hour):
    """返回当前小时生效的日程条目；左闭右开，支持跨夜。纯读取。"""
    if not isinstance(schedule, list):
        return None
    for entry in schedule:
        if not isinstance(entry, dict):
            continue
        try:
            start = int(entry.get("start", 0)) % 24
            end = int(entry.get("end", 0)) % 24
        except (TypeError, ValueError, OverflowError):
            continue
        active = (start <= hour < end) if start < end else (hour >= start or hour < end)
        if active:
            return entry
    return None


def active_schedule_entry(schedule, world_time):
    """按世界 tick 返回生效日程条目；纯读取，供行为层判断日程是否覆盖。"""
    return _active_schedule_entry(schedule, world_hour(_int(world_time, 0)))


def get_npc_current_state(npc, world_time):
    """计算 NPC 在当前世界时刻的公开状态。

    只读纯函数：不推进时钟、不读写存档、不移动人物。world_time 为世界 tick，
    内部统一换算为 0~23 小时；T2 离场返回 room_id=None，T3 始终在岗。
    """
    info = npc if isinstance(npc, dict) else {}
    tick = _int(world_time, 0)
    hour = world_hour(tick)
    tier = str(info.get("schedule_tier", "") or "")
    always_available = info.get("always_available") is True or tier == "T3"
    home = info.get("home_room") if isinstance(info.get("home_room"), str) else None
    scene_status = str(info.get("scene_status", "") or "")
    entry = _active_schedule_entry(info.get("daily_schedule"), hour)
    if entry is None:
        room_id = home
        status = scene_status
        state = "normal"
        offstage = bool(tier == "T2" and room_id is None)
    else:
        raw_location = entry.get("location")
        if raw_location is None:
            room_id = None
            offstage = True
            state = "away"
        else:
            room_id = str(raw_location)
            offstage = False
            state = str(entry.get("state", "normal") or "normal")
        status = str(entry.get("reason", "") or "")
    if always_available:
        room_id = home or room_id
        offstage = False
        status = scene_status or status
    return {
        "room_id": room_id,
        "status": status,
        "state": state,
        "tier": tier,
        "offstage": offstage,
        "always_available": always_available,
    }

_ACTION_ORDER = {action: index for index, action in enumerate(DEFAULT_ALLOWED_ACTIONS)}


def _int(value, default=0):
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def stable_noise(npc_name, action, clock):
    """返回 0~3.96 的稳定抖动，让同分行动不至于每天完全固定。"""
    seed = 0
    for char in f"{npc_name}|{action}|{_int(clock)}":
        seed = (seed * 131 + ord(char)) % 1_000_003
    return (seed % 100) / 25.0


def advance_needs(needs, elapsed, action=""):
    """按经过的时辰推进疲劳、社交与饥饿，并返回新的需求快照。"""
    current = dict(DEFAULT_NEEDS)
    if isinstance(needs, dict):
        for key in current:
            current[key] = _int(needs.get(key, current[key]), current[key])
    elapsed = max(0, min(24, _int(elapsed)))
    fatigue = current["fatigue"] + elapsed * 2.0
    social = current["social"] + elapsed * 1.5
    hunger = current["hunger"] + elapsed * 2.2
    action = str(action or "")
    if action in ("work", "patrol"):
        fatigue += 5
        hunger += 2
    elif action == "rest":
        fatigue -= 18
    elif action in ("socialize", "meet_npc", "seek_player"):
        social -= 22
    elif action == "meal":
        hunger -= 40
    return {
        "fatigue": int(round(_clamp(fatigue))),
        "social": int(round(_clamp(social))),
        "hunger": int(round(_clamp(hunger))),
    }


def _is_night(hour):
    return hour >= NIGHT_START or hour < NIGHT_END


def _add(candidates, action, target, score, reason):
    candidates.append({
        "action": action,
        "target": target if target else None,
        "score": round(score, 2),
        "reason": reason,
    })


def score_candidates(context):
    """返回所有可行行动的候选列表，按分数从高到低排序。"""
    context = context if isinstance(context, dict) else {}
    name = str(context.get("name", ""))
    clock = _int(context.get("clock"), 0)
    hour = world_hour(clock)
    location = context.get("location")
    home = context.get("home")
    schedule_room = context.get("schedule_room")
    schedule_state = str(context.get("schedule_state", "normal") or "normal")
    schedule_reason = str(context.get("schedule_reason", "") or "")
    anchor = bool(context.get("anchor"))
    state = str(context.get("state", "normal") or "normal")
    blocked_states = set(context.get("blocked_states") or ()) | BLOCKED_STATES
    needs = context.get("needs") if isinstance(context.get("needs"), dict) else DEFAULT_NEEDS
    fatigue = _int(needs.get("fatigue", 20), 20)
    social = _int(needs.get("social", 35), 35)
    hunger = _int(needs.get("hunger", 30), 30)
    if state in blocked_states:
        return [{
            "action": "rest",
            "target": location,
            "score": 0.0,
            "reason": "眼下身体或情绪不适合走动，先留在原地",
        }]

    allowed = context.get("allowed_actions") or DEFAULT_ALLOWED_ACTIONS
    allowed = [action for action in allowed if action in _ACTION_ORDER]
    if anchor:
        # 任务人物不参与巡逻、串门和主动寻找玩家，避免关键交互对象离开固定位置。
        allowed = [action for action in allowed
                   if action not in ("patrol", "socialize", "meet_npc", "seek_player")]
    allowed = set(allowed)
    candidates = []

    work_room = context.get("work_room")
    if ("work" in allowed and work_room and context.get("work_hours_ok")
            and (not schedule_room or schedule_room == work_room)):
        # 有日程时日程优先；营生只在日程本来就指向工作地点时加强行动。
        score = 66 + 12
        if location == work_room:
            score += 8
        score += stable_noise(name, "work", clock)
        _add(candidates, "work", work_room, score, "按营生工时前往做工地点")

    if "routine" in allowed and schedule_room:
        score = 60
        if schedule_state == "busy":
            score += 8
        if location == schedule_room:
            score += 10
        if anchor:
            score += 22
        score += stable_noise(name, "routine", clock)
        reason = schedule_reason or "按日常日程前往常去的地方"
        _add(candidates, "routine", schedule_room, score, reason)

    if "rest" in allowed and home:
        score = 30 + fatigue * 0.25
        if location == home:
            score += 10
        night = _is_night(hour)
        if night and schedule_state != "busy":
            score += 45
        score += stable_noise(name, "rest", clock)
        reason = "夜深了，回住处歇息" if night else "回住处歇一歇"
        _add(candidates, "rest", home, score, reason)

    meal_room = context.get("meal_room")
    if "meal" in allowed and meal_room and context.get("meal_allowed"):
        score = 76 + hunger * 0.25
        if location == meal_room:
            score += 8
        score += stable_noise(name, "meal", clock)
        _add(candidates, "meal", meal_room, score, "到了饭点，去吃点东西并歇脚")

    social_room = context.get("social_room")
    if ("socialize" in allowed and social_room and 16 <= hour < 21
            and schedule_state != "busy"
            and (not schedule_room or schedule_room == social_room)):
        # 有日程时只在日程本来就在聚集地点的情况下加强社交，避免与日程来回拉扯。
        score = 55 + social * 0.3
        if location == social_room:
            score += 8
        score += stable_noise(name, "socialize", clock)
        _add(candidates, "socialize", social_room, score, "傍晚到熟人常聚的地方走走")

    route = [room for room in (context.get("route") or []) if room]
    if "patrol" in allowed and len(route) > 1:
        security = _int(context.get("security"), 70)
        score = 45 + max(0, 60 - security) * 0.4
        if location in route:
            score += 6
        score += stable_noise(name, "patrol", clock)
        _add(candidates, "patrol", None, score, "沿巡行路线查看当地治安")

    bond_target = context.get("bond_target")
    if "meet_npc" in allowed and bond_target:
        bond_strength = _int(context.get("bond_strength"), 0)
        score = 36 + min(30, max(0, bond_strength) * 0.3)
        score += stable_noise(name, "meet_npc", clock)
        _add(candidates, "meet_npc", None, score, f"去与{bond_target}会面")

    player_location = context.get("player_location")
    relation = _int(context.get("relation"), 0)
    seek_min = _int(context.get("seek_player_min_relation"), 30)
    seek_behaviors = set(context.get("seek_player_memory_behaviors") or ())
    memory_behavior = str(context.get("memory_behavior", "neutral") or "neutral")
    if ("seek_player" in allowed and player_location and player_location != location
            and relation >= seek_min and memory_behavior in seek_behaviors):
        score = 40 + max(0, min(60, relation)) * 0.2
        score += stable_noise(name, "seek_player", clock)
        _add(candidates, "seek_player", player_location, score, "主动去找玩家说说话")

    if "investigate" in allowed:
        _add(candidates, "investigate", None, 12 + stable_noise(name, "investigate", clock),
             "留意周围动静")

    candidates.sort(key=lambda item: (
        -item["score"], _ACTION_ORDER.get(item["action"], 99), str(item.get("target") or "")
    ))
    return candidates


def choose_action(context):
    """返回得分最高的行动决策；没有候选时退化为原地观察。"""
    candidates = score_candidates(context)
    if not candidates:
        return {
            "action": "investigate",
            "target": None,
            "score": 0.0,
            "reason": "暂时没有合适的行动",
            "candidates": [],
        }
    decision = dict(candidates[0])
    decision["candidates"] = candidates[:5]
    return decision
