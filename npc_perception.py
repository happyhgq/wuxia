# -*- coding: utf-8 -*-
"""NPC 对玩家与环境状态的只读感知。

对白写在 npcs.json 的 conditional_dialogue 中，NPC 也可通过
perception_role 引用 data/perception_templates.json 的职业模板。
条目可提供 text 或 variants，并额外提供 perception 规则；只有
requires 与 perception 同时满足时才会被选中。快照构建不写存档、
不推进世界时间、不初始化天气；variants 的轮换游标只挂在玩家对象
的临时属性上，不进入 V12 存档。
"""

import engine
import weather
from world_time import world_hour

TIME_PHASES = ("dawn", "day", "dusk", "night")
INJURY_LEVELS = ("healthy", "wounded", "badly_wounded")
QUALITY_ORDER = ("普通", "精良", "稀有", "史诗")
WEATHER_KINDS = ("clear", "cloudy", "rain", "storm", "snow", "fog")
EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")
PERCEPTION_KEYS = ("time_phase", "weather", "injury", "hp_percent", "equipment_quality")

_WOUNDED_BELOW = 70
_BADLY_WOUNDED_BELOW = 35


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def quality_rank(quality):
    return QUALITY_ORDER.index(quality) if quality in QUALITY_ORDER else 0


def time_phase(hour):
    """把 0~23 的钟点归入清晨/白日/黄昏/夜晚。"""
    hour = _safe_int(hour, 0) % 24
    if 5 <= hour < 9:
        return "dawn"
    if 9 <= hour < 17:
        return "day"
    if 17 <= hour < 20:
        return "dusk"
    return "night"


def injury_level(hp_percent):
    hp_percent = _safe_int(hp_percent, 0)
    if hp_percent < _BADLY_WOUNDED_BELOW:
        return "badly_wounded"
    if hp_percent < _WOUNDED_BELOW:
        return "wounded"
    return "healthy"


def _read_weather(player):
    state = getattr(player, "world_state", None)
    variables = state.get("variables", {}) if isinstance(state, dict) else {}
    record = variables.get(weather.STATE_KEY) if isinstance(variables, dict) else None
    kind = record.get("kind") if isinstance(record, dict) else None
    return kind if kind in WEATHER_KINDS else "clear"


