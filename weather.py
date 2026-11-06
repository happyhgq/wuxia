# -*- coding: utf-8 -*-
"""天气与二十四节气：只读世界时钟，向氛围层提供确定性的天时变化。

一年按 360 天计，每 15 天一个节气；每个整日黎明（tick 为 24 的倍数）
才可能换一次天气，持续 1~3 天。所有结果由存档内的种子与当前 tick
计算，不使用随机数、线程或定时器，读档续跑得到同一序列。

新角色首日另有一条固定的引导天气：开局晴，第 8 刻转阴、第 16 刻落小雨，
之后回到黎明换天。引导只在 `create_new_player` 时写入，旧存档不受影响。

状态写在既有 V12 `world_state.variables["weather_world"]` 中，不新增
存档顶层字段。旧存档首次读取时静默初始化为晴天，下一次黎明才开始
变化；本模块只影响文案与状态显示，不改变战斗、任务、经济或等级数值。
"""

import zlib

STATE_KEY = "weather_world"
DAYS_PER_YEAR = 360
DAYS_PER_TERM = 15
TICKS_PER_DAY = 24
TICKS_PER_TERM = DAYS_PER_TERM * TICKS_PER_DAY
_MAX_REPLAY_TICKS = TICKS_PER_DAY * DAYS_PER_YEAR * 3

# 新角色首日引导天气：(天气, 生效 tick)。首日第 8 刻转阴，第 16 刻落小雨。
FIRST_DAY_GUIDE = (("cloudy", 8), ("rain", 16))

TERMS = (
    "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
    "立夏", "小满", "芒种", "夏至", "小暑", "大暑",
    "立秋", "处暑", "白露", "秋分", "寒露", "霜降",
    "立冬", "小雪", "大雪", "冬至", "小寒", "大寒",
)

TERM_TEXTS = (
    "东风解冻，草木萌动。",
    "冰雪消融，雨水渐多。",
    "春雷初动，蛰虫惊醒。",
    "昼夜均分，燕语呢喃。",
    "天清气明，柳色正新。",
    "雨生百谷，春事将尽。",
    "暖风渐盛，草木繁茂。",
    "麦穗初盈，暑气渐生。",
    "麦浪翻黄，农事正忙。",
    "日影最短，暑气正盛。",
    "热风扑面，蝉声四起。",
    "骄阳似火，暑气蒸腾。",
    "凉风初起，叶尖微黄。",
    "暑气渐退，早晚转凉。",
    "露凝而白，秋意渐深。",
    "昼夜均分，桂子飘香。",
    "露水寒凉，草木渐凋。",
    "霜色初降，柿子枝头红透。",
    "北风渐起，万物收藏。",
    "薄雪初降，寒意侵人。",
    "雪落无声，天地尽白。",
    "日影最长，寒气最盛。",
    "朔风凛冽，滴水成冰。",
    "岁末天寒，静待春回。",
)

SEASONS = ("春", "夏", "秋", "冬")

KIND_LABELS = {
    "clear": "晴",
    "cloudy": "阴",
    "rain": "小雨",
    "storm": "雷雨",
    "snow": "小雪",
    "fog": "雾",
}

# 每个季节的天气权重；冬季不会下雨，春、夏、秋不会下雪。
_WEATHER_TABLES = {
    "春": (("clear", 5), ("cloudy", 3), ("rain", 3), ("storm", 1), ("fog", 2)),
    "夏": (("clear", 6), ("cloudy", 2), ("rain", 2), ("storm", 2)),
    "秋": (("clear", 5), ("cloudy", 3), ("rain", 2), ("fog", 2)),
    "冬": (("clear", 4), ("cloudy", 3), ("snow", 4), ("fog", 1)),
}


def _safe_tick(tick):
    try:
        return max(0, int(tick))
    except (TypeError, ValueError, OverflowError):
        return 0


