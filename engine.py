# -*- coding: utf-8 -*-
"""
engine.py - 动态地图引擎、状态机制与 DataLoader
"""

import json
import os
import random
import sys
import re
import time
import unicodedata
import warnings
from copy import deepcopy
from collections import deque
from ui_output import safe_print as print

if os.name == "nt":
    os.system("")

# ==================== 全局路径与版本常量 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAVE_PATH = os.path.join(DATA_DIR, "save.json")
SAVE_VERSION = 12

p_statuses_global = {}

# ==================== 战斗概率基础规则 ====================
# P2.3：保持规则简单、可解释，并为后续装备/武学词条留下扩展空间。
COMBAT_DEFAULTS = {
    "hit": 0.90,          # 基础命中率
    "crit": 0.08,         # 基础暴击率
    "dodge": 0.05,        # 基础闪避率
    "crit_multiplier": 1.50,
    "min_hit": 0.55,
    "max_hit": 0.98,
}

# 旧存档房间 Key 别名映射字典
LEGACY_LOCATION_MAP = {
    "cave": "cave_entrance",
    "bandit_camp": "bandit_courtyard",
}


# ==================== 存档迁移与世界状态基础 ====================
WORLD_STATE_DEFAULT = {
    "flags": {},
    "variables": {},
}

RELATION_DEFAULTS = {
    "neutral": 0,
    "friendly": 20,
    "trusted": 50,
    "devoted": 80,
    "hostile": -30,
}

RELATION_LABELS = {
    "hostile": "敌对",
    "neutral": "中立",
    "friendly": "友善",
    "trusted": "信任",
    "devoted": "亲近",
}

RELATION_MIN = -100
RELATION_MAX = 100
DEFAULT_TALK_RELATION_CAP = 10

def relation_status(value):
    """统一 NPC 关系等级判定，供 Player/UI/条件系统复用。"""
    try:
        value = max(RELATION_MIN, min(RELATION_MAX, int(value)))
    except (TypeError, ValueError):
        value = 0
    if value <= RELATION_DEFAULTS["hostile"]:
        return RELATION_LABELS["hostile"]
    if value < RELATION_DEFAULTS["friendly"]:
        return RELATION_LABELS["neutral"]
    if value < RELATION_DEFAULTS["trusted"]:
        return RELATION_LABELS["friendly"]
    if value < RELATION_DEFAULTS["devoted"]:
        return RELATION_LABELS["trusted"]
    return RELATION_LABELS["devoted"]

def relation_behavior(value):
    """根据关系值返回 NPC 的行为层级。

    关系等级与关系行为分离：-30 进入冷淡、-60 拒绝合作、-80 敌对，
    正向关系则继续由对话/任务条件决定具体内容。
    """
    try:
        value = max(RELATION_MIN, min(RELATION_MAX, int(value)))
    except (TypeError, ValueError):
        value = 0
    if value <= -80:
        return "hostile"
    if value <= -60:
        return "refuse"
    if value <= -30:
        return "cold"
    if value >= 80:
        return "devoted"
    if value >= 50:
        return "trusted"
    if value >= 20:
        return "friendly"
    return "normal"


def compare_rule(value, rule):
    """统一比较规则；非法规则返回 False，避免剧情条件异常放行。"""
    try:
        value = int(value)
        if isinstance(rule, dict):
            for op, expected in rule.items():
                expected = int(expected)
                if op == "eq" and value != expected: return False
                if op == "ne" and value == expected: return False
                if op == "gte" and value < expected: return False
                if op == "gt" and value <= expected: return False
                if op == "lte" and value > expected: return False
                if op == "lt" and value >= expected: return False
                if op not in {"eq", "ne", "gte", "gt", "lte", "lt"}: return False
            return True
        return value >= int(rule)
    except (TypeError, ValueError):
        return False

DEFAULT_SECTS = {}

DEFAULT_FACTIONS = {}

DEFAULT_WORLD_REGIONS = {
    "main": {"name": "主世界", "recommended_level": 1, "danger": "normal"},
    "bandit_zone": {"name": "黑风寨", "recommended_level": 5, "danger": "dangerous"},
    "guiyun_city": {"name": "归云城", "recommended_level": 6, "danger": "normal"},
}



def _normalise_world_state(raw_state):
    """将任意旧/异常世界状态规范化为稳定的 v12 结构。"""
    if not isinstance(raw_state, dict):
        raw_state = {}
    flags = raw_state.get("flags", {})
    variables = raw_state.get("variables", {})
    if not isinstance(flags, dict):
        flags = {}
    if not isinstance(variables, dict):
        variables = {}
    return {"flags": dict(flags), "variables": dict(variables)}


_MAX_SAVE_COUNTER = 2_000_000_000