def build_snapshot(player):
    """返回 NPC 可感知的玩家与环境事实；只读，不写回任何对象。"""
    tick = player.get_quest_clock() if hasattr(player, "get_quest_clock") else 0
    hour = world_hour(tick)
    try:
        max_hp = max(1, int(getattr(player, "max_hp", 1)))
        hp = max(0, int(getattr(player, "hp", 0)))
    except (TypeError, ValueError):
        max_hp, hp = 1, 0
    hp_percent = max(0, min(100, hp * 100 // max_hp))
    equipment = getattr(player, "equipment", {}) or {}
    if not isinstance(equipment, dict):
        equipment = {}
    qualities = {}
    for slot in EQUIPMENT_SLOTS:
        item_name = equipment.get(slot)
        info = engine.ITEMS.get(item_name, {}) if item_name else {}
        quality = info.get("quality") if isinstance(info, dict) else None
        qualities[slot] = quality if quality in QUALITY_ORDER else "普通"
    return {
        "hour": hour,
        "time_phase": time_phase(hour),
        "weather": _read_weather(player),
        "hp_percent": hp_percent,
        "injury": injury_level(hp_percent),
        "equipment_quality": qualities,
        "best_equipment_quality": max(qualities.values(), key=quality_rank),
    }


def _compare_quality(value, rule):
    if isinstance(rule, str):
        # 字符串表示最低品质，避免数据里反复写 gte。
        return quality_rank(value) >= quality_rank(rule)
    if isinstance(rule, dict):
        rank = quality_rank(value)
        for op, expected in rule.items():
            if expected not in QUALITY_ORDER:
                return False
            expected_rank = quality_rank(expected)
            if op == "eq" and value != expected:
                return False
            if op == "gte" and rank < expected_rank:
                return False
            if op == "gt" and rank <= expected_rank:
                return False
            if op == "lte" and rank > expected_rank:
                return False
            if op == "lt" and rank >= expected_rank:
                return False
            if op not in {"eq", "gte", "gt", "lte", "lt"}:
                return False
        return bool(rule)
    return False


def _match_enum(value, rule):
    if isinstance(rule, (list, tuple, set)):
        return value in rule
    if isinstance(rule, dict):
        allowed = rule.get("in")
        forbidden = rule.get("not_in")
        if allowed is not None and value not in allowed:
            return False
        if forbidden is not None and value in forbidden:
            return False
        return allowed is not None or forbidden is not None
    return value == rule


def _equipment_quality_matches(snapshot, rules):
    if not isinstance(rules, dict) or not rules:
        return False
    for slot, rule in rules.items():
        if slot == "best":
            value = snapshot["best_equipment_quality"]
        elif slot in EQUIPMENT_SLOTS:
            value = snapshot["equipment_quality"].get(slot, "普通")
        else:
            return False
        if not _compare_quality(value, rule):
            return False
    return True


def _perception_matches(snapshot, rules):
    if not isinstance(rules, dict) or not rules:
        return True
    for key, rule in rules.items():
        if key == "time_phase":
            if not _match_enum(snapshot["time_phase"], rule):
                return False
        elif key == "weather":
            if not _match_enum(snapshot["weather"], rule):
                return False
        elif key == "injury":
            if not _match_enum(snapshot["injury"], rule):
                return False
        elif key == "hp_percent":
            if not engine.compare_rule(snapshot["hp_percent"], rule):
                return False
        elif key == "equipment_quality":
            if not _equipment_quality_matches(snapshot, rule):
                return False
        else:
            # 未知键失败关闭，避免数据拼写错误导致条件被静默忽略。
            return False
    return True


def entry_matches(player, entry, snapshot=None):
    """判断条件对白条目是否同时满足 requires 与 perception。"""
    if not isinstance(entry, dict):
        return False
    if not engine.check_conditions(entry.get("requires"), player.world_state, player.completed_quests, player):
        return False
    rules = entry.get("perception")
    if rules is None:
        return True
    if snapshot is None:
        snapshot = build_snapshot(player)
    return _perception_matches(snapshot, rules)


def npc_entries(npc_data, include_templates=True):
    """NPC 专属条件对白在前，职业模板在后；同优先级时专属台词优先。"""
    entries = list(npc_data.get("conditional_dialogue", []) or [])
    role = npc_data.get("perception_role")
    if include_templates and isinstance(role, str) and role:
        templates = getattr(engine, "PERCEPTION_TEMPLATES", {}) or {}
        role_entries = templates.get(role, []) if isinstance(templates, dict) else []
        if isinstance(role_entries, list):
            entries.extend(role_entries)
    return entries


def _entry_texts(entry):
    variants = entry.get("variants")
    if isinstance(variants, list):
        texts = [text for text in variants if isinstance(text, str) and text.strip()]
        if texts:
            return texts
    text = entry.get("text")
    if isinstance(text, str) and text.strip():
        return [text]
    return []


def _stable_seed(text):
    seed = 0
    for char in text:
        seed = (seed * 131 + ord(char)) % 2147483647
    return seed


def _reaction_cursor(player):
    cursors = getattr(player, "_npc_reaction_cursor", None)
    if isinstance(cursors, dict):
        return cursors
    cursors = {}
    try:
        setattr(player, "_npc_reaction_cursor", cursors)
    except AttributeError:
        return {}
    return cursors


def _variant_index(player, npc_name, entry_index, count):
    """同一玩家会话内轮换变体；游标不落存档，重载后按世界时辰重新起算。"""
    key = (str(npc_name or ""), int(entry_index))
    cursors = _reaction_cursor(player)
    last = cursors.get(key)
    if isinstance(last, int) and count > 1:
        index = (last + 1) % count
    else:
        tick = player.get_quest_clock() if hasattr(player, "get_quest_clock") else 0
        index = (_safe_int(tick, 0) + _stable_seed(f"{key[0]}|{key[1]}")) % count
    cursors[key] = index
    return index


def _pick_text(player, npc_name, entry_index, texts):
    if len(texts) == 1:
        return texts[0]
    return texts[_variant_index(player, npc_name, entry_index, len(texts))]


def select_reaction_text(player, npc_data, npc_name=None, include_templates=True):
    """返回当前状态下优先级最高的条件对白或模板台词；没有则返回 None。"""
    if not isinstance(npc_data, dict):
        return None
    name = npc_name or npc_data.get("name") or npc_data.get("title") or ""
    matched = []
    snapshot = None
    for index, entry in enumerate(npc_entries(npc_data, include_templates)):
        if not isinstance(entry, dict):
            continue
        texts = _entry_texts(entry)
        if not texts:
            continue
        if entry.get("perception") is not None and snapshot is None:
            snapshot = build_snapshot(player)
        if not entry_matches(player, entry, snapshot):
            continue
        priority = _safe_int(entry.get("priority", 0), 0)
        matched.append((priority, -index, index, texts))
    if not matched:
        return None
    _, _, index, texts = max(matched, key=lambda row: (row[0], row[1]))
    return _pick_text(player, name, index, texts)
