# -*- coding: utf-8 -*-
"""NPC 感知后的可执行反应。

反应写在 npcs.json 的 perception_actions 中，条件复用 npc_perception
的 requires/perception 判定；效果只支持 heal_percent 与 region_effects。
once_per_day 按世界日（tick // 24）限制同一 NPC 每天最多触发一次，
记录写入既有 V12 variables.npc_action_days，不新增存档顶层字段。
"""

import engine
import npc_perception
from ui_output import safe_print as print

STATE_KEY = "npc_action_days"
REGION_LABELS = (("security", "安全度"), ("commerce", "商路"), ("travel", "通行"))


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _variables(player):
    state = getattr(player, "world_state", None)
    if not isinstance(state, dict):
        return {}
    variables = state.get("variables")
    return variables if isinstance(variables, dict) else {}


def _world_day(player):
    clock = player.get_quest_clock() if hasattr(player, "get_quest_clock") else 0
    return _safe_int(clock, 0) // 24


def _heal_percent(entry):
    value = entry.get("heal_percent")
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(100, value))


def _region_effects(entry):
    effects = entry.get("region_effects")
    return effects if isinstance(effects, dict) and effects else None


def _has_effect(entry):
    return bool(_heal_percent(entry) or _region_effects(entry))


def select_action(player, npc_data):
    """返回当前状态下优先级最高的可执行反应；没有则返回 None。"""
    if not isinstance(npc_data, dict):
        return None
    entries = npc_data.get("perception_actions")
    if not isinstance(entries, list):
        return None
    snapshot = None
    matched = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not _has_effect(entry):
            continue
        # 没有感知条件的反应会退化成无条件奖励，按无效条目跳过。
        if "perception" not in entry:
            continue
        if snapshot is None:
            snapshot = npc_perception.build_snapshot(player)
        if not npc_perception.entry_matches(player, entry, snapshot):
            continue
        priority = _safe_int(entry.get("priority", 0), 0)
        matched.append((priority, -index, index, entry))
    if not matched:
        return None
    return max(matched, key=lambda row: (row[0], row[1]))[3]


def _already_today(player, npc_name):
    days = _variables(player).get(STATE_KEY)
    if not isinstance(days, dict):
        return False
    return _safe_int(days.get(npc_name), -1) == _world_day(player)


def _mark_today(player, npc_name):
    state = getattr(player, "world_state", None)
    if not isinstance(state, dict):
        return
    variables = state.setdefault("variables", {})
    if not isinstance(variables, dict):
        return
    days = variables.get(STATE_KEY)
    if not isinstance(days, dict):
        days = {}
        variables[STATE_KEY] = days
    days[npc_name] = _world_day(player)


def _apply_heal(player, percent):
    max_hp = max(1, _safe_int(getattr(player, "max_hp", 1), 1))
    hp = max(0, _safe_int(getattr(player, "hp", 0), 0))
    gained = min(max_hp, hp + max_hp * percent // 100) - hp
    if gained > 0:
        player.hp = hp + gained
    return gained


def _apply_region_effects(player, region_effects):
    report = {}
    engine.apply_world_effects(player.world_state, {"region_effects": region_effects}, report)
    applied = report.get("region_effects")
    return applied if isinstance(applied, dict) else {}


def _print_result(result):
    if result["text"]:
        print(f"{engine.Color.CYAN}{result['text']}{engine.Color.RESET}")
    if result["heal"]:
        print(f"{engine.Color.GREEN}气血恢复 {result['heal']} 点。{engine.Color.RESET}")
    regions = getattr(engine, "WORLD_REGIONS", {}) or {}
    for zone, changes in result["region_effects"].items():
        labels = [f"{label} {changes[field]:+d}" for field, label in REGION_LABELS
                  if isinstance(changes.get(field), int) and changes.get(field)]
        if not labels:
            continue
        name = str((regions.get(zone) or {}).get("name", zone))
        print(f"{engine.Color.CYAN}区域变化：{name} {'、'.join(labels)}{engine.Color.RESET}")


def run_talk_action(player, npc_name, npc_data):
    """执行当前命中的感知反应；返回结果字典，未触发时返回 None。"""
    entry = select_action(player, npc_data)
    if entry is None:
        return None
    if entry.get("once_per_day") and _already_today(player, npc_name):
        return None
    result = {
        "id": str(entry.get("id") or ""),
        "text": str(entry.get("text") or "").strip(),
        "heal": 0,
        "region_effects": {},
    }
    heal_percent = _heal_percent(entry)
    if heal_percent:
        result["heal"] = _apply_heal(player, heal_percent)
    region_effects = _region_effects(entry)
    if region_effects:
        result["region_effects"] = _apply_region_effects(player, region_effects)
    if entry.get("once_per_day"):
        _mark_today(player, npc_name)
    _print_result(result)
    return result