def _save_int(value):
    """把存档中的数值转成整数；布尔、字符串和溢出值返回 None。"""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _save_float(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalise_region_activity(raw):
    """区域治安记录会被巡逻、清剿和长周期恢复共用，逐层收敛不可用数值。"""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for zone, row in raw.items():
        if not isinstance(zone, str) or not isinstance(row, dict):
            continue
        clean = dict(row)
        for key in ("security", "commerce", "travel"):
            if key in clean:
                value = _save_int(clean.get(key))
                clean[key] = max(-60, min(30, value)) if value is not None else 0
        for key in ("last_recovery", "last_crime_clock", "last_security_event_clock"):
            if key in clean:
                value = _save_int(clean.get(key))
                clean[key] = max(0, min(_MAX_SAVE_COUNTER, value)) if value is not None else 0
        events = clean.get("events")
        if "events" in clean and not isinstance(events, dict):
            clean["events"] = {}
        elif isinstance(events, dict):
            safe_events = {}
            for event_key, event_row in events.items():
                if not isinstance(event_key, str) or not isinstance(event_row, dict):
                    continue
                safe_event = dict(event_row)
                if "last_reward_clock" in safe_event:
                    value = _save_int(safe_event.get("last_reward_clock"))
                    safe_event["last_reward_clock"] = (
                        max(-999999, min(_MAX_SAVE_COUNTER, value)) if value is not None else -999999
                    )
                safe_events[event_key] = safe_event
            clean["events"] = safe_events
        incident = clean.get("security_incident")
        if incident is not None and not isinstance(incident, dict):
            clean.pop("security_incident", None)
        elif isinstance(incident, dict):
            safe_incident = dict(incident)
            for key, default, low, high in (
                ("started_clock", 0, 0, _MAX_SAVE_COUNTER),
                ("expires_clock", 0, 0, _MAX_SAVE_COUNTER),
                ("completed_clock", 0, 0, _MAX_SAVE_COUNTER),
                ("progress", 0, 0, 1_000_000),
                ("required_patrols", 1, 1, 1000),
            ):
                if key in safe_incident:
                    value = _save_int(safe_incident.get(key))
                    safe_incident[key] = max(low, min(high, value)) if value is not None else default
            if "status" in safe_incident and not isinstance(safe_incident["status"], str):
                safe_incident["status"] = "expired"
            if "contributors" in safe_incident and not isinstance(safe_incident["contributors"], list):
                safe_incident["contributors"] = []
            if "result_text" in safe_incident and not isinstance(safe_incident["result_text"], str):
                safe_incident["result_text"] = ""
            clean["security_incident"] = safe_incident
        result[zone] = clean
    return result


_WORLD_CRISIS_CLOCK_FIELDS = {
    "started_clock": 0,
    "expires_clock": 0,
    "ended_clock": 0,
    "recovery_end_clock": 0,
    "last_npc_response_clock": -999999,
    "last_player_action_clock": -999999,
    "last_criminal_defeat_clock": -999999,
}


def _normalise_world_crises(raw):
    """危机计时被多个系统直接读取，损坏的字符串会让世界 Tick 在载入后崩溃。"""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for crisis_id, row in raw.items():
        if not isinstance(crisis_id, str) or not isinstance(row, dict):
            continue
        clean = dict(row)
        for key, default in _WORLD_CRISIS_CLOCK_FIELDS.items():
            if key in clean:
                value = _save_int(clean.get(key))
                clean[key] = max(-999999, min(_MAX_SAVE_COUNTER, value)) if value is not None else default
        for key in ("npc_relief", "player_relief"):
            if key in clean:
                value = _save_float(clean.get(key))
                clean[key] = max(0.0, min(0.70, value)) if value is not None else 0.0
        if "effects" in clean and not isinstance(clean["effects"], dict):
            clean["effects"] = {}
        for key in ("npc_response", "player_action", "escalation"):
            if key in clean and not isinstance(clean[key], dict):
                clean[key] = {}
        if "status" in clean and not isinstance(clean["status"], str):
            clean["status"] = "ended"
        if "escalated" in clean:
            clean["escalated"] = clean["escalated"] is True
        result[crisis_id] = clean
    return result


_INFORMATION_TEXT_FIELDS = {"topic": "", "text": "", "source": "", "sentiment": "neutral"}


def _normalise_information_record(record):
    """情报记录供任务条件、势力行动和 NPC 传播同时读取，字段类型必须稳定。"""
    if not isinstance(record, dict):
        return None
    clean = dict(record)
    for key, fallback in _INFORMATION_TEXT_FIELDS.items():
        if key in clean and not isinstance(clean[key], str):
            clean[key] = fallback
    if "confidence" in clean:
        confidence = _save_int(clean.get("confidence"))
        clean["confidence"] = max(0, min(100, confidence)) if confidence is not None else 50
    for key in ("learned_at", "expires_at"):
        if key in clean:
            value = _save_int(clean.get(key))
            if value is None:
                clean.pop(key)
            else:
                clean[key] = max(0, min(_MAX_SAVE_COUNTER, value))
    return clean


def _normalise_world_variables(variables):
    """修复 V12 中会被多个系统共用的动态状态。

    读档只检查 world_state 是对象还不够：世界时钟、区域生态或危机计时若是
    字符串，读档仍会提示成功，却在下一个世界 Tick 崩溃。这里不改写合法数值，
    只把无法继续运行的分支收敛为安全值。
    """
    if not isinstance(variables, dict):
        return

    if "quest_clock" in variables:
        clock = _save_int(variables.get("quest_clock"))
        variables["quest_clock"] = max(0, min(_MAX_SAVE_COUNTER, clock if clock is not None else 0))
    if "world_crisis_last_roll" in variables:
        last_roll = _save_int(variables.get("world_crisis_last_roll"))
        variables["world_crisis_last_roll"] = (
            max(-999999, min(_MAX_SAVE_COUNTER, last_roll if last_roll is not None else -999999))
        )

    ecology = variables.get("region_ecology")
    if isinstance(ecology, dict):
        safe_ecology = {}
        for zone, row in ecology.items():
            if not isinstance(zone, str) or not isinstance(row, dict):
                continue
            clean = dict(row)
            for key in ("security", "commerce", "travel"):
                if key in clean:
                    value = _save_int(clean.get(key))
                    if value is None:
                        clean.pop(key)
                    else:
                        clean[key] = max(0, min(100, value))
            for key in ("tension", "last_change"):
                if key in clean:
                    value = _save_int(clean.get(key))
                    if value is None:
                        clean.pop(key)
                    else:
                        clean[key] = max(0, min(_MAX_SAVE_COUNTER, value))
            safe_ecology[zone] = clean
        variables["region_ecology"] = safe_ecology
    elif ecology is not None:
        variables["region_ecology"] = {}

    activity = variables.get("region_activity")
    if activity is not None:
        variables["region_activity"] = _normalise_region_activity(activity)

    crises = variables.get("world_crises")
    if crises is not None:
        variables["world_crises"] = _normalise_world_crises(crises)

    locations = variables.get("npc_locations")
    if isinstance(locations, dict):
        safe_locations = {}
        for npc_name, row in locations.items():
            if not isinstance(npc_name, str) or not isinstance(row, dict):
                continue
            clean = dict(row)
            if "location" in clean and not isinstance(clean["location"], str):
                clean.pop("location")
            if "source" in clean and not isinstance(clean["source"], str):
                clean["source"] = ""
            for key in ("until_clock", "last_schedule_move_clock"):
                if key in clean:
                    value = _save_int(clean.get(key))
                    clean[key] = max(0, min(_MAX_SAVE_COUNTER, value)) if value is not None else 0
            safe_locations[npc_name] = clean
        variables["npc_locations"] = safe_locations
    elif locations is not None:
        variables["npc_locations"] = {}

    autonomy = variables.get("npc_autonomy")
    if isinstance(autonomy, dict):
        safe_autonomy = {}
        for npc_name, row in autonomy.items():
            if not isinstance(npc_name, str) or not isinstance(row, dict):
                continue
            clean = dict(row)
            history = clean.get("proactive_events")
            if "proactive_events" in clean and not isinstance(history, dict):
                clean["proactive_events"] = {}
            elif isinstance(history, dict):
                safe_history = {}
                for event_id, last_clock in history.items():
                    if not isinstance(event_id, str):
                        continue
                    value = _save_int(last_clock)
                    if value is not None:
                        safe_history[event_id] = max(-999999, min(_MAX_SAVE_COUNTER, value))
                clean["proactive_events"] = safe_history
            if "last_action_clock" in clean:
                value = _save_int(clean.get("last_action_clock"))
                clean["last_action_clock"] = (
                    max(-999999, min(_MAX_SAVE_COUNTER, value)) if value is not None else -999999
                )
            for key in ("last_action", "target", "location"):
                if key in clean and not isinstance(clean[key], str):
                    clean[key] = ""
            safe_autonomy[npc_name] = clean
        variables["npc_autonomy"] = safe_autonomy
    elif autonomy is not None:
        variables["npc_autonomy"] = {}

    npc_information = variables.get("npc_information")
    if npc_information is not None:
        safe_npc_information = {}
        if isinstance(npc_information, dict):
            for npc_name, bucket in npc_information.items():
                if not isinstance(npc_name, str) or not isinstance(bucket, dict):
                    continue
                clean_bucket = {}
                for topic, record in bucket.items():
                    if not isinstance(topic, str):
                        continue
                    clean_record = _normalise_information_record(record)
                    if clean_record is not None:
                        clean_bucket[topic] = clean_record
                safe_npc_information[npc_name] = clean_bucket
        variables["npc_information"] = safe_npc_information

    player_information = variables.get("player_information")
    if player_information is not None:
        safe_player_information = {}
        if isinstance(player_information, dict):
            for topic, record in player_information.items():
                if not isinstance(topic, str):
                    continue
                clean_record = _normalise_information_record(record)
                if clean_record is not None:
                    safe_player_information[topic] = clean_record
        variables["player_information"] = safe_player_information

    faction_actions = variables.get("faction_actions")
    if isinstance(faction_actions, dict):
        safe_actions = {}
        for faction_name, row in faction_actions.items():
            if not isinstance(faction_name, str) or not isinstance(row, dict):
                continue
            clean = dict(row)
            history = clean.get("history")
            if "history" in clean and not isinstance(history, dict):
                clean["history"] = {}
            elif isinstance(history, dict):
                safe_history = {}
                for action_id, last_clock in history.items():
                    if not isinstance(action_id, str):
                        continue
                    value = _save_int(last_clock)
                    if value is not None:
                        safe_history[action_id] = max(-999999, min(_MAX_SAVE_COUNTER, value))
                clean["history"] = safe_history
            safe_actions[faction_name] = clean
        variables["faction_actions"] = safe_actions
    elif faction_actions is not None:
        variables["faction_actions"] = {}

    conflicts = variables.get("faction_conflicts")
    if isinstance(conflicts, dict):
        safe_conflicts = {}
        for key, row in conflicts.items():
            if not isinstance(key, str) or not isinstance(row, dict):
                continue
            clean = dict(row)
            for field, low, high in (("relation", -100, 100), ("pressure", 0, 200), ("last_change", 0, _MAX_SAVE_COUNTER)):
                if field in clean:
                    value = _save_int(clean.get(field))
                    clean[field] = max(low, min(high, value)) if value is not None else low
            history = clean.get("history")
            if "history" in clean:
                clean["history"] = (
                    [entry for entry in history if isinstance(entry, dict)]
                    if isinstance(history, list) else []
                )
                del clean["history"][:-20]
            safe_conflicts[key] = clean
        variables["faction_conflicts"] = safe_conflicts
    elif conflicts is not None:
        variables["faction_conflicts"] = {}

    if "dynamic_world_stability" in variables:
        stability = variables.get("dynamic_world_stability")
        if not isinstance(stability, dict):
            variables["dynamic_world_stability"] = {}
        else:
            clean_stability = dict(stability)
            recovery = clean_stability.get("faction_recovery")
            if "faction_recovery" in clean_stability:
                if isinstance(recovery, dict):
                    safe_recovery = {}
                    for key, last_clock in recovery.items():
                        if not isinstance(key, str):
                            continue
                        value = _save_int(last_clock)
                        if value is not None:
                            safe_recovery[key] = max(-9999, min(_MAX_SAVE_COUNTER, value))
                    clean_stability["faction_recovery"] = safe_recovery
                else:
                    clean_stability["faction_recovery"] = {}
            variables["dynamic_world_stability"] = clean_stability

    for history_key in ("quest_interventions", "quest_competitions"):
        if history_key not in variables:
            continue
        history = variables.get(history_key)
        if not isinstance(history, dict):
            variables[history_key] = {}
        else:
            safe_history = {}
            for key, last_clock in history.items():
                if not isinstance(key, str):
                    continue
                value = _save_int(last_clock)
                if value is not None:
                    safe_history[key] = max(-999999, min(_MAX_SAVE_COUNTER, value))
            variables[history_key] = safe_history

    for log_key in ("faction_action_log", "faction_conflict_log", "npc_action_log",
                    "npc_proactive_events", "region_security_log",
                    "pending_world_crisis_announcements"):
        if log_key in variables and not isinstance(variables[log_key], list):
            variables[log_key] = []


def migrate_save_data(data):
    """把 v1-v10 存档安全迁移到当前版本。

    迁移只补充新字段、修正已知旧位置别名，不主动删除玩家数据。
    未知房间仍回退到村口，避免旧存档因世界扩展直接损坏。
    """
    if not isinstance(data, dict):
        raise ValueError("存档根节点必须是 JSON 对象")

    migrated = deepcopy(data)
    # 名称与门派是展示/身份字段。JSON 虽可解析，但若被手工改成列表、
    # 对象或 null，后续身份初始化可能失败；用安全默认值保持旧档可读。
    raw_name = migrated.get("name", "无名侠客")
    migrated["name"] = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else "无名侠客"
    raw_sect = migrated.get("sect", "散人")
    migrated["sect"] = raw_sect.strip() if isinstance(raw_sect, str) and raw_sect.strip() else "散人"
    try:
        old_version = int(migrated.get("version", 1))
    except (TypeError, ValueError):
        old_version = 1

    # 核心数值也可能来自手工编辑或异常中断后的旧存档；统一转成有限整数，
    # 避免读档表面成功、随后在战斗/升级/交易中因字符串或布尔值崩溃。
    def _safe_int_field(key, default, minimum=None, maximum=None):
        value = migrated.get(key, default)
        try:
            if isinstance(value, bool):
                raise ValueError("布尔值不是有效数值")
            value = int(value)
        except (TypeError, ValueError, OverflowError):
            value = default
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        migrated[key] = value

    _safe_int_field("level", 1, minimum=1, maximum=100000)
    _safe_int_field("exp", 0, minimum=0)
    _safe_int_field("exp_to_level", 50, minimum=1)
    _safe_int_field("max_hp", 100, minimum=1)
    _safe_int_field("max_mp", 50, minimum=0)
    _safe_int_field("hp", 100, minimum=0)
    _safe_int_field("mp", 50, minimum=0)
    _safe_int_field("atk", 10, minimum=0)
    _safe_int_field("defense", 5, minimum=0)
    _safe_int_field("gold", 50, minimum=0)
    migrated["hp"] = min(migrated["hp"], migrated["max_hp"])
    migrated["mp"] = min(migrated["mp"], migrated["max_mp"])

    raw_loc = migrated.get("location", "village_gate")
    mapped_loc = LEGACY_LOCATION_MAP.get(raw_loc, raw_loc)
    if mapped_loc not in ROOMS:
        mapped_loc = "village_gate"
    migrated["location"] = mapped_loc

    # 规范化核心容器字段。旧版或手工损坏的存档中，单个字段类型错误不应
    # 导致整个角色无法读取；无法恢复的可选容器使用安全默认值。
    if not isinstance(migrated.get("active_quests"), dict):
        migrated["active_quests"] = {}
    if not isinstance(migrated.get("completed_quests"), list):
        migrated["completed_quests"] = []
    if not isinstance(migrated.get("inventory"), list):
        migrated["inventory"] = []
    if not isinstance(migrated.get("equipment"), dict):
        migrated["equipment"] = {"weapon": None, "armor": None}
    else:
        equipment = migrated["equipment"]
        # 槽位值也必须是可哈希的物品名；合法 JSON 中的列表/对象会令 ITEMS.get 崩溃。
        migrated["equipment"] = {
            slot: (equipment.get(slot) if isinstance(equipment.get(slot), str) and equipment.get(slot).strip() else None)
            for slot in ("weapon", "armor")
        }
    if not isinstance(migrated.get("equip_enhance"), dict):
        migrated["equip_enhance"] = {"weapon": 0, "armor": 0}
    else:
        enhancements = migrated["equip_enhance"]
        safe_enhancements = {}
        for slot in ("weapon", "armor"):
            try:
                safe_enhancements[slot] = max(0, int(enhancements.get(slot, 0)))
            except (TypeError, ValueError, OverflowError):
                safe_enhancements[slot] = 0
        migrated["equip_enhance"] = safe_enhancements

    # v11: 正式引入 world_state；v12: 正式引入 quest_states。
    migrated["world_state"] = _normalise_world_state(migrated.get("world_state"))
    _normalise_world_variables(migrated["world_state"]["variables"])

    # v12: 阶段任务状态持久化。除字段类型外，还要约束阶段/进度范围，
    # 否则合法 JSON 中的超范围数字可能绕过任务交付校验或令分支逻辑失效。
    quest_states = migrated.get("quest_states", {})
    if not isinstance(quest_states, dict):
        quest_states = {}
    else:
        safe_quest_states = {}
        for q_name, raw_state in quest_states.items():
            if not isinstance(q_name, str) or not isinstance(raw_state, dict):
                continue
            state = deepcopy(raw_state)
            try:
                stage_idx = int(state.get("stage", 0))
                if isinstance(state.get("stage", 0), bool):
                    raise ValueError("布尔值不是阶段编号")
            except (TypeError, ValueError, OverflowError):
                stage_idx = 0
            try:
                progress = int(state.get("progress", 0))
                if isinstance(state.get("progress", 0), bool):
                    raise ValueError("布尔值不是任务进度")
            except (TypeError, ValueError, OverflowError):
                progress = 0
            stage_idx = max(0, stage_idx)
            progress = max(0, progress)
            q_info = QUESTS.get(q_name, {})
            stages = q_info.get("stages") or []
            # 分支标记必须是 JSON 布尔真值；字符串 "false" 不得被当作 True。
            had_branch_pending = "branch_pending" in state
            if stages:
                # 无效阶段不应被夹到最后一阶段，否则可能把坏存档变成可领奖任务。
                if stage_idx >= len(stages):
                    stage_idx, progress = 0, 0
                    state.pop("branch", None)
                    state["branch_pending"] = False
                elif had_branch_pending:
                    state["branch_pending"] = state.get("branch_pending") is True
                # 保留旧 V12 档中已保存的合法进度，不按当前任务数据强行回退；
                # 仅限制极端整数，避免异常存档携带无界数值。
                progress = min(progress, 1_000_000)
            elif had_branch_pending:
                state["branch_pending"] = False
            state["stage"] = stage_idx
            state["progress"] = progress
            if "accepted_at" in state:
                try:
                    accepted_at = int(state["accepted_at"])
                    if isinstance(state["accepted_at"], bool):
                        raise ValueError("布尔值不是时钟")
                    state["accepted_at"] = max(0, accepted_at)
                except (TypeError, ValueError, OverflowError):
                    state["accepted_at"] = 0
            if "branch" in state and not isinstance(state["branch"], str):
                state.pop("branch", None)
            safe_quest_states[q_name] = state
        quest_states = safe_quest_states
    active_quests = migrated.get("active_quests", {})
    if not isinstance(active_quests, dict):
        active_quests = {}
        migrated["active_quests"] = active_quests
    else:
        safe_active_quests = {}
        for q_name, progress in active_quests.items():
            if not isinstance(q_name, str):
                continue
            try:
                value = int(progress)
                if isinstance(progress, bool):
                    raise ValueError("布尔值不是进度")
                safe_active_quests[q_name] = max(0, value)
            except (TypeError, ValueError, OverflowError):
                safe_active_quests[q_name] = 0
        active_quests = safe_active_quests
        migrated["active_quests"] = active_quests
    # 去重完成列表；不可重复任务若同时出现在 active/completed 中，以已完成为准。
    completed = []
    seen_completed = set()
    for q_name in migrated["completed_quests"]:
        if isinstance(q_name, str) and q_name not in seen_completed:
            completed.append(q_name)
            seen_completed.add(q_name)
    # V12 旧档/剧情脚本可能只写入 quest_completed:<任务名> 旗标，未同步
    # completed_quests 列表。两种完成记录必须统一，否则公告栏认为已完成，
    # 接取入口却可能允许重接并再次领取一次性奖励。
    flags = migrated["world_state"].get("flags", {})
    for q_name in QUESTS:
        if flags.get(f"quest_completed:{q_name}") is True and q_name not in seen_completed:
            completed.append(q_name)
            seen_completed.add(q_name)
    migrated["completed_quests"] = completed
    for q_name in list(active_quests):
        q_info = QUESTS.get(q_name, {})
        if q_name in seen_completed and not q_info.get("repeatable", False):
            active_quests.pop(q_name, None)
            quest_states.pop(q_name, None)
            flags[f"quest_active:{q_name}"] = False
    migrated["inventory"] = [item for item in migrated["inventory"] if isinstance(item, str)]
    for q_name, progress in list(active_quests.items()):
        q_info = QUESTS.get(q_name, {})
        stages = q_info.get("stages") or []
        if stages and q_name not in quest_states:
            # 旧 V12 档可能只有 active_quests；恢复时保留其已有进度。
            quest_states[q_name] = {"stage": 0, "progress": min(max(0, int(progress)), 1_000_000), "branch_pending": False}
        if stages and q_name in quest_states:
            # 对阶段任务以规范化后的 quest_states 为准；待选分支时沿用既有约定，
            # active_quests 进度显示为 0，实际已达成进度保留在 quest_states 中。
            state = quest_states[q_name]
            active_quests[q_name] = 0 if state.get("branch_pending") is True else state.get("progress", 0)
    migrated["quest_states"] = quest_states
    migrated["version"] = SAVE_VERSION

    # 为未来条件系统留下稳定的基础访问记录；不强制写入大量内容。
    flags = migrated["world_state"]["flags"]
    flags.setdefault("visited:village_gate", mapped_loc == "village_gate")
    return migrated, old_version


def get_world_flag(world_state, key, default=False):
    state = _normalise_world_state(world_state)
    return state["flags"].get(key, default)


def set_world_flag(world_state, key, value=True):
    state = _normalise_world_state(world_state)
    state["flags"][key] = value
    world_state.clear()
    world_state.update(state)
    return value


def get_world_var(world_state, key, default=0):
    state = _normalise_world_state(world_state)
    return state["variables"].get(key, default)


def quest_display_name(quest_name):
    """返回玩家可见的任务名称；内部键只用于存档、旗标与逻辑判断。"""
    info = QUESTS.get(quest_name)
    if isinstance(info, dict):
        title = str(info.get("title", "") or "").strip()
        if title:
            return title
    return str(quest_name)


def quest_aliases(quest_name):
    """返回任务可用于指令匹配的名称：内部键、显示名与配置别名。"""
    aliases = [str(quest_name), quest_display_name(quest_name)]
    info = QUESTS.get(quest_name)
    if isinstance(info, dict):
        configured = info.get("aliases")
        if isinstance(configured, list):
            aliases.extend(str(alias) for alias in configured if str(alias).strip())
    return list(dict.fromkeys(alias for alias in aliases if alias))


def quest_prerequisite_text(player, quest_name):
    """前置任务提示必须与判定一致：完成目标不等于已交付。"""
    title = quest_display_name(quest_name)
    active_quests = getattr(player, "active_quests", {}) if player is not None else {}
    if quest_name in active_quests:
        checker = getattr(player, "is_quest_goal_complete", None)
        if callable(checker) and checker(quest_name):
            return f"需先交付【{title}】"
        return f"需先完成并交付【{title}】"
    return f"需先完成并交付【{title}】"


def check_conditions(conditions, world_state, completed_quests=None, player=None):
    """数据驱动条件判断。

    P2.12 在保留旧 flags/variables/completed_quests 语义的基础上，增加
    level、gold、items 三类玩家条件。player 为可选参数，因此旧调用完全兼容。
    """
    if not conditions:
        return True
    completed_quests = set(completed_quests or [])
    state = _normalise_world_state(world_state)
    # 玩家属性条件必须有玩家上下文；缺失上下文时失败关闭，避免 any 分支绕过路线/关系门槛。
    player_condition_keys = {
        "honor", "infamy", "jianghu_paths", "level", "gold", "sect", "sect_reputation",
        "faction_relations", "skills", "items", "relations", "npc_memory",
        "npc_memory_attitude", "npc_information", "npc_states",
    }
    if player is None and any(key in conditions for key in player_condition_keys):
        return False

    for key in conditions.get("flags", []):
        if state["flags"].get(key, False):
            continue
        # 完成列表与完成旗标都是“已交付”的合法记录；任一存在即视为已交付，
        # 避免旧档/剧情脚本只写其中一处时，前置判断与实际状态不一致。
        if key.startswith("quest_completed:") and key.split(":", 1)[1] in completed_quests:
            continue
        return False
    for key in conditions.get("not_flags", []):
        if state["flags"].get(key, False):
            return False
    for q_name in conditions.get("completed_quests", []):
        if q_name in completed_quests:
            continue
        if state["flags"].get(f"quest_completed:{q_name}", False):
            continue
        return False

    for key, rule in conditions.get("variables", {}).items():
        value = state["variables"].get(key, 0)
        if isinstance(rule, dict):
            if "eq" in rule and value != rule["eq"]: return False
            if "ne" in rule and value == rule["ne"]: return False
            if "gte" in rule and value < rule["gte"]: return False
            if "gt" in rule and value <= rule["gt"]: return False
            if "lte" in rule and value > rule["lte"]: return False
            if "lt" in rule and value >= rule["lt"]: return False
        elif value != rule:
            return False

    if player is not None:
        # P3.1.6：侠名、恶名与路线倾向可以直接作为任务/剧情条件。
        # 统一使用 compare_rule，非法条件一律不放行；旧条件未配置时行为不变。
        profile_getter = getattr(player, "_jianghu_profile", None)
        profile = profile_getter() if callable(profile_getter) else {}
        for field, profile_key in (("honor", "honor"), ("infamy", "infamy")):
            rule = conditions.get(field)
            if rule is not None and not compare_rule(profile.get(profile_key, 0), rule):
                return False
        path_rules = conditions.get("jianghu_paths", {}) or {}
        if not isinstance(path_rules, dict):
            return False
        paths = profile.get("paths", {}) if isinstance(profile, dict) else {}
        for path_name, rule in path_rules.items():
            if path_name not in getattr(player, "JIANGHU_PATHS", ()):
                return False
            if not compare_rule(paths.get(path_name, 0), rule):
                return False

        level_rule = conditions.get("level")
        if level_rule is not None:
            level = int(getattr(player, "level", 0))
            if isinstance(level_rule, dict):
                if "eq" in level_rule and level != level_rule["eq"]: return False
                if "gte" in level_rule and level < level_rule["gte"]: return False
                if "gt" in level_rule and level <= level_rule["gt"]: return False
                if "lte" in level_rule and level > level_rule["lte"]: return False
                if "lt" in level_rule and level >= level_rule["lt"]: return False
            elif level < int(level_rule):
                return False

        gold_rule = conditions.get("gold")
        if gold_rule is not None:
            gold = int(getattr(player, "gold", 0))
            if isinstance(gold_rule, dict):
                if "eq" in gold_rule and gold != gold_rule["eq"]: return False
                if "gte" in gold_rule and gold < gold_rule["gte"]: return False
                if "gt" in gold_rule and gold <= gold_rule["gt"]: return False
                if "lte" in gold_rule and gold > gold_rule["lte"]: return False
                if "lt" in gold_rule and gold >= gold_rule["lt"]: return False
            elif gold < int(gold_rule):
                return False

        sect_rule = conditions.get("sect")
        if sect_rule is not None:
            current_sect = getattr(player, "get_sect", lambda: getattr(player, "sect", "散人"))()
            if isinstance(sect_rule, list):
                if current_sect not in sect_rule:
                    return False
            elif isinstance(sect_rule, dict):
                allowed = sect_rule.get("in")
                forbidden = sect_rule.get("not_in")
                if allowed is not None and current_sect not in allowed:
                    return False
                if forbidden is not None and current_sect in forbidden:
                    return False
            elif current_sect != str(sect_rule):
                return False

        for sect_name, rule in conditions.get("sect_reputation", {}).items():
            rep = getattr(player, "get_sect_reputation", lambda _name: 0)(sect_name)
            if not compare_rule(rep, rule):
                return False

        faction_rules = conditions.get("faction_relations", {}) or {}
        if not isinstance(faction_rules, dict):
            return False
        get_faction_relation = getattr(player, "get_faction_relation", lambda _a, _b: 0)
        for pair, rule in faction_rules.items():
            if isinstance(pair, str) and ":" in pair:
                faction_a, faction_b = pair.split(":", 1)
            elif isinstance(pair, (list, tuple)) and len(pair) == 2:
                faction_a, faction_b = pair
            else:
                return False
            if not compare_rule(get_faction_relation(str(faction_a), str(faction_b)), rule):
                return False

        # P2.25：任务可以要求已掌握指定武学，并可继续要求最低武学等级/熟练度。
        skill_rules = conditions.get("skills", {}) or {}
        if not isinstance(skill_rules, dict):
            return False
        for skill_name, rule in skill_rules.items():
            progress = getattr(player, "get_skill_progress", lambda _name: {"learned": False, "level": 0, "mastery": 0})(skill_name)
            if not progress.get("learned", False):
                return False
            if isinstance(rule, dict):
                if "level" in rule and not compare_rule(progress.get("level", 0), rule["level"]):
                    return False
                if "mastery" in rule and not compare_rule(progress.get("mastery", 0), rule["mastery"]):
                    return False
            elif isinstance(rule, (int, float)) and progress.get("level", 0) < int(rule):
                return False

        for item_name, required in conditions.get("items", {}).items():
            try:
                required = int(required)
            except (TypeError, ValueError):
                return False
            if required < 0 or player.inventory.count(item_name) < required:
                return False

        relation_rules = conditions.get("relations", {}) or {}
        if relation_rules:
            for npc_name, rule in relation_rules.items():
                value = player.get_relation(npc_name) if player is not None and hasattr(player, "get_relation") else 0
                if not compare_rule(value, rule):
                    return False

        # P2.32：任务/剧情可要求玩家已掌握指定 NPC 信息。
        # P2.33：NPC 对玩家的记忆/评价可以成为剧情与任务条件。
        memory_rules = conditions.get("npc_memory", {}) or {}
        if memory_rules:
            if player is None or not hasattr(player, "get_npc_memory"):
                return False
            if not isinstance(memory_rules, dict):
                return False
            for npc_name, rules in memory_rules.items():
                if not isinstance(rules, dict):
                    return False
                for memory_id, rule in rules.items():
                    record = player.get_npc_memory(npc_name, memory_id)
                    if record is None:
                        return False
                    if isinstance(rule, dict):
                        if "min_strength" in rule and int(record.get("strength", 0)) < int(rule["min_strength"]):
                            return False
                        if "sentiment" in rule and record.get("sentiment") != rule["sentiment"]:
                            return False
                    elif rule not in (True, None):
                        return False
        memory_attitude_rules = conditions.get("npc_memory_attitude", {}) or {}
        if memory_attitude_rules:
            if player is None or not hasattr(player, "get_npc_memory_attitude") or not isinstance(memory_attitude_rules, dict):
                return False
            for npc_name, expected in memory_attitude_rules.items():
                if player.get_npc_memory_attitude(npc_name) != str(expected):
                    return False

        information_rules = conditions.get("npc_information", {}) or {}
        if information_rules:
            if player is None or not hasattr(player, "get_player_information") or not isinstance(information_rules, dict):
                return False
            for topic, rule in information_rules.items():
                record = player.get_player_information(topic)
                if record is None:
                    return False
                if isinstance(rule, dict):
                    if "min_confidence" in rule:
                        confidence = _save_int(record.get("confidence", 0))
                        minimum = _save_int(rule["min_confidence"])
                        if confidence is None or minimum is None or confidence < minimum:
                            return False
                    if "sentiment" in rule and record.get("sentiment") != rule["sentiment"]:
                        return False
                elif rule not in (True, None):
                    return False

        # P2.28：NPC 当前生态状态可以作为任务/剧情条件；状态保存在既有 world_state.variables。
        npc_state_rules = conditions.get("npc_states", {}) or {}
        if npc_state_rules:
            if player is None or not hasattr(player, "get_npc_state"):
                return False
            if not isinstance(npc_state_rules, dict):
                return False
            for npc_name, rule in npc_state_rules.items():
                current = player.get_npc_state(npc_name)
                if isinstance(rule, (list, tuple, set)):
                    if current not in rule:
                        return False
                elif current != str(rule):
                    return False

    # P3.1.7：支持 any 条件组；组内至少一项满足即可，其余顶层条件仍须全部满足。
    if "any" in conditions:
        alternatives = conditions.get("any")
        if not isinstance(alternatives, list) or not alternatives:
            return False
        if not any(isinstance(option, dict) and check_conditions(option, world_state, completed_quests, player)
                   for option in alternatives):
            return False
    return True


def _describe_condition_rule(rule):
    """把数值条件转成玩家可读的短句，避免把条件字典原样暴露给玩家。"""
    if isinstance(rule, dict):
        labels = {"gte": "至少", "gt": "高于", "lte": "不高于", "lt": "低于", "eq": "等于", "ne": "不等于"}
        parts = [f"{labels[op]} {expected}" for op, expected in rule.items() if op in labels]
        return "且".join(parts) if parts else "符合要求"
    return f"达到 {rule}"


PROGRESS_FLAG_HINTS = {
    "case:missing_person:started": "需先接下城内失踪案的调查",
    "case:missing_person:finished": "先完成失踪案调查并确认线索",
    "case:missing_person:black_market_route": "需先在失踪案中选择黑市调查路线",
    "quest:mistwood_herbs:resolved": "先查明雾隐林道失药案",
    "sunken_ruins:caravan_truth_known": "先查明沉河旧商队的真相",
    "world:trade_network:transfer_chain_traced": "先查清商路转运链",
    "northfront:trade_route_safe": "先确认北境商路安全",
    "quest:transfer_warehouse:resolved": "先查明暗仓转运疑云",
    "world:trade_network:warehouse_evidence_secured": "先取得暗仓实证",
    "world:trade_network:warehouse_reviewed": "先完成暗仓实证核验",
    "quest:jianghu_chessboard:started": "先启动暗潮主线调查",
    "world:trade_network:route_official": "需先在暗潮调查中选择官府路线",
    "world:trade_network:route_blackmarket": "需先在暗潮调查中选择黑市路线",
    "world:trade_network:route_dual": "需先在暗潮调查中选择双线并行路线",
    "newcomer:guide_seen": "先与青石村接引人完成初入江湖指引",
    "world:main:herb_trade_resumed": "先确认百草堂已恢复收药",
    "world:main:mistwood_boardwalk_repaired": "先修好雾隐林道木栈道",
    "world:main:abandoned_mine_supply_secured": "先为废弃铁矿补足矿料",
    "sect:shaolin:ordination:novice": "需先完成少林入门受戒",
    "sect:shaolin:ordination:full": "需先完成少林正式受戒",
    "sect:shaolin:scripture_catalogue_reviewed": "需先到少林藏经阁外院向守阁僧了解藏经目录与阅览规矩",
    "sect:wudang:sword_principle": "需先完成《武当剑理·松间问道》，领悟武当以静制动、后发制人的剑理",
    "sect:wudang:questline:inner_breath_done": "需先完成《武当内功·紫霄听息》，打好武当内功根基",
    "sect:huashan:sword_principle": "需先完成《华山剑理·松风听剑》，领悟华山剑路中的攻守取舍",
    "sect:huashan:questline:patrol_done": "需先完成《华山巡剑·古道清障》",
    "sect:tieyi:trade_route": "需先完成《铁衣门护运·商路问价》，摸清商路车次与货单",
    "sect:tieyi:questline:escort_done": "需先完成《铁衣门守约·短途护送》",
}


def explain_condition_failures(conditions, world_state, completed_quests=None, player=None):
    """以简短中文解释常见剧情条件未满足的原因；未知条件不猜测。"""
    if not isinstance(conditions, dict) or not conditions or check_conditions(conditions, world_state, completed_quests, player):
        return []
    state = _normalise_world_state(world_state)
    completed = set(completed_quests or [])
    messages = []
    flags = conditions.get("flags", [])
    if isinstance(flags, list):
        # 任务前提前统一使用自然语言。未知标记只说明“前置剧情未完成”，
        # 不再把 world:/sect:/quest: 之类的内部键名直接展示给玩家。
        public_flag_names = PROGRESS_FLAG_HINTS
        for flag in flags:
            if state["flags"].get(flag, False):
                continue
            flag_text = str(flag)
            if flag_text.startswith("quest_completed:"):
                prior = flag_text.split(":", 1)[1]
                if prior in completed:
                    continue
                messages.append(quest_prerequisite_text(player, prior))
            elif flag_text in public_flag_names:
                messages.append(public_flag_names[flag_text])
            elif flag_text.startswith("quest:"):
                messages.append("需要先推进相关委托")
            elif flag_text.startswith("visited_zone:"):
                zone_names = {"guiyun_city": "归云城"}
                zone = flag_text.split(":", 1)[1]
                messages.append(f"需要先到访【{zone_names.get(zone, zone)}】")
            elif flag_text.startswith("sect:") and ":rank:" in flag_text:
                parts = flag_text.split(":")
                try:
                    rank_index = int(parts[-1])
                except (TypeError, ValueError):
                    rank_index = 0
                sect_key = parts[1] if len(parts) > 1 else ""
                sect_name = {
                    "shaolin": "少林", "wudang": "武当",
                    "huashan": "华山", "tieyi": "铁衣门",
                }.get(sect_key, sect_key)
                sect_info = SECTS.get(sect_name, {}) if isinstance(SECTS, dict) else {}
                ranks = sect_info.get("ranks", []) if isinstance(sect_info, dict) else []
                if 0 <= rank_index < len(ranks):
                    messages.append(f"需先晋升为【{sect_name}·{ranks[rank_index].get('name', '更高身份')}】")
                else:
                    messages.append("需先取得相应的门派身份")
            elif flag_text.startswith("sect:"):
                messages.append("需先完成相关门派仪礼或取得相应身份")
            elif flag_text.startswith("world:") or flag_text.startswith("case:") or flag_text.startswith("northfront:"):
                messages.append("当前世界局势尚未满足此委托的前置条件")
            else:
                messages.append("尚有前置剧情尚未完成")
    not_flags = conditions.get("not_flags", [])
    if isinstance(not_flags, list):
        for flag in not_flags:
            if state["flags"].get(flag, False): messages.append("当前状态不允许接下或继续此委托")
    quests = conditions.get("completed_quests", [])
    if isinstance(quests, list):
        for quest in quests:
            if quest in completed or state["flags"].get(f"quest_completed:{quest}", False):
                continue
            messages.append(quest_prerequisite_text(player, quest))
    variables = conditions.get("variables", {})
    if isinstance(variables, dict):
        for key, rule in variables.items():
            value = state["variables"].get(key, 0)
            if not _condition_value_matches(value, rule):
                messages.append(f"世界局势尚未满足（当前 {value}，需{_describe_condition_rule(rule)}）")
    if player is not None:
        profile = getattr(player, "_jianghu_profile", lambda: {})()
        for field in ("honor", "infamy"):
            rule = conditions.get(field)
            if rule is not None and not compare_rule(profile.get(field, 0), rule):
                messages.append(f"{('侠义值' if field == 'honor' else '恶名')}需{_describe_condition_rule(rule)}（当前 {profile.get(field, 0)}）")
        paths = conditions.get("jianghu_paths", {})
        if isinstance(paths, dict):
            for name, rule in paths.items():
                if name in getattr(player, "JIANGHU_PATHS", ()) and not compare_rule(profile.get("paths", {}).get(name, 0), rule):
                    messages.append(f"【{name}】路线倾向需{_describe_condition_rule(rule)}（当前 {profile.get('paths', {}).get(name, 0)}）")
        relations = conditions.get("relations", {})
        if isinstance(relations, dict):
            for name, rule in relations.items():
                current = getattr(player, "get_relation", lambda _name: 0)(name)
                if not compare_rule(current, rule):
                    messages.append(f"与【{name}】的关系需{_describe_condition_rule(rule)}（当前 {current}）")
        for sect_name, rule in (conditions.get("sect_reputation", {}) or {}).items():
            current = getattr(player, "get_sect_reputation", lambda _name: 0)(sect_name)
            if not compare_rule(current, rule):
                messages.append(f"门派【{sect_name}】声望需{_describe_condition_rule(rule)}（当前 {current}）")
        level_rule = conditions.get("level")
        if level_rule is not None and not compare_rule(getattr(player, "level", 0), level_rule):
            messages.append(f"等级需{_describe_condition_rule(level_rule)}（当前 {getattr(player, 'level', 0)}）")
        sect_rule = conditions.get("sect")
        if sect_rule is not None:
            current_sect = getattr(player, "get_sect", lambda: getattr(player, "sect", "散人"))()
            allowed = sect_rule.get("in") if isinstance(sect_rule, dict) else sect_rule
            forbidden = sect_rule.get("not_in", []) if isinstance(sect_rule, dict) else []
            if isinstance(allowed, list):
                if current_sect not in allowed:
                    messages.append(f"当前门派为【{current_sect}】，要求门派为【{'、'.join(map(str, allowed))}】")
            elif allowed is not None and current_sect != str(allowed):
                messages.append(f"当前门派为【{current_sect}】，要求加入【{allowed}】")
            if forbidden and current_sect in forbidden:
                messages.append(f"当前门派【{current_sect}】不符合此委托要求")
        for skill_name, rule in (conditions.get("skills", {}) or {}).items():
            progress = getattr(player, "get_skill_progress", lambda _name: {"learned": False, "level": 0, "mastery": 0})(skill_name)
            if not progress.get("learned", False):
                messages.append(f"尚未掌握武学【{skill_name}】")
                continue
            if isinstance(rule, dict):
                for field, label in (("level", "等级"), ("mastery", "熟练度")):
                    requirement = rule.get(field)
                    current = progress.get(field, 0)
                    if requirement is not None and not compare_rule(current, requirement):
                        messages.append(f"武学【{skill_name}】{label}需{_describe_condition_rule(requirement)}（当前 {current}）")
        for item_name, required in (conditions.get("items", {}) or {}).items():
            current = player.inventory.count(item_name) if player is not None and isinstance(getattr(player, "inventory", None), list) else 0
            if current < int(required):
                messages.append(f"物品【{item_name}】当前 {current}/{required}")
        gold_rule = conditions.get("gold")
        if gold_rule is not None and not compare_rule(getattr(player, "gold", 0), gold_rule):
            messages.append(f"银两需{_describe_condition_rule(gold_rule)}（当前 {getattr(player, 'gold', 0)}）")
    alternatives = conditions.get("any")
    if isinstance(alternatives, list) and alternatives and not any(
        isinstance(option, dict) and check_conditions(option, world_state, completed, player) for option in alternatives
    ):
        choices = []
        for option in alternatives:
            failures = explain_condition_failures(option, world_state, completed, player)
            choices.append("且".join(failures[:2]) if failures else "该条件组")
        messages.append("以下条件至少满足一项：" + "；或".join(choices))
    return messages[:8]


def _condition_value_matches(value, rule):
    if isinstance(rule, dict):
        try:
            for op, expected in rule.items():
                if op == "eq" and value != expected: return False
                if op == "ne" and value == expected: return False
                if op == "gte" and value < expected: return False
                if op == "gt" and value <= expected: return False
                if op == "lte" and value > expected: return False
                if op == "lt" and value >= expected: return False
                if op not in {"eq", "ne", "gte", "gt", "lte", "lt"}: return False
            return True
        except (TypeError, ValueError):
            return False
    return value == rule


def apply_world_effects(world_state, effects, report=None):
    """执行任务/剧情世界效果，并防止异常配置导致状态只写入一半。

    report 传入 dict 时记录本次实际生效的 region_effects，供结算反馈使用。
    """
    if not effects:
        return world_state
    if not isinstance(effects, dict):
        return world_state
    for field in ("set_flags", "set_variables", "increment_variables", "faction_relations", "relations", "region_effects"):
        value = effects.get(field, {})
        if value is not None and not isinstance(value, dict):
            return world_state
    state = _normalise_world_state(world_state)
    for key, value in effects.get("set_flags", {}).items():
        state["flags"][key] = value
    for key, value in effects.get("set_variables", {}).items():
        state["variables"][key] = value
    for key, amount in effects.get("increment_variables", {}).items():
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            continue
        current = state["variables"].get(key, 0)
        if isinstance(current, bool) or not isinstance(current, (int, float)):
            current = 0
        state["variables"][key] = current + amount
    faction_relation_effects = effects.get("faction_relations", {}) or {}
    if isinstance(faction_relation_effects, dict):
        faction_map = state["variables"].setdefault("faction_relations", {})
        if not isinstance(faction_map, dict):
            faction_map = {}
            state["variables"]["faction_relations"] = faction_map
        for pair, delta in faction_relation_effects.items():
            if isinstance(pair, str) and ":" in pair:
                a, b = pair.split(":", 1)
            elif isinstance(pair, (list, tuple)) and len(pair) == 2:
                a, b = pair
            else:
                continue
            if a not in FACTIONS or b not in FACTIONS or a == b:
                continue
            try:
                current = faction_map.get(f"{a}:{b}", FACTIONS[a].get("relations", {}).get(b, 0))
                value = max(-100, min(100, int(current) + int(delta)))
            except (TypeError, ValueError):
                continue
            faction_map[f"{a}:{b}"] = value
            faction_map[f"{b}:{a}"] = value

    relation_effects = effects.get("relations", {}) or {}
    if relation_effects:
        relation_map = state["variables"].setdefault("npc_relations", {})
        if not isinstance(relation_map, dict):
            relation_map = {}
            state["variables"]["npc_relations"] = relation_map
        for npc_name, delta in relation_effects.items():
            try:
                relation_map[npc_name] = max(-100, min(100, int(relation_map.get(npc_name, 0)) + int(delta)))
            except (TypeError, ValueError):
                continue
    region_effects = effects.get("region_effects", {}) or {}
    if region_effects:
        from region_activity import apply_region_effects
        applied = apply_region_effects(state, region_effects)
        if applied and isinstance(report, dict):
            recorded = report.setdefault("region_effects", {})
            if isinstance(recorded, dict):
                for zone, changes in applied.items():
                    zone_changes = recorded.setdefault(zone, {})
                    if isinstance(zone_changes, dict):
                        for field, delta in changes.items():
                            zone_changes[field] = zone_changes.get(field, 0) + delta
    world_state.clear()
    world_state.update(state)
    return world_state


def set_world_var(world_state, key, value):
    state = _normalise_world_state(world_state)
    state["variables"][key] = value
    world_state.clear()
    world_state.update(state)
    return value


# ==================== ANSI 颜色代码 ====================
def _strict_color_mode():
    if getattr(sys.flags, "dev_mode", False):
        return True
    return os.environ.get("WUXIA_STRICT_COLORS", "").strip().lower() in {"1", "true", "yes", "on"}


class _ColorMeta(type):
    """未知颜色常量不再直接崩溃；记录告警后回退，开发模式下仍显式报错。"""

    def __getattr__(cls, name):
        if name.startswith("_"):
            raise AttributeError(name)
        message = f"未定义的颜色常量 Color.{name}，已回退为 RESET；请补全 engine.Color 定义。"
        warnings.warn(message, RuntimeWarning, stacklevel=2)
        if _strict_color_mode():
            raise AttributeError(message)
        return cls.RESET


class Color(metaclass=_ColorMeta):
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"


def color_text(text, color_name="RESET"):
    """按名称取色并包裹文本；未知颜色名告警后回退 RESET，避免输出非法转义串。"""
    code = vars(Color).get(color_name) if isinstance(color_name, str) else None
    if not isinstance(code, str) or not code.startswith("\033["):
        warnings.warn(
            f"未知颜色名 {color_name!r}，已回退为 RESET。",
            RuntimeWarning,
            stacklevel=2,
        )
        code = Color.RESET
    return f"{code}{text}{Color.RESET}"


# 语义色表：界面按用途取色，避免同一语义在不同模块出现不同颜色。
# 空串表示正文不额外着色；正文保持中性，只给关键词与结果上色。
ROLE_COLORS = {
    "body": "",
    "muted": Color.WHITE,
    "title": Color.BRIGHT_CYAN,
    "heading": Color.BOLD,
    "hint": Color.CYAN,
    "success": Color.BRIGHT_GREEN,
    "failure": Color.RED,
    "warning": Color.YELLOW,
    "gain": Color.BRIGHT_GREEN,
    "loss": Color.RED,
    "npc": Color.BRIGHT_CYAN,
    "enemy": Color.BRIGHT_RED,
    "exit": Color.BRIGHT_CYAN,
    "item": Color.GREEN,
    "quest": Color.BRIGHT_YELLOW,
    "system": Color.CYAN,
    "damage": Color.BRIGHT_RED,
    "heal": Color.BRIGHT_GREEN,
    "crit": "\033[1;91m",
    "phase": Color.BRIGHT_MAGENTA,
    "skill": Color.CYAN,
}


def style(text, role="body"):
    """按语义角色给文本上色；未知角色与正文保持原样，颜色开关由输出层统一处理。"""
    code = ROLE_COLORS.get(str(role), "")
    if not code:
        return str(text)
    return f"{code}{text}{Color.RESET}"


def clear_screen():
    # 非交互式运行或终端未配置 TERM 时不调用外部清屏命令，避免把环境警告打印给玩家。
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return
    if os.name != 'nt' and not os.environ.get('TERM'):
        return
    os.system('cls' if os.name == 'nt' else 'clear')


BATTLE_SPEED = 0.6


def battle_pause(seconds):
    time.sleep(seconds * BATTLE_SPEED)


# ==================== 字符显示宽度与补全函数 ====================
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def get_display_width(s):
    """计算终端可见宽度：忽略 ANSI 控制序列与组合附加符，中文全角按两列计。"""
    visible = _ANSI_ESCAPE_RE.sub("", str(s))
    width = 0
    for ch in visible:
        # 组合符不占独立列；常见中文全角/宽字符按两列计。
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        if ch == "🚪" or unicodedata.east_asian_width(ch) in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def pad_to_width(s, target_width, align="center"):
    curr_w = get_display_width(s)
    if curr_w >= target_width:
        return s
    missing = target_width - curr_w
    if align == "center":
        left = missing // 2
        right = missing - left
        return " " * left + s + " " * right
    elif align == "left":
        return s + " " * missing
    else:
        return " " * missing + s


def draw_bar(current, max_val, length=10, fill_color=Color.GREEN, empty_color=Color.WHITE):
    if max_val <= 0:
        pct = 0
    else:
        pct = max(0, min(1, current / max_val))
    filled_len = int(length * pct)
    empty_len = length - filled_len
    bar_str = fill_color + "█" * filled_len + empty_color + "░" * empty_len + Color.RESET
    return f"[{bar_str}] {current}/{max_val}"


# ==================== 状态机制 ====================
STATUS_EFFECTS = {
    "poison": {"name": "中毒", "color": Color.GREEN},
    "bleed":  {"name": "流血", "color": Color.RED},
    "stun":   {"name": "眩晕", "color": Color.YELLOW},
    "shield": {"name": "护体", "color": Color.BLUE},
    "armor_break": {"name": "破防", "color": Color.MAGENTA},
    "damage_reduction": {"name": "卸力", "color": Color.CYAN},
}


def clear_statuses():
    p_statuses_global.clear()


def add_status(statuses, name, turns, value=0):
    if not name:
        return
    if name in statuses:
        statuses[name]["turns"] = max(statuses[name]["turns"], turns)
        statuses[name]["value"] = max(statuses[name]["value"], value)
    else:
        statuses[name] = {"turns": turns, "value": value}


def process_status_effects(statuses):
    hp_change = 0
    stunned = False
    messages = []
    expired = []

    for name, info in list(statuses.items()):
        meta = STATUS_EFFECTS.get(name, {})
        c = meta.get("color", Color.WHITE)
        n = meta.get("name", name)

        if name in ("poison", "bleed"):
            hp_change -= info["value"]
            messages.append(f"{c}【{n}】损失 {info['value']} 点气血{Color.RESET}")
        elif name == "stun":
            stunned = True
            messages.append(f"{c}【{n}】受制无法行动！{Color.RESET}")

        info["turns"] -= 1
        if info["turns"] <= 0:
            expired.append(name)

    for name in expired:
        meta = STATUS_EFFECTS.get(name, {})
        messages.append(f"{meta.get('color', '')}【{meta.get('name', name)}】状态解除。{Color.RESET}")
        del statuses[name]

    return hp_change, stunned, messages


def format_statuses(statuses):
    if not statuses:
        return f"{Color.WHITE}无{Color.RESET}"
    parts = []
    for name, info in statuses.items():
        meta = STATUS_EFFECTS.get(name, {})
        c = meta.get("color", Color.WHITE)
        n = meta.get("name", name)
        turns = info.get("turns", 0)
        val = info.get("value", 0)
        val_str = f":{val}" if val > 0 else ""
        parts.append(f"{c}{n}({turns}{val_str}){Color.RESET}")
    return "  ".join(parts)


def get_effective_defense(base_defense, statuses):
    """根据战斗中的破防状态计算当前有效防御。"""
    if "armor_break" not in statuses:
        return max(0, int(base_defense))
    return max(0, int(base_defense) - int(statuses["armor_break"].get("value", 0)))


def apply_damage_reduction(statuses, raw_damage):
    """应用卸力状态；返回最终伤害。"""
    if "damage_reduction" not in statuses:
        return max(0, int(raw_damage))
    pct = max(0, min(90, int(statuses["damage_reduction"].get("value", 0))))
    return max(0, int(raw_damage * (100 - pct) / 100))


def apply_shield(statuses, raw_damage):
    if "shield" not in statuses:
        return raw_damage

    sh_val = statuses["shield"]["value"]
    if sh_val >= raw_damage:
        statuses["shield"]["value"] -= raw_damage
        print(f"{Color.BLUE}你的【护体真气】吸收了全部 {raw_damage} 点伤害！（剩余护盾: {statuses['shield']['value']}）{Color.RESET}")
        return 0
    else:
        remaining_dmg = raw_damage - sh_val
        del statuses["shield"]
        print(f"{Color.BLUE}你的【护体真气】吸收了 {sh_val} 点伤害后破碎！{Color.RESET}")
        return remaining_dmg


# ==================== 默认基础数据配置 ====================
DEFAULT_ROOMS = {
    "village_gate": {
        "name": "青石村口", "zone": "main",
        "desc": "一座破旧的木牌楼立在道旁，匾额上“青石村”三字被风雨侵蚀得斑驳。牌楼下靠着个打盹的守卫。往北进入青石长街，往南则是黄土官道。",
        "exits": {"北": "village_south_street", "南": "official_road"},
        "npcs": ["守卫"], "safe": True, "coord": [2, 1]
    },
    "village_south_street": {
        "name": "青石长街", "zone": "main",
        "desc": "青石板路两侧排列着矮小的民居。西侧挂着“悦来客栈”的招牌，东侧则是一家杂货铺。北边直通村中广场，南边是村口。",
        "exits": {"北": "village_square", "南": "village_gate", "西": "inn", "东": "general_shop"},
        "safe": True, "coord": [2, 2]
    },
    "inn": {
        "name": "悦来客栈", "zone": "main",
        "desc": "堂中灯油昏黄，掌柜支颐倚在柜台后拨弄算盘，小二在收拾桌椅。东边大门通往青石长街。",
        "exits": {"东": "village_south_street"},
        "npcs": ["掌柜", "店小二"], "safe": True, "coord": [1, 2]
    },
    "general_shop": {
        "name": "杂货铺", "zone": "main",
        "desc": "货架上摆满了日用杂物与行脚干粮。杂货铺老板正笑脸迎人。西边是大门。",
        "exits": {"西": "village_south_street"}, "npcs": ["杂货铺老板"], "safe": True, "coord": [3, 2]
    },
    "village_square": {
        "name": "村中广场", "zone": "main",
        "desc": "这里是青石村最宽阔的集散地，中央耸立着一棵百年老榕树。西边是百草堂，东边是打铁铺，南接青石长街，北通青石后街。",
        "exits": {"北": "village_north_street", "南": "village_south_street", "西": "medicine_shop", "东": "blacksmith"},
        "safe": True, "coord": [2, 3]
    },
    "medicine_shop": {
        "name": "百草堂", "zone": "main",
        "desc": "一进门便能闻到浓郁的药香。墙上密密麻麻排着药柜，老板垂首研磨金创药。东边是大门。",
        "exits": {"东": "village_square"}, "npcs": ["药铺老板"], "safe": True, "coord": [1, 3]
    },
    "blacksmith": {
        "name": "打铁铺", "zone": "main",
        "desc": "炉火通红，热浪扑面。铁匠赤膊抡锤，火星四溅。（输入“打造”可强化兵刃或防具）西边通往村中广场。",
        "exits": {"西": "village_square"}, "npcs": ["铁匠"], "safe": True, "coord": [3, 3]
    },
    "village_north_street": {
        "name": "青石后街", "zone": "main",
        "desc": "青石后街比村口清静，石板路顺着坡度缓缓向上。西侧是村长住宅，正北方向是一座古庙。",
        "exits": {"北": "temple", "南": "village_square", "西": "village_head_house"}, "safe": True, "coord": [2, 4]
    },
    "village_head_house": {
        "name": "村长宅院", "zone": "main",
        "desc": "一座朴素的四合小院，青苔爬满石阶。正房里白发村长负手而立，眉宇间带着几分愁容。",
        "exits": {"东": "village_north_street"}, "npcs": ["村长"], "safe": True, "coord": [1, 4]
    },
    "temple": {
        "name": "古庙", "zone": "main",
        "desc": "古庙颓败，朱漆剥落。室内清幽无人，只有半截石佛立于堂中。这里是打坐恢复绝佳之地，可驱散病邪。（输入“打坐”调息恢复）",
        "exits": {"南": "village_north_street"}, "safe": True, "coord": [2, 5]
    },
    "official_road": {
        "name": "黄土官道", "zone": "main",
        "desc": "黄土官道上车辙深深，两侧野草没膝。北边回青石村，西边有一条荒僻小径通往村后荒野。（先输入“搜索”发现资源，再输入“采集”获取）",
        "exits": {"北": "village_gate", "西": "wild_fields"},
        "enemies": ["野猪"], "forage": {"草药": 0.4}, "coord": [2, 0]
    },
    "wild_fields": {
        "name": "村后荒野", "zone": "main",
        "desc": "杂草丛生，偶有野兽低吼。东边接官道，西边是一条蜿蜒入山的黑风山道。",
        "exits": {"东": "official_road", "西": "mountain_path"},
        "enemies": ["野狼", "野猪"], "forage": {"草药": 0.5}, "coord": [1, 0]
    },
    "mountain_path": {
        "name": "黑风山道", "zone": "main",
        "desc": "山道狭窄，两侧崖壁嶙峋，山风穿谷而过。东边回村后荒野，北边直抵山贼寨门。（搜索调查遗落物资；采集资源请先搜索发现，再采集获取）",
        "exits": {"东": "wild_fields", "北": "cave_entrance"},
        "enemies": ["毒蛇", "山贼"], "forage": {"蛇胆": 0.3}, "coord": [0, 0]
    },
    "cave_entrance": {
        "name": "山贼寨门", "zone": "main",
        "desc": "一座用粗木和兽骨扎成的寨门矗立在前，守备森严。南下为黑风山道，往北跨过寨门即踏入黑风寨内部。",
        "exits": {"南": "mountain_path", "北": "bandit_courtyard"}, "enemies": ["山贼"], "coord": [0, 1]
    },
    "bandit_courtyard": {
        "name": "寨内演武场", "zone": "bandit_zone",
        "desc": "黑风寨前院演武场，地面夯得极实，摆放着不少兵器架和木人桩。南边通往山贼寨门，北边直通聚义厅，东边有高耸的哨塔，西边是一条幽暗的水牢狭道。",
        "exits": {"南": "cave_entrance", "北": "bandit_camp", "东": "bandit_watchtower", "西": "bandit_water_dungeon"},
        "enemies": ["山贼", "山贼头目"], "coord": [0, 0]
    },
    "bandit_watchtower": {
        "name": "山贼哨塔", "zone": "bandit_zone",
        "desc": "用圆木搭建的数丈高台，站在塔顶可俯瞰整个山寨。弓箭手居高临下戒备着。西边通往演武场。（输入“搜索”可搜寻守卫遗落的物资）",
        "exits": {"西": "bandit_courtyard"},
        "enemies": ["山贼弓手"], "forage": {"金创药": 0.3}, "coord": [1, 0]
    },
    "bandit_water_dungeon": {
        "name": "水牢狭道", "zone": "bandit_zone",
        "desc": "通道阴暗潮湿，空气中飘着霉味与血腥气。角落的铁笼里缚着受难的村民。东边返回演武场。",
        "exits": {"东": "bandit_courtyard"},
        "npcs": ["被绑村民"], "enemies": ["看守山贼"], "coord": [-1, 0]
    },
    "bandit_camp": {
        "name": "聚义厅", "zone": "bandit_zone",
        "desc": "巨大溶洞改造而成的聚义厅，篝火熊熊。大厅正中摆着虎皮大椅，黑风寨二当家与大当家在此盘坐。东边是山贼宝库，北边有一条直通后山的密道。",
        "exits": {"南": "bandit_courtyard", "东": "bandit_treasury", "北": "bandit_back_mountain"},
        "enemies": ["山贼二当家", "山贼大当家"], "coord": [0, 1]
    },
    "bandit_treasury": {
        "name": "山贼宝库", "zone": "bandit_zone",
        "desc": "黑风寨积攒多年不义之财的密室，箱笼堆叠。宝库大总管正带着精锐在此亲自把守。西边通往聚义厅。（输入“搜索”可搜寻有限的药物储备）",
        "exits": {"西": "bandit_camp"},
        "enemies": ["宝库大总管", "山贼精英"], "forage": {"大还丹": 0.2}, "coord": [1, 1]
    },
    "bandit_back_mountain": {
        "name": "黑风后山", "zone": "bandit_zone",
        "desc": "这里是黑风寨后方的隐蔽峭壁密道，灌木丛生，向南可返回聚义厅，向东有一条小路通往主世界的村后荒野。",
        "exits": {"南": "bandit_camp", "东": "wild_fields"},
        "enemies": ["毒蛇", "野狼"], "coord": [0, 2]
    }
}

DEFAULT_NPCS = {
    "守卫": {
        "title": "青石村守卫", "desc": "身穿粗布甲胄，腰间悬着一杆红缨枪，正倚着牌楼昏昏欲睡。", "type": "villager",
        "dialogue": ["小兄弟，最近黑风山上的山贼不太安分，出村切记要小心啊！"],
        "info": {"黑风山": "黑风山上有一伙恶霸，为首的二当家极为残暴！", "山贼": "黑风山的山贼凶残无比，没有像样的兵刃千万别去冒险。"}
    },
    "村长": {
        "title": "青石村老村长", "desc": "老态龙钟，身着一袭朴素长袍，双眉紧锁，似乎正在为什么事情忧心忡忡。", "type": "master",
        "dialogue": ["唉……黑风山的山贼最近越来越猖狂，连出村采药的村民都被抓走了。"],
        "info": {"山贼": "若有少侠能击败山贼二当家，解救被绑村民，老夫必有重赏！", "黑风山": "黑风山就在村后荒野西面。"},
        "quests": ["清剿黑风山"]
    },
    "药铺老板": {
        "title": "百草堂主", "desc": "一身墨绿长袍，手里拿着一根捣药棒，正专注地研磨药材，散发着阵阵药香。", "type": "trader",
        "shop": ["疗伤药", "回内丹", "金创药", "大还丹", "护体丹"],
        "dialogue": ["刀剑无眼，出远门可得多备些金创药与护体丹啊！"],
        "info": {"采药": "草药可以在荒野和官道附近采集得到。"}
    },
    "铁匠": {
        "title": "王打铁", "desc": "肌肉虬结，赤膊挥舞着百斤重的铁锤，浑身泛着健康的光泽与汗水。", "type": "smith",
        "shop": ["铁剑", "精铁剑", "皮甲", "锁子甲"],
        "dialogue": ["只要你有铁矿石和银子，我就能帮你的兵刃与防具精炼加固！（输入“打造”后选择 1 或 2 强化）"],
        "info": {"打造": "消耗铁矿石和银子可以强化装备属性。"}
    },
    "掌柜": {
        "title": "悦来客栈掌柜", "desc": "身材稍显发福，手里拿着算盘啪啪作响，眼神精明得很。", "type": "trader",
        "shop": ["疗伤药", "护体丹"], "dialogue": ["住店养伤请上楼，打尖用餐请坐大堂！"]
    },
    "店小二": {
        "title": "客栈小二", "desc": "肩上搭着一条白毛巾，干练利落，跑前跑后招呼着过往客人。", "type": "villager",
        "dialogue": ["客官要喝点什么？本店的竹叶青可是一绝！"]
    },
    "杂货铺老板": {
        "title": "杂货张", "desc": "小眼睛笑成一条缝，极其热情的外地商人，正殷勤地擦拭着货架。", "type": "trader",
        "shop": ["疗伤药", "回内丹"], "dialogue": ["走过路过不要错过，日用杂货应有尽有！"]
    },
    "被绑村民": {
        "title": "受难的村民", "desc": "被粗大绳索紧紧捆绑在柱子上，衣服破烂不堪，身上带着伤痕。", "type": "villager",
        "dialogue": ["求求你……救救我！只要消灭这里的山贼，我就能安全逃回村子！"]
    }
}

DEFAULT_QUESTS = {
    "清剿黑风山": {
        "title": "除暴安良·清剿黑风山",
        "npc": "村长",
        "target_type": "kill",
        "target_name": "山贼二当家",
        "required_cnt": 1,
        "reward": {"exp": 150, "gold": 100, "item": "玄铁重剑"},
        "desc": "帮助村长击败黑风山上的山贼二当家，惩奸除恶。"
    }
}

DEFAULT_ITEMS = {
    "疗伤药": {"type": "consumable", "desc": "寻常金疮药，敷之止血生肌。", "effect": {"hp": 50}, "price": 20},
    "回内丹": {"type": "consumable", "desc": "复耗损之内力。", "effect": {"mp": 30}, "price": 25},
    "金创药": {"type": "consumable", "desc": "掺入冰片、麝香，外伤立止。", "effect": {"hp": 120}, "price": 50},
    "大还丹": {"type": "consumable", "desc": "名贵灵药，可同时复大量气血与内力。", "effect": {"hp": 250, "mp": 120}, "price": 200},
    "护体丹": {"type": "consumable", "desc": "服下后真气护体，吸收40点伤害。", "effect": {"status": {"name": "shield", "turns": 3, "value": 40}}, "price": 60},

    "木剑":     {"type": "weapon", "desc": "寻常柳木所制。", "atk": 5, "price": 10},
    "铁剑":     {"type": "weapon", "desc": "刃口薄利，尚堪一用。", "atk": 12, "price": 50},
    "精铁剑":   {"type": "weapon", "desc": "精铁千锤百炼而成，刃口寒光凛冽。", "atk": 20, "price": 150},
    "玄铁重剑": {"type": "weapon", "desc": "重剑无锋，大巧不工。", "atk": 35, "price": 400},

    "布衣":     {"type": "armor", "desc": "寻常粗布缝制，聊胜于无。", "defense": 3, "price": 15},
    "皮甲":     {"type": "armor", "desc": "硝制牛皮所制，轻便耐穿。", "defense": 8, "price": 40},
    "锁子甲":   {"type": "armor", "desc": "铁环相扣如网，防守极佳。", "defense": 15, "price": 120},

    "草药":     {"type": "material", "desc": "山野间常见的疗伤草药。", "price": 8},
    "铁矿石":   {"type": "material", "desc": "沉甸甸的铁矿石，可用于打造强化。", "price": 12},
    "野猪肉":   {"type": "material", "desc": "新鲜野猪肉，可卖与商家换钱。", "price": 6},
    "蛇胆":     {"type": "material", "desc": "毒蛇之胆，名贵药材。", "price": 15},
}

DEFAULT_ENEMIES = {
    "野狼": {
        "hp": 40, "atk": 8, "defense": 2, "exp": 20, "gold": 5,
        "skills": [{"name": "撕咬", "chance": 0.35, "power": 1.4}],
        "drops": [{"item": "野猪肉", "chance": 0.5}]
    },
    "野猪": {
        "hp": 55, "atk": 11, "defense": 4, "exp": 30, "gold": 10,
        "skills": [{"name": "冲撞", "chance": 0.30, "power": 1.5, "effect": "stun", "turns": 1}],
        "drops": [{"item": "野猪肉", "chance": 0.8}]
    },
    "毒蛇": {
        "hp": 35, "atk": 13, "defense": 1, "exp": 32, "gold": 12,
        "skills": [{"name": "毒牙", "chance": 0.45, "power": 1.2, "effect": "poison", "turns": 4, "value": 5}],
        "drops": [{"item": "蛇胆", "chance": 0.55}]
    },
    "山贼": {
        "hp": 65, "atk": 13, "defense": 4, "exp": 38, "gold": 18,
        "skills": [{"name": "猛砍", "chance": 0.30, "power": 1.5}],
        "drops": [{"item": "铁矿石", "chance": 0.4}]
    },
    "山贼头目": {
        "hp": 120, "atk": 18, "defense": 8, "exp": 80, "gold": 50,
        "skills": [{"name": "狂暴斩", "chance": 0.30, "power": 1.6}],
        "drops": [{"item": "铁矿石", "chance": 0.7}]
    },
    "山贼二当家": {
        "hp": 160, "atk": 22, "defense": 11, "exp": 130, "gold": 90,
        "skills": [{"name": "夺命三刀", "chance": 0.35, "power": 1.8}],
        "drops": [{"item": "精铁剑", "chance": 0.35}, {"item": "金创药", "chance": 0.7}]
    },
    "山贼弓手": {
        "hp": 50, "atk": 16, "defense": 2, "exp": 35, "gold": 20,
        "skills": [{"name": "冷箭", "chance": 0.40, "power": 1.6}],
        "drops": [{"item": "金创药", "chance": 0.4}]
    },
    "看守山贼": {
        "hp": 80, "atk": 14, "defense": 6, "exp": 45, "gold": 25,
        "skills": [{"name": "皮鞭抽打", "chance": 0.30, "power": 1.3, "effect": "bleed", "turns": 3, "value": 4}],
        "drops": [{"item": "铁矿石", "chance": 0.6}]
    },
    "山贼精英": {
        "hp": 100, "atk": 18, "defense": 8, "exp": 60, "gold": 35,
        "skills": [{"name": "连环砍", "chance": 0.35, "power": 1.5}],
        "drops": [{"item": "锁子甲", "chance": 0.15}, {"item": "金创药", "chance": 0.5}]
    },
    "宝库大总管": {
        "hp": 180, "atk": 24, "defense": 12, "exp": 150, "gold": 120,
        "skills": [{"name": "金钱镖", "chance": 0.40, "power": 1.7}],
        "drops": [{"item": "大还丹", "chance": 0.5}, {"item": "锁子甲", "chance": 0.3}]
    },
    "山贼大当家": {
        "hp": 240, "atk": 30, "defense": 15, "exp": 220, "gold": 200,
        "skills": [
            {"name": "开山霸刀", "chance": 0.30, "power": 2.0},
            {"name": "咆哮震慑", "chance": 0.25, "power": 1.2, "effect": "stun", "turns": 1}
        ],
        "drops": [{"item": "玄铁重剑", "chance": 0.3}, {"item": "大还丹", "chance": 0.8}]
    }
}

DEFAULT_SKILLS = {
    "少林": [
        {"name": "罗汉拳", "mp_cost": 15, "power": 1.8, "level": 1},
        {"name": "般若掌", "mp_cost": 25, "power": 2.4, "level": 3}
    ],
    "武当": [
        {"name": "太极剑", "mp_cost": 12, "power": 1.6, "level": 1},
        {"name": "绵掌", "mp_cost": 22, "power": 2.2, "level": 3}
    ],
    "华山": [
        {"name": "华山剑法", "mp_cost": 14, "power": 1.9, "level": 1},
        {"name": "夺命连环三仙剑", "mp_cost": 26, "power": 2.5, "level": 3}
    ],
    "散人": [
        {"name": "基础吐纳", "mp_cost": 10, "power": 1.3, "level": 1},
        {"name": "江湖散手", "mp_cost": 20, "power": 2.0, "level": 3}
    ]
}


# ==================== DataLoader 机制 ====================
class DataLoader:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.defaults = {
            "rooms": DEFAULT_ROOMS,
            "npcs": DEFAULT_NPCS,
            "items": DEFAULT_ITEMS,
            "enemies": DEFAULT_ENEMIES,
            "skills": DEFAULT_SKILLS,
            "quests": DEFAULT_QUESTS,
            "build_profiles": {},
            "world_regions": DEFAULT_WORLD_REGIONS,
            "sects": DEFAULT_SECTS,
            "factions": DEFAULT_FACTIONS,
            "world_events": {},
            "events": {}
        }

    def deep_merge(self, default, loaded):
        if not isinstance(default, dict) or not isinstance(loaded, dict):
            return loaded if loaded is not None else default
        result = deepcopy(default)
        for k, v in loaded.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self.deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def load_json(self, name):
        filepath = os.path.join(self.data_dir, f"{name}.json")
        default_data = self.defaults.get(name, {})

        if not os.path.exists(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            return deepcopy(default_data)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                user_data = json.load(f)
            return self.deep_merge(default_data, user_data)
        except Exception:
            print(f"{Color.RED}[读取错误] 部分游戏数据无法解析，已临时采用默认内容。请检查游戏数据文件。{Color.RESET}")
            return deepcopy(default_data)

    def load_all(self):
        loaded = {}
        for name in self.defaults.keys():
            loaded[name] = self.load_json(name)
        return loaded


loader = DataLoader()
GAME_DATA = loader.load_all()

ROOMS = GAME_DATA["rooms"]
NPCS = GAME_DATA["npcs"]
ITEMS = GAME_DATA["items"]
ENEMIES = GAME_DATA["enemies"]
SKILLS = GAME_DATA["skills"]
QUESTS = GAME_DATA["quests"]
BUILD_PROFILES = GAME_DATA["build_profiles"]
WORLD_REGIONS = GAME_DATA["world_regions"]
SECTS = GAME_DATA["sects"]
FACTIONS = GAME_DATA["factions"]
WORLD_EVENTS = GAME_DATA["world_events"]
EVENTS = GAME_DATA["events"]


# ==================== MapEngine 动态地图引擎 ====================
class MapEngine:
    DIR_VECTORS = {
        "北": (0, 1),
        "南": (0, -1),
        "东": (1, 0),
        "西": (-1, 0)
    }

    OPPOSITE_DIRS = {
        "北": "南", "南": "北", "东": "西", "西": "东"
    }

    CUSTOM_EXIT_ORDER = ("内", "外", "后", "前")

    ZONE_NAMES = {
        "main": "主世界",
        "bandit_zone": "黑风寨",
        "guiyun_city": "归云城",
        "mistwood": "雾隐山林",
        "sunken_ruins": "沉河遗址",
        "northfront_town": "北境商镇",
        "shaolin_mountain": "少林寺",
        "wudang_mountain": "武当派",
        "huashan_mountain": "华山派",
        "tieyi_mountain": "铁衣门",
        "duanhun_ridge": "断魂岭",
        "inn_upper": "悦来客栈二楼"
    }

    # 同名场景在地图中使用方位补充说明，避免玩家把连续道路误认为同一个房间。
    MAP_LABEL_OVERRIDES = {
        "official_road": "黄土官道（村口段）",
        "official_road_east_1": "黄土官道（东段）",
        "official_road_east_2": "黄土官道（城南段）",
        "inn": "一楼大堂",
    }
    # 地图节点使用紧凑简称，完整名称仍用于出口列表；避免长道路名撑宽整列，
    # 进而把同一行的“百草堂—村中广场—打铁铺”挤出大段空白。
    MAP_GRID_LABEL_OVERRIDES = {
        "official_road": "官道·村口",
        "official_road_east_1": "官道·东段",
        "official_road_east_2": "官道·城南",
    }

    def display_name(self, room_key):
        room = self.rooms.get(room_key, {})
        return self.MAP_LABEL_OVERRIDES.get(room_key, room.get("name", room_key))

    def __init__(self, rooms):
        self.rooms = rooms
        self.room_coords = {}
        self.coord_to_room = {}
        self.build_layout()

    def build_layout(self):
        self.room_coords.clear()
        self.coord_to_room.clear()
        zones = set(r.get("zone", "main") for r in self.rooms.values())

        for z in zones:
            # 内室/后院的 map_hidden 房间不参与地图连线，也不占用地图坐标。
            zone_rooms = {
                k: v for k, v in self.rooms.items()
                if v.get("zone", "main") == z and not v.get("map_hidden")
            }
            unpositioned = []

            for r_key, r_info in zone_rooms.items():
                if "coord" in r_info and isinstance(r_info["coord"], list) and len(r_info["coord"]) == 2:
                    coord = (r_info["coord"][0], r_info["coord"][1])
                    zone_coord = (z, coord[0], coord[1])
                    if zone_coord in self.coord_to_room:
                        unpositioned.append(r_key)
                    else:
                        self.room_coords[r_key] = coord
                        self.coord_to_room[zone_coord] = r_key
                else:
                    unpositioned.append(r_key)

            if unpositioned:
                self._multi_source_bfs_place(z, zone_rooms, unpositioned)

    def _find_nearest_empty(self, zone, start_coord):
        start_zone_coord = (zone, start_coord[0], start_coord[1])
        if start_zone_coord not in self.coord_to_room:
            return start_coord

        queue = deque([start_coord])
        visited = {start_coord}

        while queue:
            cx, cy = queue.popleft()
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nc = (cx + dx, cy + dy)
                if nc not in visited:
                    visited.add(nc)
                    if (zone, nc[0], nc[1]) not in self.coord_to_room:
                        return nc
                    queue.append(nc)
        return start_coord

    def _multi_source_bfs_place(self, zone, zone_rooms, unpositioned):
        z_positioned = [k for k in zone_rooms if k in self.room_coords]

        if not z_positioned and unpositioned:
            first = unpositioned.pop(0)
            self.room_coords[first] = (0, 0)
            self.coord_to_room[(zone, 0, 0)] = first
            z_positioned.append(first)

        queue = deque(z_positioned)
        placed_keys = set(z_positioned)

        while queue:
            parent = queue.popleft()
            px, py = self.room_coords[parent]
            exits = zone_rooms.get(parent, {}).get("exits", {})

            for d_name, target in exits.items():
                if target in placed_keys or target not in zone_rooms:
                    continue
                v = self.DIR_VECTORS.get(d_name, (0, 0))
                guess = (px + v[0], py + v[1])
                actual_coord = self._find_nearest_empty(zone, guess)

                self.room_coords[target] = actual_coord
                self.coord_to_room[(zone, actual_coord[0], actual_coord[1])] = target
                placed_keys.add(target)
                queue.append(target)

        for r_key in unpositioned:
            if r_key not in placed_keys:
                coord = self._find_nearest_empty(zone, (0, 0))
                self.room_coords[r_key] = coord
                self.coord_to_room[(zone, coord[0], coord[1])] = r_key
                placed_keys.add(r_key)

    def render(self, player_loc, player=None):
        curr_room = self.rooms.get(player_loc, {})
        curr_zone = curr_room.get("zone", "main")
        zone_title = self.ZONE_NAMES.get(curr_zone, curr_zone)

        # 隐藏出口对应的房间在发现前不应直接出现在地图上；否则地图会泄露目标位置。
        undiscovered_hidden_targets = set()
        if player is not None:
            for source in self.rooms.values():
                if source.get("zone", "main") != curr_zone:
                    continue
                hidden = source.get("hidden_exits", {}) or {}
                if not isinstance(hidden, dict):
                    continue
                for entry in hidden.values():
                    if not isinstance(entry, dict):
                        continue
                    flag = entry.get("flag")
                    target = entry.get("target")
                    if flag and target and not player.get_flag(flag):
                        undiscovered_hidden_targets.add(target)

        zone_room_coords = {
            k: v for k, v in self.room_coords.items()
            if self.rooms.get(k, {}).get("zone", "main") == curr_zone
            and not self.rooms.get(k, {}).get("map_hidden")
            and k not in undiscovered_hidden_targets
        }

        if not zone_room_coords:
            return f"{Color.RED}当前区域 [{zone_title}] 地图数据为空！{Color.RESET}"

        xs = [c[0] for c in zone_room_coords.values()]
        ys = [c[1] for c in zone_room_coords.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        grid_width = max_x - min_x + 1
        grid_height = max_y - min_y + 1

        # 每个横向坐标列独立计算宽度。列内所有节点按中心对齐，
        # 这样竖向连接线以列中心为基准时，不会偏离较短的场景名称。
        node_labels = {}
        node_widths = {}
        node_widths_by_x = {x: 10 for x in range(min_x, max_x + 1)}
        for r_key, (x, _y) in zone_room_coords.items():
            room_row = self.rooms.get(r_key, {})
            room_name = str(self.MAP_GRID_LABEL_OVERRIDES.get(r_key, self.display_name(r_key)))
            has_portal = any(
                self.rooms.get(target, {}).get("zone", "main") != curr_zone
                for target in (room_row.get("exits", {}) or {}).values()
            )
            display_label = f"{room_name}🚪" if has_portal else room_name
            exits = room_row.get("exits", {}) or {}
            custom_tags = [f"({d})" for d in self.CUSTOM_EXIT_ORDER if d in exits]
            if custom_tags:
                display_label += "".join(custom_tags)
            raw_node = f"[{pad_to_width(display_label, 8, align='center')}]"
            node_labels[r_key] = display_label
            node_widths[r_key] = get_display_width(raw_node)
            node_widths_by_x[x] = max(node_widths_by_x[x], node_widths[r_key])

        # 列宽统一为偶数，方便不同长度节点共享同一竖线中心；相邻列间留最少两格。
        for x in node_widths_by_x:
            if node_widths_by_x[x] % 2:
                node_widths_by_x[x] += 1
        column_starts = {}
        cursor = 0
        for x in range(min_x, max_x + 1):
            column_starts[x] = cursor
            cursor += node_widths_by_x[x] + 2
        canvas_rows = grid_height * 2 - 1
        canvas_cols = max(1, cursor - 2)
        canvas = [[" "] * canvas_cols for _ in range(canvas_rows)]
        node_starts = {}

        def centered_node_start(room_key, x):
            # 以列中心而非左边缘对齐，保证同一列不同长度节点的中心一致。
            return column_starts[x] + node_widths_by_x[x] // 2 - node_widths[room_key] // 2

        def put_text(row, col_start, text):
            idx = 0
            for ch in text:
                w = 2 if (ch == "🚪" or unicodedata.east_asian_width(ch) in ('F', 'W')) else 1
                if col_start + idx < canvas_cols:
                    canvas[row][col_start + idx] = ch
                    idx += 1
                    if w == 2 and col_start + idx < canvas_cols:
                        canvas[row][col_start + idx] = ""
                        idx += 1

        target_raw_node = None
        for r_key, (x, y) in zone_room_coords.items():
            row = (max_y - y) * 2
            col = centered_node_start(r_key, x)
            display_label = node_labels[r_key]
            raw_node = f"[{pad_to_width(display_label, 8, align='center')}]"
            node_starts[r_key] = col

            if r_key == player_loc:
                target_raw_node = raw_node

            put_text(row, col, raw_node)

        for r_key, (x, y) in zone_room_coords.items():
            r_row = (max_y - y) * 2
            r_col = column_starts[x]
            exits = self.rooms.get(r_key, {}).get("exits", {})

            for d_name, target_key in exits.items():
                if target_key not in zone_room_coords: continue
                tx, ty = zone_room_coords[target_key]
                dx = tx - x
                dy = ty - y

                if dx == 0 and abs(dy) == 1:
                    # 竖线使用列中心；节点已按相同中心对齐，长短名称不会造成错位。
                    mid_row = int((max_y - (y + ty) / 2) * 2)
                    line_col = column_starts[x] + node_widths_by_x[x] // 2
                    put_text(mid_row, line_col, "│")
                elif dy == 0 and abs(dx) == 1:
                    # 横线从当前节点的实际右边缘连到目标节点实际左边缘，避免穿过节点。
                    if tx > x:
                        left_key, right_key = r_key, target_key
                    else:
                        left_key, right_key = target_key, r_key
                    left_end = node_starts.get(left_key, centered_node_start(left_key, zone_room_coords[left_key][0])) + node_widths[left_key]
                    right_start = node_starts.get(right_key, centered_node_start(right_key, zone_room_coords[right_key][0]))
                    for line_col in range(left_end, right_start):
                        put_text(r_row, line_col, "─")

        lines = [f"\n{Color.BRIGHT_CYAN}======================== 动态江湖地图 [{zone_title}] ========================{Color.RESET}"]

        for r in canvas:
            line_str = "".join(r).rstrip()
            if target_raw_node and target_raw_node in line_str:
                highlighted = f"{Color.BRIGHT_RED}{Color.BOLD}{target_raw_node}{Color.RESET}"
                line_str = line_str.replace(target_raw_node, highlighted)
            lines.append(line_str)

        exits_info = []
        for dir_key, tgt_key in curr_room.get("exits", {}).items():
            t_info = self.rooms.get(tgt_key, {})
            t_name = self.display_name(tgt_key)
            t_zone = t_info.get("zone", "main")
            if t_zone != curr_zone and dir_key not in ("上", "下"):
                t_name += f" (进入{self.ZONE_NAMES.get(t_zone, t_zone)})"
            exits_info.append(f"{dir_key} -> {t_name}")
        exit_str = " | ".join(exits_info) if exits_info else "无出口"

        lines.append(f"\n当前位置：{Color.BRIGHT_RED}{curr_room.get('name', '未知')}{Color.RESET}")
        lines.append(f"可去方向：{Color.YELLOW}{exit_str}{Color.RESET}")
        lines.append(f"{Color.BRIGHT_YELLOW}图例提示：高亮红字为当前位置，带有 🚪 符号表示该处连通其他区域/副本。{Color.RESET}")
        lines.append(f"{Color.BRIGHT_CYAN}============================================================{Color.RESET}")

        return "\n".join(lines)


MAP_ENGINE = MapEngine(ROOMS)


def reload_game_data():
    global GAME_DATA, ROOMS, NPCS, ITEMS, ENEMIES, SKILLS, QUESTS, BUILD_PROFILES, WORLD_REGIONS, SECTS, FACTIONS, WORLD_EVENTS, EVENTS
    GAME_DATA = loader.load_all()
    ROOMS = GAME_DATA["rooms"]
    NPCS = GAME_DATA["npcs"]
    ITEMS = GAME_DATA["items"]
    ENEMIES = GAME_DATA["enemies"]
    SKILLS = GAME_DATA["skills"]
    QUESTS = GAME_DATA["quests"]
    BUILD_PROFILES = GAME_DATA["build_profiles"]
    WORLD_REGIONS = GAME_DATA["world_regions"]
    SECTS = GAME_DATA["sects"]
    FACTIONS = GAME_DATA["factions"]
    WORLD_EVENTS = GAME_DATA["world_events"]
    EVENTS = GAME_DATA["events"]
    MAP_ENGINE = MapEngine(ROOMS)
    print(f"{Color.BRIGHT_GREEN}[热重载完成] 游戏配置数据与动态地图引擎已同步刷新！{Color.RESET}\n")