def term_index_for_tick(tick):
    """当前节气在 TERMS 中的下标。"""
    return (_safe_tick(tick) // TICKS_PER_TERM) % len(TERMS)


def term_for_tick(tick):
    return TERMS[term_index_for_tick(tick)]


def season_for_tick(tick):
    """按每 6 个节气划分四季。"""
    return SEASONS[term_index_for_tick(tick) // 6]


def _seed_for(player):
    name = str(getattr(player, "name", "") or "")
    return zlib.crc32(name.encode("utf-8"))


def _next_dawn(tick):
    """严格晚于当前 tick 的下一个黎明；黎明本身不触发新的换天。"""
    return (tick // TICKS_PER_DAY + 1) * TICKS_PER_DAY


def _state(player, tick):
    world_state = getattr(player, "world_state", None)
    if not isinstance(world_state, dict):
        # 极端情况下允许无世界状态的调用方只读展示，不写回任何对象。
        return {
            "kind": "clear",
            "until_tick": _next_dawn(tick),
            "term_ordinal": tick // TICKS_PER_TERM,
            "seed": _seed_for(player),
        }
    variables = world_state.setdefault("variables", {})
    if not isinstance(variables, dict):
        variables = {}
        world_state["variables"] = variables
    state = variables.get(STATE_KEY)
    if not isinstance(state, dict):
        state = {}
        variables[STATE_KEY] = state
        state.update({
            "kind": "clear",
            "until_tick": _next_dawn(tick),
            "term_ordinal": tick // TICKS_PER_TERM,
            "seed": _seed_for(player),
        })
        return state
    if state.get("kind") not in KIND_LABELS:
        state["kind"] = "clear"
    until = state.get("until_tick")
    if not isinstance(until, int) or isinstance(until, bool) or until <= 0:
        state["until_tick"] = _next_dawn(tick)
    ordinal = state.get("term_ordinal")
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        state["term_ordinal"] = tick // TICKS_PER_TERM
    seed = state.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        state["seed"] = _seed_for(player)
    return state


def start_first_day_guide(player):
    """为新角色写入首日引导天气；只在尚未推进的晴天状态上生效。"""
    state = _state(player, 0)
    if state.get("guide") or state.get("kind") != "clear":
        return False
    state["kind"] = "clear"
    state["until_tick"] = FIRST_DAY_GUIDE[0][1]
    state["guide"] = [[kind, start] for kind, start in FIRST_DAY_GUIDE]
    return True


def _guide_step(state, tick):
    """引导天气到点时推进一步，返回新的 until_tick；没有可推进的引导返回 None。"""
    guide = state.get("guide")
    if not isinstance(guide, list) or not guide:
        if "guide" in state:
            state.pop("guide", None)
        return None
    entry = guide[0]
    if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
        state.pop("guide", None)
        return None
    kind, start_tick = entry
    if kind not in KIND_LABELS or not isinstance(start_tick, int) or isinstance(start_tick, bool):
        state.pop("guide", None)
        return None
    if tick < start_tick:
        return None
    guide.pop(0)
    state["kind"] = kind
    until_tick = None
    if guide:
        following = guide[0]
        if isinstance(following, (list, tuple)) and len(following) == 2 and isinstance(following[1], int):
            until_tick = following[1]
        else:
            guide.clear()
    if until_tick is None:
        # 最后一段引导天气持续到下一次黎明之后的正常时长，之后重新按黎明换天。
        dawn = _next_dawn(start_tick)
        until_tick = dawn + _duration_days(state["seed"], dawn) * TICKS_PER_DAY
    if not guide:
        state.pop("guide", None)
    state["until_tick"] = until_tick
    return until_tick


def _pick_kind(seed, until_tick, season, previous):
    table = _WEATHER_TABLES.get(season, _WEATHER_TABLES["春"])
    total = sum(weight for _kind, weight in table)
    roll = zlib.crc32(f"weather:{seed}:{until_tick}".encode("utf-8")) % total
    chosen = table[-1][0]
    for kind, weight in table:
        if roll < weight:
            chosen = kind
            break
        roll -= weight
    if chosen == previous:
        # 同一天气不连续出现，避免“阴了又阴”这类无信息的变化。
        index = [kind for kind, _weight in table].index(chosen)
        for offset in range(1, len(table)):
            candidate = table[(index + offset) % len(table)][0]
            if candidate != previous:
                chosen = candidate
                break
    return chosen


def _duration_days(seed, until_tick):
    return 1 + zlib.crc32(f"weather-duration:{seed}:{until_tick}".encode("utf-8")) % 3


def advance(player, tick):
    """把天气推进到 `tick`，返回 `(当前天气, 是否发生变化)`。

    只在黎明换天；一次跨越多天时只落在抵达时生效的天气上，不补报
    中间过程。超过三年的空档直接落到当前黎明，避免读取异常存档时
    做无意义的长循环。
    """
    tick = _safe_tick(tick)
    state = _state(player, tick)
    until_tick = state["until_tick"]
    if tick < until_tick:
        return state["kind"], False
    if tick - until_tick > _MAX_REPLAY_TICKS:
        until_tick = (tick // TICKS_PER_DAY) * TICKS_PER_DAY
        if until_tick <= 0:
            until_tick = TICKS_PER_DAY
    changed = False
    while tick >= until_tick:
        guided_until = _guide_step(state, tick)
        if guided_until is not None:
            until_tick = guided_until
            changed = True
            continue
        season = season_for_tick(until_tick)
        kind = _pick_kind(state["seed"], until_tick, season, state["kind"])
        state["kind"] = kind
        until_tick = until_tick + _duration_days(state["seed"], until_tick) * TICKS_PER_DAY
        state["until_tick"] = until_tick
        changed = True
    return state["kind"], changed


def current_kind(player, tick=None):
    """只读当前天气；未初始化时按晴天处理。"""
    if tick is None:
        tick = player.get_quest_clock() if hasattr(player, "get_quest_clock") else 0
    return _state(player, _safe_tick(tick))["kind"]


def transition_pending(player, tick):
    """当前 tick 是否已经到达换天时刻（不修改状态）。"""
    tick = _safe_tick(tick)
    return tick >= _state(player, tick)["until_tick"]


def term_is_pending(player, tick):
    """当前 tick 是否已经跨入新节气（不修改状态）。"""
    tick = _safe_tick(tick)
    return tick // TICKS_PER_TERM > _state(player, tick)["term_ordinal"]


def term_message(player, tick):
    """跨入新节气时返回一条文案；旧档初始化与读档回退保持静默。"""
    tick = _safe_tick(tick)
    state = _state(player, tick)
    ordinal = tick // TICKS_PER_TERM
    previous = state["term_ordinal"]
    if ordinal < previous:
        # 读入更早的存档或时间回退时静默对齐，避免之后长期不再播报节气。
        state["term_ordinal"] = ordinal
        return None
    if ordinal == previous:
        return None
    state["term_ordinal"] = ordinal
    index = ordinal % len(TERMS)
    return f"节气已至{TERMS[index]}，{TERM_TEXTS[index]}"


def snapshot(player):
    """状态面板用的天时摘要；不推进世界，也不弹出消息。"""
    tick = _safe_tick(getattr(player, "get_quest_clock", lambda: 0)())
    kind = _state(player, tick)["kind"]
    return {
        "kind": kind,
        "label": KIND_LABELS.get(kind, KIND_LABELS["clear"]),
        "term": term_for_tick(tick),
        "season": season_for_tick(tick),
    }
