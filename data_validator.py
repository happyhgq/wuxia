# -*- coding: utf-8 -*-
"""wuxia data validator - read-only integrity checks for rooms/NPCs/items/enemies/skills/quests."""
import json, os, re, sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DIR_VECTORS = {"北": (0,1), "南": (0,-1), "东": (1,0), "西": (-1,0)}
VERTICAL_DIRECTIONS = {"上", "下"}
CUSTOM_DIRECTIONS = {"内", "外", "后", "前"}
OPPOSITE = {
    "北": "南", "南": "北", "东": "西", "西": "东",
    "上": "下", "下": "上", "内": "外", "外": "内", "后": "前", "前": "后",
}
SCHEDULE_TIERS = {"T1", "T2", "T3"}
EVENT_CONDITION_KEYS = {
    "flags", "not_flags", "completed_quests", "variables", "honor", "infamy",
    "jianghu_paths", "level", "gold", "sect", "sect_reputation",
    "faction_relations", "skills", "items", "relations", "npc_memory",
    "npc_memory_attitude", "npc_information", "npc_states",
}
EVENT_EFFECT_KEYS = {"set_flags", "set_variables", "increment_variables", "faction_relations", "relations", "region_effects"}
REGION_EFFECT_FIELDS = {"security", "commerce", "travel"}
REGION_EFFECT_RANGE = (-60, 30)
PERCEPTION_TIME_PHASES = {"dawn", "day", "dusk", "night"}
PERCEPTION_WEATHERS = {"clear", "cloudy", "rain", "storm", "snow", "fog"}
PERCEPTION_INJURIES = {"healthy", "wounded", "badly_wounded"}
PERCEPTION_QUALITIES = {"普通", "精良", "稀有", "史诗"}
PERCEPTION_QUALITY_OPS = {"eq", "gte", "gt", "lte", "lt"}
PERCEPTION_NUMBER_OPS = {"eq", "ne", "gte", "gt", "lte", "lt"}
PERCEPTION_EQUIPMENT_KEYS = {"best", "weapon", "armor", "accessory"}


def valid_perception_enum(rule, allowed):
    if isinstance(rule, str):
        return rule in allowed
    if isinstance(rule, (list, tuple)):
        return bool(rule) and all(isinstance(value, str) and value in allowed for value in rule)
    if isinstance(rule, dict):
        if not rule or not set(rule) <= {"in", "not_in"}:
            return False
        for values in rule.values():
            if not isinstance(values, (list, tuple)) or not values:
                return False
            if any(not isinstance(value, str) or value not in allowed for value in values):
                return False
        return True
    return False


def valid_perception_quality(rule):
    if isinstance(rule, str):
        return rule in PERCEPTION_QUALITIES
    if isinstance(rule, dict):
        return bool(rule) and set(rule) <= PERCEPTION_QUALITY_OPS and all(
            value in PERCEPTION_QUALITIES for value in rule.values()
        )
    return False


def valid_perception_number(rule):
    if isinstance(rule, dict):
        return bool(rule) and set(rule) <= PERCEPTION_NUMBER_OPS and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100
            for value in rule.values()
        )
    return isinstance(rule, (int, float)) and not isinstance(rule, bool) and 0 <= rule <= 100


def validate_perception_rules(perception, label, errors):
    if not isinstance(perception, dict) or not perception:
        errors.append(f"{label} perception 必须为非空对象")
        return
    for key, rule in perception.items():
        if key == "time_phase" and not valid_perception_enum(rule, PERCEPTION_TIME_PHASES):
            errors.append(f"{label} perception.time_phase 非法")
        elif key == "weather" and not valid_perception_enum(rule, PERCEPTION_WEATHERS):
            errors.append(f"{label} perception.weather 非法")
        elif key == "injury" and not valid_perception_enum(rule, PERCEPTION_INJURIES):
            errors.append(f"{label} perception.injury 非法")
        elif key == "hp_percent" and not valid_perception_number(rule):
            errors.append(f"{label} perception.hp_percent 必须在 0~100")
        elif key == "equipment_quality":
            if not isinstance(rule, dict) or not rule:
                errors.append(f"{label} perception.equipment_quality 必须为非空对象")
                continue
            for slot, quality_rule in rule.items():
                if slot not in PERCEPTION_EQUIPMENT_KEYS:
                    errors.append(f"{label} perception.equipment_quality 槽位非法 {slot}")
                elif not valid_perception_quality(quality_rule):
                    errors.append(f"{label} perception.equipment_quality.{slot} 品质非法")
        elif key not in {"time_phase", "weather", "injury", "hp_percent", "equipment_quality"}:
            errors.append(f"{label} perception 未知键 {key}")


def validate_conditional_entry(entry, label, errors, require_perception=False):
    if not isinstance(entry, dict):
        errors.append(f"{label} 必须为对象")
        return
    variants = entry.get("variants")
    if variants is not None:
        if not isinstance(variants, list) or not variants:
            errors.append(f"{label} variants 必须为非空数组")
        else:
            seen = set()
            for vidx, text in enumerate(variants, 1):
                if not isinstance(text, str) or not text.strip():
                    errors.append(f"{label} variants[{vidx}] 必须为非空字符串")
                elif text in seen:
                    errors.append(f"{label} variants[{vidx}] 重复")
                else:
                    seen.add(text)
    has_text = isinstance(entry.get("text"), str) and bool(entry["text"].strip())
    if not has_text and variants is None:
        errors.append(f"{label} 必须提供 text 或 variants")
    if "priority" in entry:
        try:
            int(entry.get("priority"))
        except (TypeError, ValueError):
            errors.append(f"{label} priority 必须为整数")
    if "requires" in entry and not isinstance(entry.get("requires"), dict):
        errors.append(f"{label} requires 必须为对象")
    if require_perception and "perception" not in entry:
        errors.append(f"{label} perception 必须为非空对象")
        return
    if "perception" in entry:
        validate_perception_rules(entry.get("perception"), label, errors)


def check_region_effects(effects, label, zone_names, errors):
    """region_effects 写入持久治安记录，区域名与夹紧范围必须和运行时一致。"""
    if not isinstance(effects, dict):
        return
    region_effects = effects.get("region_effects")
    if region_effects is None:
        return
    if not isinstance(region_effects, dict):
        errors.append(f"{label}: region_effects 必须为对象")
        return
    low, high = REGION_EFFECT_RANGE
    for zone, delta in region_effects.items():
        if zone not in zone_names:
            errors.append(f"{label}: region_effects 引用不存在的区域 {zone}")
        if not isinstance(delta, dict):
            errors.append(f"{label}: region_effects.{zone} 必须为对象")
            continue
        for key, amount in delta.items():
            if key not in REGION_EFFECT_FIELDS:
                errors.append(f"{label}: region_effects.{zone} 不支持字段 {key}")
            elif isinstance(amount, bool) or not isinstance(amount, int):
                errors.append(f"{label}: region_effects.{zone}.{key} 必须为整数")
            elif not low <= amount <= high:
                errors.append(f"{label}: region_effects.{zone}.{key} 超出 {low}~{high}")

def schedule_hours(start, end):
    """返回日程条目覆盖的整点集合；左闭右开，支持跨午夜。"""
    if start < end:
        return set(range(start, end))
    return set(range(start, 24)) | set(range(0, end))

def load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)

def main():
    rooms=load("rooms.json"); npcs=load("npcs.json"); items=load("items.json"); build_profiles=load("build_profiles.json"); world_regions=load("world_regions.json"); world_events=load("world_events.json")
    enemies=load("enemies.json"); skills=load("skills.json"); quests=load("quests.json"); sects=load("sects.json"); factions=load("factions.json"); entry_events=load("events.json")
    perception_templates=load("perception_templates.json")
    economy_dir = os.path.join(DATA_DIR, "economy")
    def load_economy(name):
        with open(os.path.join(economy_dir, name), encoding="utf-8") as f:
            return json.load(f)
    resources=load_economy("resources.json"); gatherers=load_economy("gatherers.json")
    recipes=load_economy("recipes.json"); caravans=load_economy("caravans.json")
    errors=[]; warnings=[]; coords={}
    if not isinstance(perception_templates, dict):
        errors.append("perception_templates.json 顶层必须为对象")
        perception_templates = {}
    else:
        for role, template_entries in perception_templates.items():
            if not isinstance(role, str) or not role.strip():
                errors.append("感知模板: 职业名必须为非空字符串")
                continue
            if not isinstance(template_entries, list) or not template_entries:
                errors.append(f"感知模板 {role}: 必须为非空数组")
                continue
            for idx, entry in enumerate(template_entries, 1):
                validate_conditional_entry(entry, f"感知模板 {role}[{idx}]", errors, require_perception=True)
    for rid,r in rooms.items():
        c=r.get("coord")
        if not (isinstance(c,list) and len(c)==2 and all(isinstance(x,(int,float)) for x in c)):
            errors.append(f"房间 {rid}: coord 缺失/非法")
        else:
            key=(r.get("zone","main"),c[0],c[1])
            if key in coords: errors.append(f"重复坐标 {key}: {coords[key]} / {rid}")
            coords[key]=rid
        for d,t in r.get("exits",{}).items():
            if d not in DIR_VECTORS and d not in VERTICAL_DIRECTIONS and d not in CUSTOM_DIRECTIONS:
                errors.append(f"房间 {rid}: 非法方向 {d}")
            if t not in rooms: errors.append(f"房间 {rid}: 出口 {d} -> {t} 不存在"); continue
            tr=rooms[t]
            same_zone = r.get("zone","main")==tr.get("zone","main")
            if same_zone and d in DIR_VECTORS:
                rc=r.get("coord"); tc=tr.get("coord")
                if isinstance(rc,list) and isinstance(tc,list):
                    dx,dy=DIR_VECTORS[d]
                    if tuple(tc)!=(rc[0]+dx,rc[1]+dy):
                        errors.append(f"房间 {rid}: {d}->{t} 坐标不一致")
            if same_zone or d in VERTICAL_DIRECTIONS or d in CUSTOM_DIRECTIONS:
                reverse_target = tr.get("exits", {}).get(OPPOSITE[d])
                hidden_reverse = tr.get("hidden_exits", {}).get(OPPOSITE[d], {}) if isinstance(tr.get("hidden_exits", {}), dict) else {}
                if reverse_target != rid and not (isinstance(hidden_reverse, dict) and hidden_reverse.get("target") == rid):
                    errors.append(f"房间 {rid}: {d}->{t} 缺少反向出口 {OPPOSITE[d]}")
        for flag in ("map_hidden", "safe_zone", "trade_closed", "indoor", "window_view"):
            if flag in r and not isinstance(r.get(flag), bool):
                errors.append(f"房间 {rid}: {flag} 必须为布尔值")
        if "trade_closed_text" in r and (not isinstance(r.get("trade_closed_text"), str) or not r.get("trade_closed_text").strip()):
            errors.append(f"房间 {rid}: trade_closed_text 必须为非空字符串")
        if "night_desc" in r and (not isinstance(r.get("night_desc"), str) or not r.get("night_desc").strip()):
            errors.append(f"房间 {rid}: night_desc 必须为非空字符串")
        if "night_hours" in r:
            hours = r.get("night_hours")
            if not (isinstance(hours, list) and len(hours) == 2 and all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 23 for x in hours)):
                errors.append(f"房间 {rid}: night_hours 必须为两个 0~23 整数")
            elif hours[0] == hours[1]:
                errors.append(f"房间 {rid}: night_hours 不能首尾相同")
        if "absence_notes" in r:
            notes = r.get("absence_notes")
            if not isinstance(notes, dict):
                errors.append(f"房间 {rid}: absence_notes 必须为对象")
            else:
                room_npcs = r.get("npcs", []) or []
                for npc_name, text in notes.items():
                    if npc_name not in npcs:
                        errors.append(f"房间 {rid}: absence_notes 引用不存在 NPC {npc_name}")
                    elif npc_name not in room_npcs:
                        warnings.append(f"房间 {rid}: absence_notes 的 {npc_name} 不在本房间 npcs 列表中")
                    if not isinstance(text, str) or not text.strip():
                        errors.append(f"房间 {rid}: absence_notes.{npc_name} 必须为非空字符串")
    zone_names = {r.get("zone", "main") for r in rooms.values()}
    if not isinstance(entry_events, dict) or not entry_events:
        errors.append("events.json 必须为非空对象")
    else:
        for event_id, event in entry_events.items():
            if not isinstance(event_id, str) or not event_id.strip():
                errors.append("事件 ID 必须为非空字符串")
            if not isinstance(event, dict):
                errors.append(f"事件 {event_id}: 必须为对象"); continue
            title = event.get("title")
            if title is not None and (not isinstance(title, str) or not title.strip()):
                errors.append(f"事件 {event_id}: title 必须为非空字符串")
            text = event.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"事件 {event_id}: text 必须为非空字符串")
            event_rooms = event.get("rooms")
            zone = event.get("zone")
            if event_rooms is None and zone is None:
                errors.append(f"事件 {event_id}: rooms 与 zone 至少需要一项")
            if event_rooms is not None:
                if not isinstance(event_rooms, list) or not event_rooms:
                    errors.append(f"事件 {event_id}: rooms 必须为非空数组")
                else:
                    for room_id in event_rooms:
                        if room_id not in rooms:
                            errors.append(f"事件 {event_id}: rooms 引用不存在房间 {room_id}")
            if zone is not None:
                if not isinstance(zone, str) or not zone.strip():
                    errors.append(f"事件 {event_id}: zone 必须为非空字符串")
                elif zone not in zone_names:
                    errors.append(f"事件 {event_id}: zone 不存在 {zone}")
            if "hours" in event:
                hours = event.get("hours")
                if not (isinstance(hours, list) and len(hours) == 2 and all(
                        isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 23 for x in hours)):
                    errors.append(f"事件 {event_id}: hours 必须为两个 0~23 整数")
                elif hours[0] == hours[1]:
                    errors.append(f"事件 {event_id}: hours 不能首尾相同")
            if "requires" in event:
                requires = event.get("requires")
                if not isinstance(requires, dict):
                    errors.append(f"事件 {event_id}: requires 必须为对象")
                else:
                    for key in requires:
                        if key not in EVENT_CONDITION_KEYS:
                            errors.append(f"事件 {event_id}: 不支持的条件 {key}")
            if "once" in event and not isinstance(event.get("once"), bool):
                errors.append(f"事件 {event_id}: once 必须为布尔值")
            for field in ("cooldown", "priority"):
                if field in event and (not isinstance(event.get(field), int)
                                       or isinstance(event.get(field), bool) or event.get(field) < 0):
                    errors.append(f"事件 {event_id}: {field} 必须为非负整数")
            if "effects" in event:
                effects = event.get("effects")
                if not isinstance(effects, dict):
                    errors.append(f"事件 {event_id}: effects 必须为对象")
                else:
                    for key, value in effects.items():
                        if key not in EVENT_EFFECT_KEYS:
                            errors.append(f"事件 {event_id}: 不支持的效果 {key}")
                        elif not isinstance(value, dict):
                            errors.append(f"事件 {event_id}: effects.{key} 必须为对象")
                    check_region_effects(effects, f"事件 {event_id}", zone_names, errors)
    if not isinstance(factions, dict) or not factions:
        errors.append("factions.json 必须为非空对象")
    else:
        for faction_name, info in factions.items():
            if not isinstance(info, dict):
                errors.append(f"势力 {faction_name}: 必须为对象"); continue
            influence=info.get("influence", 0)
            if not isinstance(influence, int) or isinstance(influence, bool) or not 0 <= influence <= 100:
                errors.append(f"势力 {faction_name}: influence 必须为 0~100 整数")
            relations=info.get("relations", {})
            if not isinstance(relations, dict):
                errors.append(f"势力 {faction_name}: relations 必须为对象")
            else:
                for other, value in relations.items():
                    if other not in factions: errors.append(f"势力 {faction_name}: relations 引用不存在 {other}")
                    if not isinstance(value, int) or isinstance(value, bool) or not -100 <= value <= 100:
                        errors.append(f"势力 {faction_name}: relations.{other} 必须为 -100~100 整数")
            actions = info.get("actions", []) or []
            if not isinstance(actions, list):
                errors.append(f"势力 {faction_name}: actions 必须为数组")
            else:
                action_ids = set()
                valid_action_types = {"conflict", "mediation", "political", "defense", "information", "world"}
                for idx, action in enumerate(actions):
                    if not isinstance(action, dict):
                        errors.append(f"势力 {faction_name}: actions[{idx}] 必须为对象"); continue
                    aid = action.get("id")
                    if not aid or aid in action_ids:
                        errors.append(f"势力 {faction_name}: actions[{idx}] id 缺失或重复")
                    action_ids.add(aid)
                    if "type" in action and action.get("type") not in valid_action_types:
                        errors.append(f"势力 {faction_name}: actions[{idx}].type 非法")
                    for field in ("interval", "cooldown"):
                        if field in action and (not isinstance(action[field], int) or isinstance(action[field], bool) or action[field] < 0):
                            errors.append(f"势力 {faction_name}: actions[{idx}].{field} 必须为非负整数")
                    if "requires" in action and not isinstance(action.get("requires"), dict):
                        errors.append(f"势力 {faction_name}: actions[{idx}].requires 必须为对象")
                    target = action.get("target_faction")
                    if target and target not in factions:
                        errors.append(f"势力 {faction_name}: actions[{idx}] 引用不存在目标势力 {target}")
                    effects = action.get("effects", {}) or {}
                    if not isinstance(effects, dict):
                        errors.append(f"势力 {faction_name}: actions[{idx}].effects 必须为对象")
                    reactions = action.get("npc_reactions", []) or []
                    if not isinstance(reactions, list):
                        errors.append(f"势力 {faction_name}: actions[{idx}].npc_reactions 必须为数组")
                    else:
                        for ridx, reaction in enumerate(reactions):
                            if not isinstance(reaction, dict):
                                errors.append(f"势力 {faction_name}: actions[{idx}].npc_reactions[{ridx}] 必须为对象"); continue
                            if reaction.get("npc") not in npcs:
                                errors.append(f"势力 {faction_name}: actions[{idx}] 引用不存在 NPC {reaction.get('npc')}")

    npc_display_ids = {}
    for n,info in npcs.items():
        if not isinstance(info, dict):
            continue
        display_id = info.get("id")
        if not isinstance(display_id, str) or not display_id.strip():
            errors.append(f"NPC {n}: id 必须为非空字符串")
        elif not re.fullmatch(r"[a-z0-9][a-z0-9 -]*", display_id):
            errors.append(f"NPC {n}: id 只能使用小写字母、数字、空格与连字符")
        elif display_id in npc_display_ids:
            errors.append(f"NPC {n}: id 与 {npc_display_ids[display_id]} 重复 {display_id}")
        else:
            npc_display_ids[display_id] = n
        name = info.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"NPC {n}: name 必须为非空字符串")
        rank_title = info.get("rank_title")
        if not isinstance(rank_title, str):
            errors.append(f"NPC {n}: rank_title 必须为字符串")
        nickname = info.get("nickname")
        if nickname is not None and not isinstance(nickname, str):
            errors.append(f"NPC {n}: nickname 必须为字符串")
        talk_verb = info.get("talk_verb")
        if talk_verb is not None:
            if not isinstance(talk_verb, str) or not talk_verb.strip():
                errors.append(f"NPC {n}: talk_verb 必须为非空字符串")
            elif not re.fullmatch(r"[\u4e00-\u9fff]{2,12}", talk_verb.strip()) or not talk_verb.strip().endswith("道"):
                errors.append(f"NPC {n}: talk_verb 必须为 2~12 个汉字且以“道”结尾")
        if info.get("gender") not in ("male", "female", "neutral"):
            errors.append(f"NPC {n}: gender 必须为 male/female/neutral")
        power_tier = info.get("power_tier")
        if not isinstance(power_tier, int) or isinstance(power_tier, bool) or not 0 <= power_tier <= 5:
            errors.append(f"NPC {n}: power_tier 必须为 0~5 整数")
        for field in ("age_desc", "face_attire", "martial_style", "condition_trait"):
            if field in info and (not isinstance(info.get(field), str) or not info.get(field, "").strip()):
                errors.append(f"NPC {n}: {field} 必须为非空字符串")
        gear_display = info.get("gear_display")
        if gear_display is not None:
            if not isinstance(gear_display, list):
                errors.append(f"NPC {n}: gear_display 必须为数组")
            else:
                for idx, entry in enumerate(gear_display):
                    if not isinstance(entry, dict):
                        errors.append(f"NPC {n}: gear_display[{idx}] 必须为对象")
                        continue
                    if not isinstance(entry.get("name"), str) or not entry.get("name", "").strip():
                        errors.append(f"NPC {n}: gear_display[{idx}].name 必须为非空字符串")
                    if not isinstance(entry.get("id"), str) or not entry.get("id", "").strip():
                        errors.append(f"NPC {n}: gear_display[{idx}].id 必须为非空字符串")
        faction = info.get("faction", "")
        if faction and faction not in factions:
            errors.append(f"NPC {n}: faction 引用不存在 {faction}")
        bonds=info.get("npc_bonds", {}) or {}
        if not isinstance(bonds, dict): errors.append(f"NPC {n}: npc_bonds 必须为对象")
        else:
            for other,val in bonds.items():
                if other not in npcs: errors.append(f"NPC {n}: npc_bonds 引用不存在 {other}")
                if not isinstance(val, int) or isinstance(val, bool) or not -100 <= val <= 100:
                    errors.append(f"NPC {n}: npc_bonds.{other} 必须为 -100~100 整数")
        autonomy=info.get("autonomy_profile", {}) or {}
        if not isinstance(autonomy, dict):
            errors.append(f"NPC {n}: autonomy_profile 必须为对象")
        else:
            if autonomy.get("enabled") is not True:
                errors.append(f"NPC {n}: autonomy_profile.enabled 必须为 true")
            interval=autonomy.get("interval", 3)
            if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
                errors.append(f"NPC {n}: autonomy_profile.interval 必须为正整数")
            allowed=autonomy.get("allowed_actions", [])
            valid_actions={"patrol", "investigate", "meet_npc", "seek_player", "rest"}
            if not isinstance(allowed, list) or not allowed:
                errors.append(f"NPC {n}: autonomy_profile.allowed_actions 必须为非空数组")
            else:
                for action in allowed:
                    if action not in valid_actions:
                        errors.append(f"NPC {n}: autonomy_profile.allowed_actions 包含非法动作 {action}")
            blocked=autonomy.get("blocked_states", [])
            if not isinstance(blocked, list):
                errors.append(f"NPC {n}: autonomy_profile.blocked_states 必须为数组")
            for room_id in autonomy.get("route", []) or []:
                if room_id not in rooms:
                    errors.append(f"NPC {n}: autonomy_profile.route 引用不存在房间 {room_id}")
            for field in ("seek_player_min_relation", "seek_player_frequency", "meet_frequency"):
                if field in autonomy and (not isinstance(autonomy[field], int) or isinstance(autonomy[field], bool) or autonomy[field] < 1):
                    errors.append(f"NPC {n}: autonomy_profile.{field} 必须为正整数")
        utility = info.get("utility_profile", {}) or {}
        if not isinstance(utility, dict):
            errors.append(f"NPC {n}: utility_profile 必须为对象")
        elif utility:
            if utility.get("enabled") is not True:
                errors.append(f"NPC {n}: utility_profile.enabled 必须为 true")
            interval = utility.get("interval", 2)
            if not isinstance(interval, int) or isinstance(interval, bool) or interval < 1:
                errors.append(f"NPC {n}: utility_profile.interval 必须为正整数")
            for field in ("work_room", "meal_room", "social_room"):
                if field in utility and utility[field] not in rooms:
                    errors.append(f"NPC {n}: utility_profile.{field} 引用不存在房间 {utility[field]}")
            for field in ("work_hours", "meal_hours"):
                values = utility.get(field, [])
                if not isinstance(values, list):
                    errors.append(f"NPC {n}: utility_profile.{field} 必须为数组")
                    continue
                if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 23 for v in values):
                    errors.append(f"NPC {n}: utility_profile.{field} 必须为 0~23 整数")
            if "work_hours" in utility and len(utility.get("work_hours") or []) != 2:
                errors.append(f"NPC {n}: utility_profile.work_hours 必须为两个钟点")
            utility_actions = {"work", "routine", "rest", "meal", "socialize", "patrol", "meet_npc", "seek_player", "investigate"}
            allowed = utility.get("allowed_actions", [])
            if not isinstance(allowed, list):
                errors.append(f"NPC {n}: utility_profile.allowed_actions 必须为数组")
            else:
                for action in allowed:
                    if action not in utility_actions:
                        errors.append(f"NPC {n}: utility_profile.allowed_actions 包含非法动作 {action}")
            if not isinstance(utility.get("blocked_states", []), list):
                errors.append(f"NPC {n}: utility_profile.blocked_states 必须为数组")
        proactive_quests = info.get("proactive_quests", []) or []
        if not isinstance(proactive_quests, list):
            errors.append(f"NPC {n}: proactive_quests 必须为数组")
        else:
            for idx, pq in enumerate(proactive_quests, 1):
                if not isinstance(pq, dict):
                    errors.append(f"NPC {n}: proactive_quests[{idx}] 必须为对象"); continue
                q_name = pq.get("quest")
                if q_name not in quests:
                    errors.append(f"NPC {n}: proactive_quests[{idx}] 引用不存在任务 {q_name}")
                if "trigger_action" in pq and pq.get("trigger_action") not in valid_actions:
                    errors.append(f"NPC {n}: proactive_quests[{idx}].trigger_action 非法")
                for field in ("cooldown", "fail_after", "min_relation"):
                    if field in pq and (not isinstance(pq[field], int) or isinstance(pq[field], bool) or (field != "min_relation" and pq[field] < 0) or (field == "min_relation" and not -100 <= pq[field] <= 100)):
                        errors.append(f"NPC {n}: proactive_quests[{idx}].{field} 数值非法")
                if "memory_behaviors" in pq and not isinstance(pq.get("memory_behaviors"), list):
                    errors.append(f"NPC {n}: proactive_quests[{idx}].memory_behaviors 必须为数组")
        profile=info.get("information_profile", {}) or {}
        if not isinstance(profile, dict): errors.append(f"NPC {n}: information_profile 必须为对象")
        memory_profile=info.get("memory_profile", {}) or {}
        if not isinstance(memory_profile, dict):
            errors.append(f"NPC {n}: memory_profile 必须为对象")
        else:
            behavior=memory_profile.get("behavior", {}) or {}
            if not isinstance(behavior, dict):
                errors.append(f"NPC {n}: memory_profile.behavior 必须为对象")
            else:
                for key in ("friendly_gte", "favorable_gte", "wary_lte", "hostile_lte"):
                    if key in behavior and (not isinstance(behavior[key], int) or isinstance(behavior[key], bool) or not -100 <= behavior[key] <= 100):
                        errors.append(f"NPC {n}: memory_profile.behavior.{key} 必须为 -100~100 整数")
            quest_memory=memory_profile.get("quest_memory", {}) or {}
            if not isinstance(quest_memory, dict):
                errors.append(f"NPC {n}: memory_profile.quest_memory 必须为对象")
            elif "ttl" in quest_memory and (not isinstance(quest_memory["ttl"], int) or isinstance(quest_memory["ttl"], bool) or quest_memory["ttl"] < 0):
                errors.append(f"NPC {n}: memory_profile.quest_memory.ttl 必须为非负整数")
        entries=info.get("information", []) or []
        if not isinstance(entries, list):
            errors.append(f"NPC {n}: information 必须为数组")
        else:
            topics=set()
            for idx,entry in enumerate(entries,1):
                if not isinstance(entry, dict): errors.append(f"NPC {n}: information[{idx}] 必须为对象"); continue
                topic=entry.get("topic"); text=entry.get("text")
                if not isinstance(topic,str) or not topic: errors.append(f"NPC {n}: information[{idx}] topic 非法")
                if not isinstance(text,str) or not text: errors.append(f"NPC {n}: information[{idx}] text 非法")
                if topic in topics: errors.append(f"NPC {n}: information topic 重复 {topic}")
                topics.add(topic)
                conf=entry.get("confidence",50)
                if not isinstance(conf,int) or isinstance(conf,bool) or not 0 <= conf <= 100: errors.append(f"NPC {n}: information[{idx}] confidence 必须为 0~100 整数")
                ttl=entry.get("ttl",0)
                if not isinstance(ttl,int) or isinstance(ttl,bool) or ttl < 0: errors.append(f"NPC {n}: information[{idx}] ttl 必须为非负整数")
    for rid, room in rooms.items():
        hidden_exits = room.get("hidden_exits", {}) or {}
        if not isinstance(hidden_exits, dict):
            errors.append(f"房间 {rid}: hidden_exits 必须为对象")
        else:
            for direction, entry in hidden_exits.items():
                if direction not in DIR_VECTORS:
                    errors.append(f"房间 {rid}: 隐藏出口方向非法 {direction}"); continue
                if not isinstance(entry, dict):
                    errors.append(f"房间 {rid}: 隐藏出口 {direction} 必须为对象"); continue
                target = entry.get("target")
                if target not in rooms:
                    errors.append(f"房间 {rid}: 隐藏出口 {direction} 目标不存在 {target}"); continue
                if not isinstance(entry.get("flag"), str) or not entry.get("flag"):
                    errors.append(f"房间 {rid}: 隐藏出口 {direction} 缺少解锁标记")
                target_room = rooms[target]
                if room.get("zone", "main") != target_room.get("zone", "main"):
                    errors.append(f"房间 {rid}: 隐藏出口 {direction} 跨区域，需使用显式传送门配置")
                rc, tc = room.get("coord"), target_room.get("coord")
                if isinstance(rc, list) and isinstance(tc, list):
                    dx, dy = DIR_VECTORS[direction]
                    if tuple(tc) != (rc[0] + dx, rc[1] + dy):
                        errors.append(f"房间 {rid}: 隐藏出口 {direction}->{target} 坐标不一致")
                reverse = target_room.get("exits", {}).get(OPPOSITE[direction])
                if reverse != rid:
                    errors.append(f"房间 {rid}: 隐藏出口 {direction}->{target} 缺少目标房间反向出口 {OPPOSITE[direction]}")
        for n in room.get("npcs",[]) or []:
            if n not in npcs: errors.append(f"房间 {rid}: NPC {n} 不存在")
        for e in r.get("enemies",[]) or []:
            if e not in enemies: errors.append(f"房间 {rid}: 敌人 {e} 不存在")
        if "area_level" in r and (not isinstance(r.get("area_level"), int) or r.get("area_level") < 1):
            errors.append(f"房间 {rid}: area_level 必须为正整数")
        if "recommended_level" in r and (not isinstance(r.get("recommended_level"), int) or r.get("recommended_level") < 1):
            errors.append(f"房间 {rid}: recommended_level 必须为正整数")
        if "danger" in r and r.get("danger") not in ("safe","normal","dangerous","high","extreme"):
            errors.append(f"房间 {rid}: danger 非法")
        if "exploration_events" in r and not isinstance(r.get("exploration_events"), list):
            errors.append(f"房间 {rid}: exploration_events 必须为数组")
        if "difficulty_level" in r:
            if not isinstance(r.get("difficulty_level"), int) or isinstance(r.get("difficulty_level"), bool) or not 1 <= r.get("difficulty_level") <= 30:
                errors.append(f"房间 {rid}: difficulty_level 必须为 1~30 整数")
            if "difficulty_label" in r and not isinstance(r.get("difficulty_label"), str):
                errors.append(f"房间 {rid}: difficulty_label 必须为字符串")
        for item in r.get("forage",{}) or {}:
            if item not in items: errors.append(f"房间 {rid}: 采集物 {item} 不存在")
    item_display_ids = {}
    for item_name, info in items.items():
        display_id = info.get("id")
        if not isinstance(display_id, str) or not display_id.strip():
            errors.append(f"物品 {item_name}: id 必须为非空字符串")
        elif not re.fullmatch(r"[a-z0-9][a-z0-9 -]*", display_id):
            errors.append(f"物品 {item_name}: id 只能使用小写字母、数字、空格与连字符")
        elif display_id in item_display_ids:
            errors.append(f"物品 {item_name}: id 与 {item_display_ids[display_id]} 重复 {display_id}")
        else:
            item_display_ids[display_id] = item_name
        if "clothing" in info and not isinstance(info.get("clothing"), bool):
            errors.append(f"物品 {item_name}: clothing 必须为布尔值")
        if info.get("type") in ("weapon", "armor", "accessory"):
            expected_slot = info.get("type")
            if info.get("slot") != expected_slot:
                errors.append(f"物品 {item_name}: 装备 slot 必须为 {expected_slot}")
            stat_key = "atk" if expected_slot == "weapon" else "defense"
            value = info.get(stat_key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                errors.append(f"物品 {item_name}: {stat_key} 必须为非负数")
            for rate_key in ("accuracy_bonus", "crit_bonus", "dodge_bonus"):
                if rate_key in info:
                    try:
                        rate = float(info[rate_key])
                        if not -0.50 <= rate <= 0.50:
                            errors.append(f"物品 {item_name}: {rate_key} 必须在 -0.50~0.50")
                    except (TypeError, ValueError):
                        errors.append(f"物品 {item_name}: {rate_key} 必须为数字")
            quality = info.get("quality", "普通")
            if quality not in ("普通", "精良", "稀有", "史诗"):
                errors.append(f"物品 {item_name}: quality 必须为 普通/精良/稀有/史诗")
            if "base_item" in info and info.get("base_item") not in items:
                errors.append(f"物品 {item_name}: base_item 不存在 {info.get('base_item')}")
            if "affix_count" in info:
                if not isinstance(info["affix_count"], int) or isinstance(info["affix_count"], bool) or not 0 <= info["affix_count"] <= 3:
                    errors.append(f"物品 {item_name}: affix_count 必须为 0~3 整数")
            if info.get("type") in ("weapon", "armor"):
                for field, minimum in (("enhance_max", 0), ("enhance_ore_cost", 1), ("enhance_gold_cost", 0)):
                    if field in info and (not isinstance(info[field], int) or isinstance(info[field], bool) or info[field] < minimum):
                        errors.append(f"物品 {item_name}: {field} 必须为不小于 {minimum} 的整数")
                if "enhance_max" in info and int(info.get("enhance_max", 0)) > 20:
                    errors.append(f"物品 {item_name}: enhance_max 不得超过 20")
            variants = info.get("quality_variants", {})
            if variants:
                if not isinstance(variants, dict):
                    errors.append(f"物品 {item_name}: quality_variants 必须为对象")
                else:
                    for q, variant in variants.items():
                        if q not in ("精良", "稀有", "史诗"):
                            errors.append(f"物品 {item_name}: quality_variants 含未知品质 {q}")
                        if variant not in items:
                            errors.append(f"物品 {item_name}: quality_variants 指向不存在物品 {variant}")
            attr_bonus = info.get("attribute_bonus", {})
            if not isinstance(attr_bonus, dict):
                errors.append(f"物品 {item_name}: attribute_bonus 必须为对象")
            else:
                for attr_name, attr_value in attr_bonus.items():
                    if attr_name not in ("strength", "constitution", "internal", "agility", "insight"):
                        errors.append(f"物品 {item_name}: 未知属性词条 {attr_name}")
                    if not isinstance(attr_value, int) or isinstance(attr_value, bool):
                        errors.append(f"物品 {item_name}: attribute_bonus.{attr_name} 必须为整数")
        price = info.get("price", 0)
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
            errors.append(f"物品 {item_name}: price 必须为非负数")

    if not isinstance(build_profiles, dict):
        errors.append("build_profiles.json 根节点必须为对象")
    else:
        for profile_name, profile in build_profiles.items():
            if not isinstance(profile, dict):
                errors.append(f"Build 流派 {profile_name}: 必须为对象")
                continue
            required = profile.get("required", {})
            bonuses = profile.get("bonuses", {})
            if not isinstance(required, dict) or not isinstance(bonuses, dict):
                errors.append(f"Build 流派 {profile_name}: required/bonuses 必须为对象")
                continue
            weapon_base = required.get("weapon_base")
            armor_base = required.get("armor_base")
            if weapon_base and weapon_base not in items:
                errors.append(f"Build 流派 {profile_name}: weapon_base 不存在 {weapon_base}")
            if armor_base and armor_base not in items:
                errors.append(f"Build 流派 {profile_name}: armor_base 不存在 {armor_base}")
            attrs = required.get("attributes", {})
            if not isinstance(attrs, dict):
                errors.append(f"Build 流派 {profile_name}: attributes 必须为对象")
            else:
                for attr, minimum in attrs.items():
                    if attr not in ("strength", "constitution", "internal", "agility", "insight"):
                        errors.append(f"Build 流派 {profile_name}: 未知属性 {attr}")
                    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
                        errors.append(f"Build 流派 {profile_name}: {attr} 门槛必须为非负整数")
            for key in ("atk", "defense"):
                if key in bonuses and (not isinstance(bonuses[key], int) or isinstance(bonuses[key], bool)):
                    errors.append(f"Build 流派 {profile_name}: {key} 必须为整数")
            for key in ("hit_bonus", "crit_bonus", "dodge_bonus"):
                if key in bonuses:
                    try:
                        if not -0.50 <= float(bonuses[key]) <= 0.50:
                            errors.append(f"Build 流派 {profile_name}: {key} 必须在 -0.50~0.50")
                    except (TypeError, ValueError):
                        errors.append(f"Build 流派 {profile_name}: {key} 必须为数字")

    if not isinstance(sects, dict) or not sects:
        errors.append("sects.json 必须为非空对象")
    else:
        for sect_name, info in sects.items():
            if not isinstance(info, dict):
                errors.append(f"门派 {sect_name}: 必须为对象"); continue
            if not isinstance(info.get("ranks", []), list) or not info.get("ranks"):
                errors.append(f"门派 {sect_name}: ranks 必须为非空数组")
            else:
                last = -10**9
                for idx, rank in enumerate(info["ranks"], 1):
                    if not isinstance(rank, dict):
                        errors.append(f"门派 {sect_name}: ranks[{idx}] 必须为对象"); continue
                    name = rank.get("name")
                    minimum = rank.get("min_reputation")
                    if not isinstance(name, str) or not name:
                        errors.append(f"门派 {sect_name}: ranks[{idx}] name 非法")
                    if not isinstance(minimum, int) or isinstance(minimum, bool):
                        errors.append(f"门派 {sect_name}: ranks[{idx}] min_reputation 必须为整数")
                    elif minimum < last:
                        errors.append(f"门派 {sect_name}: ranks 声望门槛必须递增")
                    else:
                        last = minimum
            try:
                if not -1000 <= int(info.get("initial_reputation", 0)) <= 1000:
                    errors.append(f"门派 {sect_name}: initial_reputation 超出范围")
            except (TypeError, ValueError):
                errors.append(f"门派 {sect_name}: initial_reputation 必须为整数")
            if not isinstance(info.get("exclusive_skills", []), list):
                errors.append(f"门派 {sect_name}: exclusive_skills 必须为数组")
            else:
                known_skills = {sk.get("name") for group in skills.values() if isinstance(group, list) for sk in group if isinstance(sk, dict)}
                for sk in info.get("exclusive_skills", []):
                    if sk not in known_skills:
                        errors.append(f"门派 {sect_name}: 专属武学不存在 {sk}")
            if not isinstance(info.get("relations", {}), dict):
                errors.append(f"门派 {sect_name}: relations 必须为对象")
            else:
                for other in info.get("relations", {}):
                    if other not in sects:
                        errors.append(f"门派 {sect_name}: relation 引用不存在门派 {other}")

    # 门派晋升剧情标记与任务线必须能在真实数据中找到来源，避免把玩家永远卡在门槛前。
    def collect_quest_flags(node, bucket):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "set_flags" and isinstance(value, dict):
                    bucket.update(str(flag) for flag in value.keys())
                elif key == "flag" and isinstance(value, str) and value:
                    bucket.add(value)
                collect_quest_flags(value, bucket)
        elif isinstance(node, list):
            for value in node:
                collect_quest_flags(value, bucket)

    produced_flags = set()
    for q_info in quests.values():
        collect_quest_flags(q_info, produced_flags)
    for npc_info in npcs.values():
        collect_quest_flags(npc_info, produced_flags)
    # 少量由运行时逻辑直接写入的仪礼标记，不在任务/NPC数据里重复声明。
    runtime_promotion_flags = {
        "sect:shaolin:ordination:novice",
        "sect:shaolin:ordination:full",
    }
    produced_flags.update(runtime_promotion_flags)

    for sect_name, info in (sects or {}).items():
        if not isinstance(info, dict):
            continue
        promotion_flags = info.get("promotion_flags", {}) or {}
        if not isinstance(promotion_flags, dict):
            errors.append(f"门派 {sect_name}: promotion_flags 必须为对象")
        else:
            rank_count = len(info.get("ranks", []) or [])
            for target, flags in promotion_flags.items():
                target_text = str(target)
                if not target_text.isdigit() or not 1 <= int(target_text) <= max(rank_count - 1, 0):
                    errors.append(f"门派 {sect_name}: promotion_flags 阶位 {target} 非法")
                if not isinstance(flags, list) or not flags:
                    errors.append(f"门派 {sect_name}: promotion_flags.{target} 必须为非空数组")
                    continue
                for flag in flags:
                    if not isinstance(flag, str) or not flag:
                        errors.append(f"门派 {sect_name}: promotion_flags.{target} 包含非法标记")
                    elif flag not in produced_flags:
                        errors.append(f"门派 {sect_name}: promotion_flags.{target} 标记无来源 {flag}")
        questline = info.get("questline", []) or []
        if not isinstance(questline, list):
            errors.append(f"门派 {sect_name}: questline 必须为数组")
        else:
            seen_quests = set()
            for idx, entry in enumerate(questline, 1):
                if isinstance(entry, str):
                    quest_name = entry
                elif isinstance(entry, dict):
                    quest_name = entry.get("quest")
                    if "optional" in entry and not isinstance(entry.get("optional"), bool):
                        errors.append(f"门派 {sect_name}: questline[{idx}].optional 必须为布尔值")
                else:
                    errors.append(f"门派 {sect_name}: questline[{idx}] 必须为字符串或对象")
                    continue
                if not isinstance(quest_name, str) or not quest_name:
                    errors.append(f"门派 {sect_name}: questline[{idx}].quest 非法")
                elif quest_name not in quests:
                    errors.append(f"门派 {sect_name}: questline[{idx}] 引用不存在任务 {quest_name}")
                elif quest_name in seen_quests:
                    errors.append(f"门派 {sect_name}: questline 重复任务 {quest_name}")
                else:
                    seen_quests.add(quest_name)

    for q_name, q_info in quests.items():
        if not isinstance(q_info, dict):
            continue
        reward = q_info.get("reward", {}) or {}
        if not isinstance(reward, dict):
            errors.append(f"任务 {q_name}: reward 必须为对象")
        else:
            sr = reward.get("sect_reputation", {}) or {}
            if not isinstance(sr, dict):
                errors.append(f"任务 {q_name}: reward.sect_reputation 必须为对象")
            else:
                for sect_name, delta in sr.items():
                    if sect_name not in sects:
                        errors.append(f"任务 {q_name}: sect_reputation 引用不存在门派 {sect_name}")
                    if not isinstance(delta, int) or isinstance(delta, bool):
                        errors.append(f"任务 {q_name}: sect_reputation.{sect_name} 必须为整数")
        req = q_info.get("requires", {}) or {}
        difficulty = q_info.get("difficulty")
        if difficulty is not None and difficulty not in {"入门", "普通", "进阶", "高难", "重大"}:
            errors.append(f"任务 {q_name}: difficulty 必须为 入门/普通/进阶/高难/重大")
        sect_rule = req.get("sect") if isinstance(req, dict) else None
        if sect_rule is not None:
            allowed = sect_rule if isinstance(sect_rule, list) else [sect_rule] if isinstance(sect_rule, str) else []
            for sect_name in allowed:
                if sect_name not in sects:
                    errors.append(f"任务 {q_name}: requires.sect 引用不存在门派 {sect_name}")

    for n,info in npcs.items():
        for item in info.get("shop",[]) or []:
            if item not in items: errors.append(f"NPC {n}: 商店物品 {item} 不存在")
        for rate_name in ("buy_rate", "sell_rate"):
            if rate_name in info:
                try:
                    rate = float(info[rate_name])
                    if rate < 0 or (rate_name == "sell_rate" and rate > 1):
                        errors.append(f"NPC {n}: {rate_name} 必须在允许范围内")
                except (TypeError, ValueError):
                    errors.append(f"NPC {n}: {rate_name} 必须是数字")
        for q in info.get("quests",[]) or []:
            if q not in quests: errors.append(f"NPC {n}: 任务 {q} 不存在")
        if "state_profile" in info:
            profile = info.get("state_profile")
            if not isinstance(profile, dict):
                errors.append(f"NPC {n}: state_profile 必须为对象")
            else:
                default_state = str(profile.get("default", "normal"))
                allowed_states = profile.get("allowed", [])
                valid_states = {"normal", "busy", "injured", "fear", "angry", "away", "event_affected"}
                if default_state not in valid_states:
                    errors.append(f"NPC {n}: state_profile.default 非法 {default_state}")
                if not isinstance(allowed_states, list) or not allowed_states:
                    errors.append(f"NPC {n}: state_profile.allowed 必须为非空数组")
                else:
                    for state in allowed_states:
                        if state not in valid_states:
                            errors.append(f"NPC {n}: state_profile.allowed 包含非法状态 {state}")
        tier = info.get("schedule_tier")
        if "schedule_tier" in info and tier not in SCHEDULE_TIERS:
            errors.append(f"NPC {n}: schedule_tier 必须为 T1/T2/T3")
        for flag in ("instant", "always_available"):
            if flag in info and not isinstance(info.get(flag), bool):
                errors.append(f"NPC {n}: {flag} 必须为布尔值")
        if "scene_status" in info and (not isinstance(info.get("scene_status"), str) or not info.get("scene_status").strip()):
            errors.append(f"NPC {n}: scene_status 必须为非空字符串")
        if "home_room" in info:
            home = info.get("home_room")
            if not isinstance(home, str) or home not in rooms:
                errors.append(f"NPC {n}: home_room 引用不存在房间 {home}")
            elif tier == "T1" and rooms[home].get("safe") is not True:
                errors.append(f"NPC {n}: T1 home_room 必须位于安全房间 {home}")
        if "daily_schedule" in info:
            schedule = info.get("daily_schedule")
            if not isinstance(schedule, list):
                errors.append(f"NPC {n}: daily_schedule 必须为数组")
            else:
                covered = set()
                for idx, entry in enumerate(schedule, 1):
                    if not isinstance(entry, dict):
                        errors.append(f"NPC {n}: daily_schedule[{idx}] 必须为对象"); continue
                    for field in ("start", "end"):
                        if not isinstance(entry.get(field), int) or isinstance(entry.get(field), bool) or not 0 <= entry.get(field) <= 23:
                            errors.append(f"NPC {n}: daily_schedule[{idx}].{field} 必须为 0~23 整数")
                    if entry.get("state") not in {"normal", "busy", "injured", "fear", "angry", "away", "event_affected"}:
                        errors.append(f"NPC {n}: daily_schedule[{idx}].state 非法")
                    if "location" in entry:
                        location = entry.get("location")
                        if location is not None and (not isinstance(location, str) or location not in rooms):
                            errors.append(f"NPC {n}: daily_schedule[{idx}].location 引用不存在房间 {location}")
                    if "instant" in entry and not isinstance(entry.get("instant"), bool):
                        errors.append(f"NPC {n}: daily_schedule[{idx}].instant 必须为布尔值")
                    start, end = entry.get("start"), entry.get("end")
                    if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool):
                        if start == end:
                            errors.append(f"NPC {n}: daily_schedule[{idx}] 时间段不能 start=end")
                        elif 0 <= start <= 23 and 0 <= end <= 23:
                            hours = schedule_hours(start, end)
                            overlap = covered & hours
                            if overlap:
                                errors.append(f"NPC {n}: daily_schedule 时间段重叠，冲突小时 {sorted(overlap)}")
                            covered |= hours
                if tier in ("T1", "T2") and covered != set(range(24)):
                    errors.append(f"NPC {n}: {tier} 日程未覆盖 24 小时，缺少 {sorted(set(range(24)) - covered)}")
                if tier == "T1":
                    for idx, entry in enumerate(schedule, 1):
                        if not isinstance(entry, dict):
                            continue
                        if entry.get("location") is None:
                            errors.append(f"NPC {n}: T1 daily_schedule[{idx}] 不得离场（location 不能为空）")
                        if entry.get("instant") is not True:
                            errors.append(f"NPC {n}: T1 daily_schedule[{idx}] 必须 instant=true")
        if tier == "T1":
            if not isinstance(info.get("daily_schedule"), list) or not info.get("daily_schedule"):
                errors.append(f"NPC {n}: T1 必须配置非空 daily_schedule")
            if "home_room" not in info:
                errors.append(f"NPC {n}: T1 必须配置 home_room")
        elif tier == "T2":
            if not isinstance(info.get("daily_schedule"), list) or not info.get("daily_schedule"):
                errors.append(f"NPC {n}: T2 必须配置非空 daily_schedule")
        elif tier == "T3":
            if info.get("always_available") is not True:
                errors.append(f"NPC {n}: T3 必须设置 always_available=true")
            if info.get("daily_schedule"):
                errors.append(f"NPC {n}: T3 不应配置轮转日程")
            if "home_room" not in info:
                errors.append(f"NPC {n}: T3 必须配置 home_room")
            if not isinstance(info.get("scene_status"), str) or not info.get("scene_status").strip():
                errors.append(f"NPC {n}: T3 必须配置 scene_status")
        if "sect_profile" in info:
            profile = info.get("sect_profile")
            if not isinstance(profile, dict):
                errors.append(f"NPC {n}: sect_profile 必须为对象")
            else:
                valid_stances = {"preferred", "friendly", "wary", "opposed"}
                for stance in valid_stances:
                    values = profile.get(stance, []) or []
                    if not isinstance(values, list):
                        errors.append(f"NPC {n}: sect_profile.{stance} 必须为数组")
                    else:
                        for sect_name in values:
                            if sect_name not in sects:
                                errors.append(f"NPC {n}: sect_profile.{stance} 引用不存在门派 {sect_name}")

        for key in ("event_reactions",):
            reactions = info.get(key, []) or []
            if not isinstance(reactions, list):
                errors.append(f"NPC {n}: {key} 必须为数组")
            else:
                for idx, reaction in enumerate(reactions, 1):
                    if not isinstance(reaction, dict):
                        errors.append(f"NPC {n}: {key}[{idx}] 必须为对象"); continue
                    if not reaction.get("event") or not isinstance(reaction.get("event"), str):
                        errors.append(f"NPC {n}: {key}[{idx}] event 必须为字符串")
                    elif reaction.get("event") not in world_events:
                        errors.append(f"NPC {n}: {key}[{idx}] 引用不存在世界事件 {reaction.get('event')}")
                    if reaction.get("state") not in {"normal", "busy", "injured", "fear", "angry", "away", "event_affected"}:
                        errors.append(f"NPC {n}: {key}[{idx}] state 非法")
                    if "duration" in reaction and (not isinstance(reaction.get("duration"), int) or reaction.get("duration") < 0):
                        errors.append(f"NPC {n}: {key}[{idx}] duration 必须为非负整数")
                    if "location" in reaction and reaction.get("location") not in rooms:
                        errors.append(f"NPC {n}: {key}[{idx}] location 引用不存在房间 {reaction.get('location')}")
        q_reactions = info.get("quest_reactions", {}) or {}
        if not isinstance(q_reactions, dict):
            errors.append(f"NPC {n}: quest_reactions 必须为对象")
        else:
            for q_name, outcomes in q_reactions.items():
                if q_name not in quests:
                    errors.append(f"NPC {n}: quest_reactions 引用不存在任务 {q_name}")
                if not isinstance(outcomes, dict):
                    errors.append(f"NPC {n}: quest_reactions.{q_name} 必须为对象"); continue
                for outcome, reaction in outcomes.items():
                    if outcome not in {"complete", "fail", "abandon"} or not isinstance(reaction, dict):
                        errors.append(f"NPC {n}: quest_reactions.{q_name}.{outcome} 格式非法"); continue
                    if reaction.get("state") not in {"normal", "busy", "injured", "fear", "angry", "away", "event_affected"}:
                        errors.append(f"NPC {n}: quest_reactions.{q_name}.{outcome} state 非法")
                    if "duration" in reaction and (not isinstance(reaction.get("duration"), int) or reaction.get("duration") < 0):
                        errors.append(f"NPC {n}: quest_reactions.{q_name}.{outcome} duration 必须为非负整数")
                    if "location" in reaction and reaction.get("location") not in rooms:
                        errors.append(f"NPC {n}: quest_reactions.{q_name}.{outcome} location 引用不存在房间 {reaction.get('location')}")

        if "initial_relation" in info:
            try:
                initial_relation = int(info["initial_relation"])
                if initial_relation < -100 or initial_relation > 100:
                    errors.append(f"NPC {n}: initial_relation 必须在 -100~100")
            except (TypeError, ValueError):
                errors.append(f"NPC {n}: initial_relation 必须为整数")
        if "talk_relation_cap" in info:
            try:
                if int(info["talk_relation_cap"]) < 0:
                    errors.append(f"NPC {n}: talk_relation_cap 不能为负数")
            except (TypeError, ValueError):
                errors.append(f"NPC {n}: talk_relation_cap 必须为整数")
        if "dialogue_choices" in info:
            if not isinstance(info["dialogue_choices"], list): errors.append(f"NPC {n}: dialogue_choices 必须为数组")
            else:
                choice_ids = set()
                for idx, choice in enumerate(info["dialogue_choices"], 1):
                    if not isinstance(choice, dict): errors.append(f"NPC {n}: dialogue_choices[{idx}] 必须为对象"); continue
                    if not isinstance(choice.get("keywords", []), list) or not choice.get("keywords"):
                        errors.append(f"NPC {n}: dialogue_choices[{idx}] keywords 必须为非空数组")
                    cid = str(choice.get("id", f"choice_{idx}"))
                    if cid in choice_ids:
                        errors.append(f"NPC {n}: dialogue_choices[{idx}] id 重复 {cid}")
                    choice_ids.add(cid)
                    try: int(choice.get("relation_delta", 0))
                    except (TypeError, ValueError): errors.append(f"NPC {n}: dialogue_choices[{idx}] relation_delta 非法")
                    if "once" in choice and not isinstance(choice.get("once"), bool):
                        errors.append(f"NPC {n}: dialogue_choices[{idx}] once 必须为布尔值")
                    if "requires" in choice:
                        requires = choice.get("requires")
                        if not isinstance(requires, dict):
                            errors.append(f"NPC {n}: dialogue_choices[{idx}] requires 必须为对象")
                        else:
                            rr = requires.get("relations", {}) or {}
                            if not isinstance(rr, dict):
                                errors.append(f"NPC {n}: dialogue_choices[{idx}] requires.relations 必须为对象")
                            else:
                                for rel_npc in rr:
                                    if rel_npc not in npcs:
                                        errors.append(f"NPC {n}: dialogue_choices[{idx}] 引用不存在的关系 NPC {rel_npc}")
                    if "effects" in choice:
                        effects = choice.get("effects")
                        if not isinstance(effects, dict):
                            errors.append(f"NPC {n}: dialogue_choices[{idx}] effects 必须为对象")
                        else:
                            effect_relations = effects.get("relations", {}) or {}
                            if not isinstance(effect_relations, dict):
                                errors.append(f"NPC {n}: dialogue_choices[{idx}] effects.relations 必须为对象")
                            else:
                                for rel_npc in effect_relations:
                                    if rel_npc not in npcs:
                                        errors.append(f"NPC {n}: dialogue_choices[{idx}] effects 引用不存在的关系 NPC {rel_npc}")
        if "memory_profile" in info:
            profile = info.get("memory_profile")
            if not isinstance(profile, dict):
                errors.append(f"NPC {n}: memory_profile 必须为对象")
            else:
                for flag in ("remember_player_actions", "share_player_memories", "receive_player_memories"):
                    if flag in profile and not isinstance(profile.get(flag), bool):
                        errors.append(f"NPC {n}: memory_profile.{flag} 必须为布尔值")
                for field in ("memory_share_min_bond", "memory_propagation_loss"):
                    if field in profile:
                        try:
                            value = int(profile[field])
                            if value < 0 or value > 100:
                                errors.append(f"NPC {n}: memory_profile.{field} 必须在 0~100")
                        except (TypeError, ValueError):
                            errors.append(f"NPC {n}: memory_profile.{field} 必须为整数")

        if "relation_dialogue" in info:
            entries = info.get("relation_dialogue")
            if not isinstance(entries, list):
                errors.append(f"NPC {n}: relation_dialogue 必须为数组")
            else:
                relation_ids = set()
                for idx, entry in enumerate(entries, 1):
                    if not isinstance(entry, dict):
                        errors.append(f"NPC {n}: relation_dialogue[{idx}] 必须为对象")
                        continue
                    try:
                        minimum = int(entry.get("min_relation", 0))
                        if minimum < -100 or minimum > 100:
                            errors.append(f"NPC {n}: relation_dialogue[{idx}] min_relation 必须在 -100~100")
                    except (TypeError, ValueError):
                        errors.append(f"NPC {n}: relation_dialogue[{idx}] min_relation 必须为整数")
                    rid = str(entry.get("id", f"relation_{idx}"))
                    if rid in relation_ids:
                        errors.append(f"NPC {n}: relation_dialogue[{idx}] id 重复 {rid}")
                    relation_ids.add(rid)
                    if "once" in entry and not isinstance(entry.get("once"), bool):
                        errors.append(f"NPC {n}: relation_dialogue[{idx}] once 必须为布尔值")
                    if "requires" in entry and not isinstance(entry.get("requires"), dict):
                        errors.append(f"NPC {n}: relation_dialogue[{idx}] requires 必须为对象")
                    if "effects" in entry and not isinstance(entry.get("effects"), dict):
                        errors.append(f"NPC {n}: relation_dialogue[{idx}] effects 必须为对象")
                    reward = entry.get("reward")
                    if reward is not None:
                        if not isinstance(reward, dict):
                            errors.append(f"NPC {n}: relation_dialogue[{idx}] reward 必须为对象")
                        else:
                            for field in ("exp", "gold"):
                                if field in reward:
                                    try:
                                        if int(reward[field]) < 0:
                                            errors.append(f"NPC {n}: relation_dialogue[{idx}] {field} 不能为负数")
                                    except (TypeError, ValueError):
                                        errors.append(f"NPC {n}: relation_dialogue[{idx}] {field} 必须为整数")
                            reward_items = []
                            if reward.get("item"):
                                reward_items.append(reward.get("item"))
                            for item_entry in reward.get("items", []) or []:
                                if isinstance(item_entry, str):
                                    reward_items.append(item_entry)
                                elif isinstance(item_entry, dict):
                                    reward_items.append(item_entry.get("item") or item_entry.get("name"))
                            for item_name in reward_items:
                                if item_name and item_name not in items:
                                    errors.append(f"NPC {n}: relation_dialogue[{idx}] 奖励物品不存在 {item_name}")

        role = info.get("perception_role")
        if role is not None:
            if not isinstance(role, str) or not role.strip():
                errors.append(f"NPC {n}: perception_role 必须为非空字符串")
            elif role not in perception_templates:
                errors.append(f"NPC {n}: perception_role 未知职业模板 {role}")

        if "conditional_dialogue" in info:
            entries = info.get("conditional_dialogue")
            if not isinstance(entries, list):
                errors.append(f"NPC {n}: conditional_dialogue 必须为数组")
            else:
                for idx, entry in enumerate(entries, 1):
                    validate_conditional_entry(entry, f"NPC {n}: conditional_dialogue[{idx}]", errors)
    for sect_name, skill_list in skills.items():
        if not isinstance(skill_list, list):
            errors.append(f"武学组 {sect_name}: 必须为数组")
            continue
        skill_names = set()
        for idx, skill in enumerate(skill_list, 1):
            if not isinstance(skill, dict):
                errors.append(f"武学 {sect_name}[{idx}]: 必须为对象")
                continue
            name = skill.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"武学 {sect_name}[{idx}]: name 非法")
            elif name in skill_names:
                errors.append(f"武学 {sect_name}: name 重复 {name}")
            skill_names.add(name)
            for field in ("level", "learn_min_reputation", "learn_min_rank", "mastery_max", "mastery_gain", "mastery_mp_reduction"):
                try:
                    value = int(skill.get(field, 0))
                    if value < 0:
                        errors.append(f"武学 {sect_name}/{name}: {field} 不能为负数")
                except (TypeError, ValueError):
                    errors.append(f"武学 {sect_name}/{name}: {field} 必须为整数")
            if int(skill.get("mastery_max", 100) or 100) < 1:
                errors.append(f"武学 {sect_name}/{name}: mastery_max 必须 >= 1")
            try:
                power_bonus = float(skill.get("mastery_power_per_level", 0.0))
                if power_bonus < 0:
                    errors.append(f"武学 {sect_name}/{name}: mastery_power_per_level 不能为负数")
            except (TypeError, ValueError):
                errors.append(f"武学 {sect_name}/{name}: mastery_power_per_level 必须为数字")

    for ename, einfo in enemies.items():
        level = einfo.get("level", 1)
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 30:
            errors.append(f"敌人 {ename}: level 必须为 1~30 整数")
        tier = einfo.get("tier", "normal")
        if tier not in ("normal", "ranged", "elite", "boss"):
            errors.append(f"敌人 {ename}: tier 非法 {tier}")
        ai = einfo.get("ai", {}) or {}
        if not isinstance(ai, dict):
            errors.append(f"敌人 {ename}: ai 必须为对象")
        else:
            if "style" in ai and ai.get("style") not in ("standard", "beast", "aggressive", "defensive", "tactical", "ranged", "elite", "boss"):
                errors.append(f"敌人 {ename}: ai.style 非法 {ai.get('style')}")
            if "faction" in ai and not isinstance(ai.get("faction"), str):
                errors.append(f"敌人 {ename}: ai.faction 必须为字符串")
        exp = einfo.get("exp", 0)
        gold = einfo.get("gold", 0)
        for field, value in (("exp", exp), ("gold", gold)):
            if isinstance(value, dict):
                if "amount" not in value and ("min" not in value or "max" not in value):
                    errors.append(f"敌人 {ename}: {field} 奖励必须是整数、amount 或 min/max")
                else:
                    try:
                        low = int(value.get("min", value.get("amount", 0)))
                        high = int(value.get("max", value.get("amount", low)))
                        if low < 0 or high < 0 or low > high:
                            errors.append(f"敌人 {ename}: {field} min/max 非法")
                    except (TypeError, ValueError):
                        errors.append(f"敌人 {ename}: {field} 奖励数值非法")
            elif not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                errors.append(f"敌人 {ename}: {field} 奖励数值非法")
        equipment = einfo.get("equipment", {}) or {}
        if not isinstance(equipment, dict):
            errors.append(f"敌人 {ename}: equipment 必须为对象")
        else:
            for slot, item_name in equipment.items():
                if slot not in ("weapon", "armor"):
                    errors.append(f"敌人 {ename}: equipment 部位非法 {slot}")
                if item_name not in items:
                    errors.append(f"敌人 {ename}: 装备物品不存在 {item_name}")
                elif slot == "weapon" and items[item_name].get("type") != "weapon":
                    errors.append(f"敌人 {ename}: weapon 配置的 {item_name} 不是武器")
                elif slot == "armor" and items[item_name].get("type") != "armor":
                    errors.append(f"敌人 {ename}: armor 配置的 {item_name} 不是防具")
        if "equipment_drop_chance" in einfo:
            try:
                if not 0 <= float(einfo["equipment_drop_chance"]) <= 0.25:
                    errors.append(f"敌人 {ename}: equipment_drop_chance 必须在 0~0.25")
            except (TypeError, ValueError):
                errors.append(f"敌人 {ename}: equipment_drop_chance 非法")
        if "equipment_quality_pool" in einfo:
            pool = einfo.get("equipment_quality_pool")
            worn = []
            if isinstance(equipment, dict):
                worn = [equipment.get(slot) for slot in ("weapon", "armor") if equipment.get(slot) in items]
            if not isinstance(pool, list) or not pool:
                errors.append(f"敌人 {ename}: equipment_quality_pool 必须为非空数组")
            else:
                if not worn or not any(items.get(item, {}).get("quality_variants") for item in worn):
                    errors.append(f"敌人 {ename}: equipment_quality_pool 需要至少一件带品质变体的穿戴装备")
                try:
                    if float(einfo.get("equipment_drop_chance", 0)) <= 0:
                        errors.append(f"敌人 {ename}: equipment_quality_pool 需要 equipment_drop_chance > 0")
                except (TypeError, ValueError):
                    pass
                total = 0.0
                for qidx, entry in enumerate(pool, 1):
                    if not isinstance(entry, dict) or entry.get("quality") not in ("精良", "稀有", "史诗"):
                        errors.append(f"敌人 {ename}: equipment_quality_pool[{qidx}] 品质非法")
                        continue
                    try:
                        chance = float(entry.get("chance", 0))
                        if not 0 <= chance <= 1:
                            errors.append(f"敌人 {ename}: equipment_quality_pool[{qidx}] chance 必须在 0~1")
                        total += max(0.0, chance)
                    except (TypeError, ValueError):
                        errors.append(f"敌人 {ename}: equipment_quality_pool[{qidx}] chance 非法")
                    if not any(
                        items.get(item, {}).get("quality_variants", {}).get(entry.get("quality")) in items
                        for item in worn
                    ):
                        errors.append(f"敌人 {ename}: equipment_quality_pool[{qidx}] 的 {entry.get('quality')} 品质没有对应变体")
                if total > 1.0 + 1e-9:
                    errors.append(f"敌人 {ename}: equipment_quality_pool 总概率不得超过 1")
        for field in ("respawn_seconds", "corpse_seconds"):
            if field in einfo:
                try:
                    if not 30 <= float(einfo[field]) <= 3600:
                        errors.append(f"敌人 {ename}: {field} 必须在 30~3600 秒")
                except (TypeError, ValueError):
                    errors.append(f"敌人 {ename}: {field} 非法")
        manual_drop = einfo.get("manual_drop")
        if manual_drop is not None:
            if not isinstance(manual_drop, dict) or manual_drop.get("item") not in items:
                errors.append(f"敌人 {ename}: manual_drop 必须引用存在的秘籍物品")
            else:
                try:
                    if not 0 <= float(manual_drop.get("chance", 0)) <= 0.01:
                        errors.append(f"敌人 {ename}: manual_drop.chance 必须在 0~0.01")
                except (TypeError, ValueError):
                    errors.append(f"敌人 {ename}: manual_drop.chance 非法")
        for variant_index, variant in enumerate(einfo.get("loadout_variants", []) or [], 1):
            if not isinstance(variant, dict):
                errors.append(f"敌人 {ename}: loadout_variants[{variant_index}] 必须为对象")
                continue
            for slot, item_name in (variant.get("equipment", {}) or {}).items():
                if item_name not in items:
                    errors.append(f"敌人 {ename}: loadout_variants[{variant_index}] 装备物品不存在 {item_name}")
                elif slot == "weapon" and items[item_name].get("type") != "weapon":
                    errors.append(f"敌人 {ename}: loadout_variants[{variant_index}] 的 {item_name} 不是武器")
                elif slot == "armor" and items[item_name].get("type") != "armor":
                    errors.append(f"敌人 {ename}: loadout_variants[{variant_index}] 的 {item_name} 不是防具")
        if manual_drop and isinstance(manual_drop, dict):
            manual_item = items.get(manual_drop.get("item"), {})
            if manual_item.get("type") != "manual" or manual_item.get("teaches_skill") not in {sk.get("name") for group in skills.values() if isinstance(group, list) for sk in group if isinstance(sk, dict)}:
                errors.append(f"敌人 {ename}: 秘籍掉落物必须能教授现有武学")
        for idx, drop in enumerate(einfo.get("drops", []) or [], 1):
            if not isinstance(drop, dict) or not drop.get("item"):
                errors.append(f"敌人 {ename}: drops[{idx}] 缺少 item")
                continue
            if drop["item"] not in items:
                errors.append(f"敌人 {ename}: 掉落物品不存在 {drop['item']}")
            if "chance" in drop:
                try:
                    chance = float(drop["chance"])
                    if not 0 <= chance <= 1:
                        errors.append(f"敌人 {ename}: drops[{idx}] chance 必须在 0~1")
                except (TypeError, ValueError):
                    errors.append(f"敌人 {ename}: drops[{idx}] chance 非法")
            if "quantity" in drop and (not isinstance(drop["quantity"], int) or isinstance(drop["quantity"], bool) or drop["quantity"] < 1):
                errors.append(f"敌人 {ename}: drops[{idx}] quantity 必须为正整数")
            if "min_qty" in drop or "max_qty" in drop:
                try:
                    low = int(drop.get("min_qty", drop.get("max_qty", 1)))
                    high = int(drop.get("max_qty", low))
                    if low < 1 or high < 1 or low > high:
                        errors.append(f"敌人 {ename}: drops[{idx}] min_qty/max_qty 非法")
                except (TypeError, ValueError):
                    errors.append(f"敌人 {ename}: drops[{idx}] min_qty/max_qty 非法")
            if "rolls" in drop and (not isinstance(drop["rolls"], int) or isinstance(drop["rolls"], bool) or drop["rolls"] < 1):
                errors.append(f"敌人 {ename}: drops[{idx}] rolls 必须为正整数")
            if "quality_pool" in drop:
                pool = drop.get("quality_pool")
                if not isinstance(pool, list):
                    errors.append(f"敌人 {ename}: drops[{idx}] quality_pool 必须为数组")
                else:
                    total = 0.0
                    for qidx, entry in enumerate(pool, 1):
                        if not isinstance(entry, dict) or entry.get("quality") not in ("精良", "稀有", "史诗"):
                            errors.append(f"敌人 {ename}: drops[{idx}] quality_pool[{qidx}] 品质非法")
                            continue
                        try:
                            chance = float(entry.get("chance", 0))
                            if not 0 <= chance <= 1:
                                errors.append(f"敌人 {ename}: drops[{idx}] quality_pool[{qidx}] chance 必须在 0~1")
                            total += max(0.0, chance)
                        except (TypeError, ValueError):
                            errors.append(f"敌人 {ename}: drops[{idx}] quality_pool[{qidx}] chance 非法")
                        variant = items.get(drop["item"], {}).get("quality_variants", {}).get(entry.get("quality"))
                        if variant not in items:
                            errors.append(f"敌人 {ename}: drops[{idx}] 没有 {entry.get('quality')} 对应的品质变体")
                    if total > 1.0 + 1e-9:
                        errors.append(f"敌人 {ename}: drops[{idx}] quality_pool 总概率不得超过 1")

    for region_id, rinfo in world_regions.items():
        exposure = rinfo.get("faction_exposure", []) or []
        if not isinstance(exposure, list):
            errors.append(f"区域 {region_id}: faction_exposure 必须为数组")
        else:
            for faction in exposure:
                if faction not in factions: errors.append(f"区域 {region_id}: faction_exposure 势力不存在 {faction}")
        ecology = rinfo.get("region_ecology", {}) or {}
        if not isinstance(ecology, dict):
            errors.append(f"区域 {region_id}: region_ecology 必须为对象")
        else:
            for key in ("security_base", "commerce_base", "travel_base"):
                if not isinstance(ecology.get(key, 70), int) or isinstance(ecology.get(key, 70), bool) or not 0 <= int(ecology.get(key, 70)) <= 100:
                    errors.append(f"区域 {region_id}: region_ecology.{key} 必须为 0~100 整数")
        effects = rinfo.get("conflict_effects", {}) or {}
        if not isinstance(effects, dict): errors.append(f"区域 {region_id}: conflict_effects 必须为对象")
        else:
            for level, effect in effects.items():
                if level not in ("calm", "tension", "confrontation", "conflict", "escalation", "war") or not isinstance(effect, dict):
                    errors.append(f"区域 {region_id}: conflict_effects.{level} 格式非法")
                    continue
                for key in ("security", "commerce", "travel"):
                    if key in effect and not isinstance(effect[key], int): errors.append(f"区域 {region_id}: conflict_effects.{level}.{key} 必须为整数")
        thresholds = rinfo.get("danger_thresholds", {}) or {}
        if not isinstance(thresholds, dict): errors.append(f"区域 {region_id}: danger_thresholds 必须为对象")
        events_conflict = rinfo.get("conflict_events", []) or []
        if not isinstance(events_conflict, list): errors.append(f"区域 {region_id}: conflict_events 必须为数组")
        else:
            for idx, event in enumerate(events_conflict, 1):
                if not isinstance(event, dict): errors.append(f"区域 {region_id}: conflict_events[{idx}] 必须为对象"); continue
                if event.get("requires_level") not in ("calm", "tension", "confrontation", "conflict", "escalation", "war"):
                    errors.append(f"区域 {region_id}: conflict_events[{idx}] requires_level 非法")
                if not isinstance(event.get("text", ""), str): errors.append(f"区域 {region_id}: conflict_events[{idx}] text 必须为字符串")
        events = rinfo.get("exploration_events", []) or []
        if not isinstance(events, list):
            errors.append(f"区域 {region_id}: exploration_events 必须为数组")
        else:
            for idx, event in enumerate(events, 1):
                if isinstance(event, dict) and "requires" in event and not isinstance(event.get("requires"), dict):
                    errors.append(f"区域 {region_id}: exploration_events[{idx}] requires 必须为对象")
                if isinstance(event, dict) and "effects" in event and not isinstance(event.get("effects"), dict):
                    errors.append(f"区域 {region_id}: exploration_events[{idx}] effects 必须为对象")

    for q,qinfo in quests.items():
        requires = qinfo.get("requires", {}) or {}
        if not isinstance(requires, dict):
            errors.append(f"任务 {q}: requires 必须是对象")
        else:
            level_rule = requires.get("level")
            if level_rule is not None and not isinstance(level_rule, (int, float, dict)):
                errors.append(f"任务 {q}: requires.level 必须是数字或比较对象")
            gold_rule = requires.get("gold")
            if gold_rule is not None and not isinstance(gold_rule, (int, float, dict)):
                errors.append(f"任务 {q}: requires.gold 必须是数字或比较对象")
            relations_rule = requires.get("relations", {})
            if not isinstance(relations_rule, dict):
                errors.append(f"任务 {q}: requires.relations 必须是对象")
            else:
                for npc_name, rule in relations_rule.items():
                    if npc_name not in npcs: errors.append(f"任务 {q}: requires.relations NPC 不存在 {npc_name}")
                    if not isinstance(rule, (int, float, dict)):
                        errors.append(f"任务 {q}: requires.relations.{npc_name} 必须为数字或比较对象")
            memory_rule = requires.get("npc_memory", {}) or {}
            if not isinstance(memory_rule, dict):
                errors.append(f"任务 {q}: requires.npc_memory 必须为对象")
            else:
                for npc_name, memories in memory_rule.items():
                    if npc_name not in npcs:
                        errors.append(f"任务 {q}: requires.npc_memory NPC 不存在 {npc_name}")
                        continue
                    if not isinstance(memories, dict):
                        errors.append(f"任务 {q}: requires.npc_memory.{npc_name} 必须为对象")
                    else:
                        for memory_id, rule in memories.items():
                            if not isinstance(memory_id, str) or not memory_id:
                                errors.append(f"任务 {q}: requires.npc_memory 存在非法记忆ID")
                            if rule not in (True, None) and not isinstance(rule, dict):
                                errors.append(f"任务 {q}: requires.npc_memory.{npc_name}.{memory_id} 必须为对象/true/null")
                            elif isinstance(rule, dict):
                                if "min_strength" in rule:
                                    try:
                                        if not 0 <= int(rule["min_strength"]) <= 100:
                                            errors.append(f"任务 {q}: npc_memory.{npc_name}.{memory_id}.min_strength 非法")
                                    except (TypeError, ValueError):
                                        errors.append(f"任务 {q}: npc_memory.{npc_name}.{memory_id}.min_strength 非法")
                                if "sentiment" in rule and not isinstance(rule["sentiment"], str):
                                    errors.append(f"任务 {q}: npc_memory.{npc_name}.{memory_id}.sentiment 必须为字符串")
            attitude_rule = requires.get("npc_memory_attitude", {}) or {}
            if not isinstance(attitude_rule, dict):
                errors.append(f"任务 {q}: requires.npc_memory_attitude 必须为对象")
            else:
                for npc_name, attitude in attitude_rule.items():
                    if npc_name not in npcs:
                        errors.append(f"任务 {q}: requires.npc_memory_attitude NPC 不存在 {npc_name}")
                    elif attitude not in {"friendly", "favorable", "neutral", "wary", "hostile"}:
                        errors.append(f"任务 {q}: requires.npc_memory_attitude.{npc_name} 非法")
            info_rule = requires.get("npc_information", {}) or {}
            if not isinstance(info_rule, dict):
                errors.append(f"任务 {q}: requires.npc_information 必须是对象")
            else:
                for topic, rule in info_rule.items():
                    if not isinstance(topic, str) or not topic:
                        errors.append(f"任务 {q}: requires.npc_information 主题非法")
                    if rule not in (True, None) and not isinstance(rule, dict):
                        errors.append(f"任务 {q}: requires.npc_information.{topic} 必须为对象/true/null")
                    elif isinstance(rule, dict) and "min_confidence" in rule:
                        value = rule.get("min_confidence")
                        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
                            errors.append(f"任务 {q}: requires.npc_information.{topic}.min_confidence 非法")
            skills_rule = requires.get("skills", {})
            if not isinstance(skills_rule, dict):
                errors.append(f"任务 {q}: requires.skills 必须是对象")
            else:
                all_skills = {str(skill.get("name")): sect for sect, rows in skills.items() for skill in (rows or []) if isinstance(skill, dict)}
                for skill_name, rule in skills_rule.items():
                    if skill_name not in all_skills:
                        errors.append(f"任务 {q}: requires.skills 引用不存在武学 {skill_name}")
                    if not isinstance(rule, (int, float, dict)):
                        errors.append(f"任务 {q}: requires.skills.{skill_name} 必须为数字或对象")
            
            items_rule = requires.get("items", {})
            if not isinstance(items_rule, dict):
                errors.append(f"任务 {q}: requires.items 必须是对象")
            else:
                for item_name, count in items_rule.items():
                    if item_name not in items:
                        errors.append(f"任务 {q}: requires.items 中不存在物品 {item_name}")
                    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                        errors.append(f"任务 {q}: requires.items.{item_name} 必须为非负整数")
        stages = qinfo.get("stages", []) or []
        if not isinstance(stages, list):
            errors.append(f"任务 {q}: stages 必须是数组")
        else:
            for idx, stage in enumerate(stages, 1):
                if not isinstance(stage, dict):
                    errors.append(f"任务 {q}: stages[{idx}] 必须是对象")
                    continue
                if stage.get("target_type") not in (None, "kill", "talk", "collect"):
                    errors.append(f"任务 {q}: stages[{idx}] target_type 暂不支持该类型")
                req = stage.get("required_cnt", 1)
                if not isinstance(req, int) or isinstance(req, bool) or req < 1:
                    errors.append(f"任务 {q}: stages[{idx}] required_cnt 必须为正整数")
                branches = stage.get("branch_choices", []) or []
                if not isinstance(branches, list):
                    errors.append(f"任务 {q}: stages[{idx}] branch_choices 必须是数组")
                else:
                    branch_ids = set()
                    for bidx, branch in enumerate(branches, 1):
                        if not isinstance(branch, dict):
                            errors.append(f"任务 {q}: stages[{idx}].branch_choices[{bidx}] 必须是对象"); continue
                        bid = str(branch.get("id", "")).strip()
                        if not bid or bid in branch_ids:
                            errors.append(f"任务 {q}: stages[{idx}].branch_choices[{bidx}] id 缺失或重复")
                        branch_ids.add(bid)
                        try:
                            target_stage = int(branch.get("next_stage"))
                            if target_stage < 0 or target_stage >= len(stages):
                                errors.append(f"任务 {q}: stages[{idx}].branch_choices[{bidx}] next_stage 超出范围")
                        except (TypeError, ValueError):
                            errors.append(f"任务 {q}: stages[{idx}].branch_choices[{bidx}] next_stage 必须为整数")
                        if "requires" in branch and not isinstance(branch.get("requires"), dict):
                            errors.append(f"任务 {q}: stages[{idx}].branch_choices[{bidx}] requires 必须为对象")
                        if "effects" in branch and not isinstance(branch.get("effects"), dict):
                            errors.append(f"任务 {q}: stages[{idx}].branch_choices[{bidx}] effects 必须为对象")
        interventions = qinfo.get("npc_interventions", []) or []
        if not isinstance(interventions, list):
            errors.append(f"任务 {q}: npc_interventions 必须是数组")
        else:
            ids = set()
            for idx, item in enumerate(interventions, 1):
                if not isinstance(item, dict):
                    errors.append(f"任务 {q}: npc_interventions[{idx}] 必须是对象")
                    continue
                iid = str(item.get("id", "")).strip()
                if not iid or iid in ids:
                    errors.append(f"任务 {q}: npc_interventions[{idx}] id 缺失或重复")
                ids.add(iid)
                npc_name = item.get("npc")
                if npc_name is not None and npc_name not in npcs:
                    errors.append(f"任务 {q}: npc_interventions[{idx}] 引用不存在 NPC {npc_name}")
                action = item.get("action", "world_intervention")
                if action not in ("advance_stage", "reroute", "fail_quest", "complete_stage", "world_intervention"):
                    errors.append(f"任务 {q}: npc_interventions[{idx}].action 非法")
                for field in ("delay", "cooldown", "next_stage", "min_relation"):
                    if field in item and (not isinstance(item[field], int) or isinstance(item[field], bool)):
                        errors.append(f"任务 {q}: npc_interventions[{idx}].{field} 必须为整数")
                if "requires" in item and not isinstance(item.get("requires"), dict):
                    errors.append(f"任务 {q}: npc_interventions[{idx}].requires 必须为对象")
                if "effects" in item and not isinstance(item.get("effects"), dict):
                    errors.append(f"任务 {q}: npc_interventions[{idx}].effects 必须为对象")
                if action in ("advance_stage", "reroute") and "next_stage" in item:
                    try:
                        target_stage = int(item["next_stage"])
                        if target_stage < 0 or target_stage >= len(stages):
                            errors.append(f"任务 {q}: npc_interventions[{idx}].next_stage 超出范围")
                    except (TypeError, ValueError):
                        errors.append(f"任务 {q}: npc_interventions[{idx}].next_stage 必须为整数")
        competitions = qinfo.get("npc_competitions", []) or []
        if not isinstance(competitions, list):
            errors.append(f"任务 {q}: npc_competitions 必须是数组")
        else:
            comp_ids=set()
            for idx,item in enumerate(competitions,1):
                if not isinstance(item,dict):
                    errors.append(f"任务 {q}: npc_competitions[{idx}] 必须是对象"); continue
                cid=str(item.get("id","")).strip()
                if not cid or cid in comp_ids: errors.append(f"任务 {q}: npc_competitions[{idx}] id 缺失或重复")
                comp_ids.add(cid)
                for field in ("stage","delay","cooldown","min_relation"):
                    if field in item and (not isinstance(item[field],int) or isinstance(item[field],bool)):
                        errors.append(f"任务 {q}: npc_competitions[{idx}].{field} 必须为整数")
                if "requires" in item and not isinstance(item.get("requires"),dict): errors.append(f"任务 {q}: npc_competitions[{idx}].requires 必须为对象")
                contestants=item.get("contestants",[])
                if not isinstance(contestants,list) or len(contestants)<2:
                    errors.append(f"任务 {q}: npc_competitions[{idx}].contestants 至少需要两个竞争者")
                else:
                    for cidx,c in enumerate(contestants,1):
                        if not isinstance(c,dict): errors.append(f"任务 {q}: npc_competitions[{idx}].contestants[{cidx}] 必须为对象"); continue
                        if c.get("npc") not in npcs: errors.append(f"任务 {q}: npc_competitions[{idx}].contestants[{cidx}] 引用不存在 NPC {c.get('npc')}")
                        for field in ("next_stage","min_relation"):
                            if field in c and (not isinstance(c[field],int) or isinstance(c[field],bool)): errors.append(f"任务 {q}: npc_competitions[{idx}].contestants[{cidx}].{field} 必须为整数")
                        if "requires" in c and not isinstance(c.get("requires"),dict): errors.append(f"任务 {q}: npc_competitions[{idx}].contestants[{cidx}].requires 必须为对象")
                        if "effects" in c and not isinstance(c.get("effects"),dict): errors.append(f"任务 {q}: npc_competitions[{idx}].contestants[{cidx}].effects 必须为对象")
                        if c.get("action") in ("advance_stage","reroute") and "next_stage" in c:
                            try:
                                if int(c["next_stage"])<0 or int(c["next_stage"])>=len(stages): errors.append(f"任务 {q}: npc_competitions[{idx}].contestants[{cidx}].next_stage 超出范围")
                            except Exception: pass
        for field in ("time_limit",):
            if field in qinfo and (not isinstance(qinfo[field], int) or isinstance(qinfo[field], bool) or qinfo[field] < 1):
                errors.append(f"任务 {q}: {field} 必须为正整数")
        for field in ("repeatable", "retryable"):
            if field in qinfo and not isinstance(qinfo[field], bool):
                errors.append(f"任务 {q}: {field} 必须为布尔值")
        if qinfo.get("repeatable") is True:
            repeat_reward = qinfo.get("repeat_reward")
            if not isinstance(repeat_reward, dict) or not repeat_reward:
                errors.append(f"任务 {q}: 可重复任务必须定义非空的 repeat_reward")
            else:
                for field in ("sect_reputation", "honor_delta", "infamy_delta", "jianghu_action", "jianghu_amount"):
                    if field in repeat_reward:
                        errors.append(f"任务 {q}: repeat_reward 不得包含永久成长字段 {field}")
                repeat_effects = repeat_reward.get("effects") or {}
                if isinstance(repeat_effects, dict):
                    for field in ("increment_variables", "relations", "faction_relations", "region_effects"):
                        if repeat_effects.get(field):
                            errors.append(f"任务 {q}: repeat_reward.effects 不得包含可累积字段 {field}")
                repeat_entries = []
                if repeat_reward.get("item"):
                    repeat_entries.append({"item": repeat_reward.get("item"), "quantity": repeat_reward.get("item_quantity", 1)})
                repeat_entries.extend(repeat_reward.get("items", []) or [])
                for idx, entry in enumerate(repeat_entries, 1):
                    if isinstance(entry, str):
                        item_name, qty = entry, 1
                    elif isinstance(entry, dict):
                        item_name = entry.get("item") or entry.get("name")
                        qty = entry.get("quantity", 1)
                    else:
                        errors.append(f"任务 {q}: repeat_reward items[{idx}] 格式非法")
                        continue
                    if item_name and item_name not in items:
                        errors.append(f"任务 {q}: repeat_reward 奖励物品不存在 {item_name}")
                    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
                        errors.append(f"任务 {q}: repeat_reward items[{idx}] quantity 必须为正整数")
                for field in ("exp", "gold"):
                    if field in repeat_reward:
                        value = repeat_reward[field]
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                            errors.append(f"任务 {q}: repeat_reward.{field} 必须为非负数值")
            cooldown = qinfo.get("repeat_cooldown_ticks")
            if not isinstance(cooldown, int) or isinstance(cooldown, bool) or cooldown < 1:
                errors.append(f"任务 {q}: 可重复任务必须设置正整数 repeat_cooldown_ticks")
            if qinfo.get("choices"):
                errors.append(f"任务 {q}: 可重复任务不支持 choices（选择奖励会绕过 repeat_reward）")
            for effect_field in ("on_accept", "on_complete"):
                effects = qinfo.get(effect_field) or {}
                if not isinstance(effects, dict):
                    continue
                for field in ("increment_variables", "relations", "faction_relations", "region_effects"):
                    if effects.get(field):
                        errors.append(f"任务 {q}: 可重复任务的 {effect_field} 不得包含可累积字段 {field}")
        for effect_field in ("on_accept", "on_complete", "on_fail", "on_abandon"):
            if effect_field not in qinfo:
                continue
            field_effects = qinfo.get(effect_field)
            if not isinstance(field_effects, dict):
                errors.append(f"任务 {q}: {effect_field} 必须为对象")
                continue
            check_region_effects(field_effects, f"任务 {q}: {effect_field}", zone_names, errors)
        choices = qinfo.get("choices", []) or []
        if not isinstance(choices, list):
            errors.append(f"任务 {q}: choices 必须是数组")
        else:
            ids = set()
            for idx, choice in enumerate(choices, 1):
                if not isinstance(choice, dict):
                    errors.append(f"任务 {q}: choices[{idx}] 必须是对象")
                    continue
                cid = str(choice.get("id", "")).strip()
                if not cid or cid in ids:
                    errors.append(f"任务 {q}: choices[{idx}] id 缺失或重复")
                ids.add(cid)
                if "requires" in choice and not isinstance(choice.get("requires"), dict):
                    errors.append(f"任务 {q}: choices[{idx}] requires 必须为对象")
                if "effects" in choice and not isinstance(choice.get("effects"), dict):
                    errors.append(f"任务 {q}: choices[{idx}] effects 必须为对象")
                elif isinstance(choice.get("effects"), dict):
                    check_region_effects(choice.get("effects"), f"任务 {q}: choices[{idx}]", zone_names, errors)
                if "reward" in choice and not isinstance(choice.get("reward"), dict):
                    errors.append(f"任务 {q}: choices[{idx}] reward 必须为对象")
        target=qinfo.get("target_name")
        if target and qinfo.get("target_type")=="kill" and target not in enemies:
            errors.append(f"任务 {q}: kill目标 {target} 不存在")
        if target and qinfo.get("target_type")=="talk" and target not in npcs:
            errors.append(f"任务 {q}: talk目标 {target} 不存在")
        giver=qinfo.get("npc")
        if giver and giver not in npcs: errors.append(f"任务 {q}: 发布NPC {giver} 不存在")
        turn=qinfo.get("turn_in_npc")
        if turn and turn not in npcs: errors.append(f"任务 {q}: 交付NPC {turn} 不存在")
        reward=qinfo.get("reward",{})
        if not isinstance(reward, dict):
            errors.append(f"任务 {q}: reward 必须是对象")
        else:
            reward_entries=[]
            if reward.get("item"):
                reward_entries.append({"item": reward.get("item"), "quantity": reward.get("item_quantity", 1)})
            reward_entries.extend(reward.get("items", []) or [])
            for idx, entry in enumerate(reward_entries, 1):
                if isinstance(entry, str):
                    item_name, qty = entry, 1
                elif isinstance(entry, dict):
                    item_name = entry.get("item") or entry.get("name")
                    qty = entry.get("quantity", 1)
                else:
                    errors.append(f"任务 {q}: reward items[{idx}] 格式非法")
                    continue
                if item_name and item_name not in items:
                    errors.append(f"任务 {q}: 奖励物品不存在 {item_name}")
                if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
                    errors.append(f"任务 {q}: reward items[{idx}] quantity 必须为正整数")
            for field in ("exp", "gold"):
                if field in reward:
                    value = reward[field]
                    values = [value] if not isinstance(value, dict) else [value.get("amount", value.get("min", 0)), value.get("max", value.get("amount", value.get("min", 0)))]
                    try:
                        nums = [int(v) for v in values]
                        if any(v < 0 for v in nums) or len(nums) == 2 and nums[0] > nums[1]:
                            errors.append(f"任务 {q}: {field} 奖励数值非法")
                    except (TypeError, ValueError):
                        errors.append(f"任务 {q}: {field} 奖励数值非法")
    if not isinstance(world_regions, dict):
        errors.append("world_regions.json 根节点必须为对象")
    else:
        for zone, info in world_regions.items():
            if not isinstance(info, dict): errors.append(f"区域 {zone}: 必须为对象"); continue
            if not isinstance(info.get("recommended_level", 1), int) or info.get("recommended_level", 1) < 1:
                errors.append(f"区域 {zone}: recommended_level 必须为正整数")
            if info.get("danger", "normal") not in ("safe","normal","dangerous","high","extreme"):
                errors.append(f"区域 {zone}: danger 非法")

    if not isinstance(world_events, dict):
        errors.append("world_events.json 根节点必须为对象")
    else:
        for event_id, info in world_events.items():
            if not isinstance(info, dict):
                errors.append(f"世界事件 {event_id}: 必须为对象"); continue
            for key in ("title", "region", "text"):
                if key in info and not isinstance(info.get(key), str): errors.append(f"世界事件 {event_id}: {key} 必须为字符串")
            if info.get("region") not in world_regions: errors.append(f"世界事件 {event_id}: region 不存在 {info.get('region')}")
            if "requires" in info and not isinstance(info.get("requires"), dict): errors.append(f"世界事件 {event_id}: requires 必须为对象")
            if "effects" in info and not isinstance(info.get("effects"), dict): errors.append(f"世界事件 {event_id}: effects 必须为对象")
            npc_info_effects=(info.get("effects", {}) or {}).get("npc_information", [])
            if not isinstance(npc_info_effects, list): errors.append(f"世界事件 {event_id}: effects.npc_information 必须为数组")
            else:
                for idx,entry in enumerate(npc_info_effects,1):
                    if not isinstance(entry, dict): errors.append(f"世界事件 {event_id}: npc_information[{idx}] 必须为对象"); continue
                    if entry.get("npc") not in npcs: errors.append(f"世界事件 {event_id}: npc_information[{idx}] NPC 不存在 {entry.get('npc')}")
                    if not isinstance(entry.get("topic"), str) or not entry.get("topic"): errors.append(f"世界事件 {event_id}: npc_information[{idx}] topic 非法")
                    if not isinstance(entry.get("text"), str) or not entry.get("text"): errors.append(f"世界事件 {event_id}: npc_information[{idx}] text 非法")
                    if not isinstance(entry.get("confidence",70), int) or isinstance(entry.get("confidence",70), bool) or not 0 <= int(entry.get("confidence",70)) <= 100: errors.append(f"世界事件 {event_id}: npc_information[{idx}] confidence 非法")
                    if not isinstance(entry.get("ttl",0), int) or isinstance(entry.get("ttl",0), bool) or int(entry.get("ttl",0)) < 0: errors.append(f"世界事件 {event_id}: npc_information[{idx}] ttl 非法")
            if "rewards" in info and not isinstance(info.get("rewards"), dict): errors.append(f"世界事件 {event_id}: rewards 必须为对象")
            if "once" in info and not isinstance(info.get("once"), bool): errors.append(f"世界事件 {event_id}: once 必须为布尔值")
            if "cooldown" in info and (not isinstance(info.get("cooldown"), int) or info.get("cooldown") < 0): errors.append(f"世界事件 {event_id}: cooldown 必须为非负整数")
            for nxt in info.get("unlock_events", []) or []:
                if nxt not in world_events: errors.append(f"世界事件 {event_id}: unlock_events 引用不存在 {nxt}")
            rewards=info.get("rewards", {}) or {}
            if not isinstance(rewards, dict):
                errors.append(f"世界事件 {event_id}: rewards 必须为对象")
            else:
                gold = rewards.get("gold", 0)
                if not isinstance(gold, int) or isinstance(gold, bool) or gold < 0:
                    errors.append(f"世界事件 {event_id}: rewards.gold 必须为非负整数")
                if "item" in rewards and rewards.get("item"):
                    if not isinstance(rewards.get("item"), str) or rewards.get("item") not in items:
                        errors.append(f"世界事件 {event_id}: rewards.item 引用不存在物品 {rewards.get('item')}")
                    quantity = rewards.get("item_quantity", 1)
                    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
                        errors.append(f"世界事件 {event_id}: rewards.item_quantity 必须为正整数")
                if not isinstance(rewards.get("sect_reputation", {}), dict):
                    errors.append(f"世界事件 {event_id}: sect_reputation 必须为对象")
                else:
                    for sect_name, delta in rewards.get("sect_reputation", {}).items():
                        if sect_name not in sects:
                            errors.append(f"世界事件 {event_id}: sect_reputation 引用不存在门派 {sect_name}")
                        if not isinstance(delta, int) or isinstance(delta, bool):
                            errors.append(f"世界事件 {event_id}: sect_reputation.{sect_name} 必须为整数")
                if not isinstance(rewards.get("relations", {}), dict):
                    errors.append(f"世界事件 {event_id}: relations 必须为对象")
                else:
                    for npc_name, delta in rewards.get("relations", {}).items():
                        if npc_name not in npcs:
                            errors.append(f"世界事件 {event_id}: relations 引用不存在 NPC {npc_name}")
                        if not isinstance(delta, int) or isinstance(delta, bool):
                            errors.append(f"世界事件 {event_id}: relations.{npc_name} 必须为整数")
    # P3.2 跨文件经济链校验：配置存在不等于资源、职业、配方和商队真正连通。
    valid_resource_actions = {"mine", "chop", "gather"}
    if not isinstance(resources, dict):
        errors.append("economy/resources.json 根节点必须为对象")
        resources = {}
    for room_id, cfg in resources.items():
        if not isinstance(cfg, dict):
            errors.append(f"资源点 {room_id}: 配置必须为对象"); continue
        if room_id not in rooms:
            errors.append(f"资源点 {room_id}: 房间不存在")
        item_name = cfg.get("item")
        if item_name not in items:
            errors.append(f"资源点 {room_id}: 物品不存在 {item_name}")
        action = cfg.get("action", "mine")
        if action not in valid_resource_actions:
            errors.append(f"资源点 {room_id}: action 非法 {action}")
        for field in ("capacity", "yield_max", "regen_interval", "regen_amount"):
            value = cfg.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < (0 if field == "regen_amount" else 1):
                errors.append(f"资源点 {room_id}: {field} 数值非法")
    if not isinstance(gatherers, dict):
        errors.append("economy/gatherers.json 根节点必须为对象"); gatherers = {}
    for npc_name, cfg in gatherers.items():
        if not isinstance(cfg, dict):
            errors.append(f"采集职业 {npc_name}: 配置必须为对象"); continue
        if npc_name not in npcs:
            errors.append(f"采集职业引用不存在 NPC {npc_name}")
        if cfg.get("room_id") not in rooms:
            errors.append(f"采集职业 {npc_name}: 工作房间不存在 {cfg.get('room_id')}")
        resource_room = cfg.get("resource_room_id")
        resource_cfg = resources.get(resource_room) if isinstance(resources, dict) else None
        if not isinstance(resource_cfg, dict):
            errors.append(f"采集职业 {npc_name}: 资源点不存在 {resource_room}"); continue
        if cfg.get("item") != resource_cfg.get("item"):
            errors.append(f"采集职业 {npc_name}: 产出物品与资源点 {resource_room} 不一致")
        expected_action = cfg.get("action") or {"木材": "chop", "铁矿石": "mine"}.get(cfg.get("item"), "gather")
        actual_action = resource_cfg.get("action", "mine")
        if expected_action != actual_action:
            errors.append(f"采集职业 {npc_name}: 操作 {expected_action} 与资源点 {resource_room} 的操作 {actual_action} 不一致")
        for field in ("interval", "amount", "capacity"):
            value = cfg.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(f"采集职业 {npc_name}: {field} 必须为正整数")
    if not isinstance(recipes, dict):
        errors.append("economy/recipes.json 根节点必须为对象"); recipes = {}
    for npc_name, cfg in recipes.items():
        if not isinstance(cfg, dict):
            errors.append(f"生产配方 {npc_name}: 配置必须为对象"); continue
        if npc_name not in npcs:
            errors.append(f"生产配方引用不存在 NPC {npc_name}")
        room_id = cfg.get("room_id")
        if room_id and room_id not in rooms:
            errors.append(f"生产配方 {npc_name}: 工作房间不存在 {room_id}")
        for field in ("inputs", "outputs", "output_capacity"):
            mapping = cfg.get(field, {})
            if not isinstance(mapping, dict):
                errors.append(f"生产配方 {npc_name}: {field} 必须为对象"); continue
            for item_name, amount in mapping.items():
                if item_name not in items:
                    errors.append(f"生产配方 {npc_name}: {field} 物品不存在 {item_name}")
                if not isinstance(amount, int) or isinstance(amount, bool) or amount < (0 if field == "output_capacity" else 1):
                    errors.append(f"生产配方 {npc_name}: {field}.{item_name} 数量非法")
        routes = cfg.get("supplier_routes", []) or []
        if not isinstance(routes, list):
            errors.append(f"生产配方 {npc_name}: supplier_routes 必须为数组"); continue
        for idx, route in enumerate(routes, 1):
            if not isinstance(route, dict):
                errors.append(f"生产配方 {npc_name}: supplier_routes[{idx}] 必须为对象"); continue
            item_name = route.get("item")
            if item_name not in items:
                errors.append(f"生产配方 {npc_name}: 采购物品不存在 {item_name}")
            suppliers = route.get("suppliers", [])
            if not isinstance(suppliers, list) or not suppliers:
                errors.append(f"生产配方 {npc_name}: supplier_routes[{idx}].suppliers 必须为非空数组")
            else:
                for supplier in suppliers:
                    if supplier not in npcs:
                        errors.append(f"生产配方 {npc_name}: 供应 NPC 不存在 {supplier}")
            for field in ("unit_price", "max_per_tick", "max_stock"):
                if field in route and (not isinstance(route[field], int) or isinstance(route[field], bool) or route[field] < (0 if field == "unit_price" else 1)):
                    errors.append(f"生产配方 {npc_name}: supplier_routes[{idx}].{field} 数值非法")
    if not isinstance(caravans, dict):
        errors.append("economy/caravans.json 根节点必须为对象"); caravans = {}
    for caravan_name, cfg in caravans.items():
        if not isinstance(cfg, dict):
            errors.append(f"商队 {caravan_name}: 配置必须为对象"); continue
        route = cfg.get("route", [])
        if not isinstance(route, list) or not route:
            errors.append(f"商队 {caravan_name}: route 必须为非空数组")
        else:
            for room_id in route:
                if room_id not in rooms:
                    errors.append(f"商队 {caravan_name}: 路线房间不存在 {room_id}")
        for appearance in cfg.get("appearances", []) or []:
            if not isinstance(appearance, dict):
                errors.append(f"商队 {caravan_name}: appearances 条目必须为对象"); continue
            if appearance.get("room") not in rooms:
                errors.append(f"商队 {caravan_name}: 到场房间不存在 {appearance.get('room')}")
            if not isinstance(appearance.get("interval"), int) or isinstance(appearance.get("interval"), bool) or appearance.get("interval", 0) < 1:
                errors.append(f"商队 {caravan_name}: 到场 interval 必须为正整数")
        for field in ("sale_prices", "buy_prices", "inventory"):
            mapping = cfg.get(field, {}) or {}
            if not isinstance(mapping, dict):
                errors.append(f"商队 {caravan_name}: {field} 必须为对象"); continue
            for item_name, value in mapping.items():
                if item_name not in items:
                    errors.append(f"商队 {caravan_name}: {field} 物品不存在 {item_name}")
                if field != "inventory" and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0):
                    errors.append(f"商队 {caravan_name}: {field}.{item_name} 价格非法")
        if not isinstance(cfg.get("capacity", 0), int) or isinstance(cfg.get("capacity", 0), bool) or cfg.get("capacity", 0) < 1:
            errors.append(f"商队 {caravan_name}: capacity 必须为正整数")

    # P3.2 经济闭环联动校验：供应者必须真实产出对应原料，
    # 制作成品必须有商队报价，且至少一支商队会经过对应作坊。
    if isinstance(gatherers, dict) and isinstance(recipes, dict) and isinstance(caravans, dict):
        supplier_outputs = {}
        for supplier_id, supplier_cfg in gatherers.items():
            if isinstance(supplier_cfg, dict):
                supplier_outputs.setdefault(supplier_id, set()).add(str(supplier_cfg.get("item", "")))
        for producer_id, producer_cfg in recipes.items():
            if isinstance(producer_cfg, dict) and isinstance(producer_cfg.get("outputs", {}), dict):
                supplier_outputs.setdefault(producer_id, set()).update(str(item) for item in producer_cfg.get("outputs", {}))
        for buyer_id, recipe_cfg in recipes.items():
            if not isinstance(recipe_cfg, dict):
                continue
            for route_index, supplier_route in enumerate(recipe_cfg.get("supplier_routes", []) or [], 1):
                if not isinstance(supplier_route, dict):
                    continue
                required_item = str(supplier_route.get("item", ""))
                for supplier_id in supplier_route.get("suppliers", []) or []:
                    if required_item not in supplier_outputs.get(supplier_id, set()):
                        errors.append(f"经济闭环 {buyer_id}: 供应者 {supplier_id} 未配置产出 {required_item}（采购路线 {route_index}）")
        caravan_routes = [cfg.get("route", []) for cfg in caravans.values() if isinstance(cfg, dict)]
        caravan_trade_items = set()
        for caravan_cfg in caravans.values():
            if not isinstance(caravan_cfg, dict):
                continue
            for price_field in ("sale_prices", "buy_prices"):
                prices = caravan_cfg.get(price_field, {})
                if isinstance(prices, dict):
                    caravan_trade_items.update(str(item) for item in prices)
        for producer_id, recipe_cfg in recipes.items():
            if not isinstance(recipe_cfg, dict):
                continue
            outputs = recipe_cfg.get("outputs", {})
            if not isinstance(outputs, dict):
                continue
            room_id = str(recipe_cfg.get("room_id", "") or "")
            # 旧版铁匠使用 blacksmith 站点名，由商队路线兼容层处理。
            required_stop = room_id or ("blacksmith" if producer_id == "铁匠" else "")
            if required_stop and not any(required_stop in route for route in caravan_routes):
                errors.append(f"经济闭环 {producer_id}: 没有商队经过制作地点 {required_stop}")
            for output_item in outputs:
                if str(output_item) not in caravan_trade_items:
                    errors.append(f"经济闭环 {producer_id}: 成品 {output_item} 未配置任何商队交易报价")

    # P4.0 gameplay closure audit: validate runtime targets and effect names,
    # not only JSON shapes. These checks catch content that parses correctly
    # but cannot be completed or activated during play.
    enemy_names = set(enemies)
    for enemy_id, enemy_info in enemies.items():
        if isinstance(enemy_info, dict) and enemy_info.get("name"):
            enemy_names.add(str(enemy_info["name"]))
    npc_room_placements = {}
    for room_id, room_info in rooms.items():
        for npc_name in room_info.get("npcs", []) or []:
            npc_room_placements.setdefault(npc_name, set()).add(room_id)
    for quest_id, quest_info in quests.items():
        targets = [{
            "target_type": quest_info.get("target_type"),
            "target_name": quest_info.get("target_name"),
        }] + (quest_info.get("stages", []) or [])
        for stage_index, target_info in enumerate(targets):
            if not isinstance(target_info, dict):
                continue
            target_type = target_info.get("target_type")
            target_name = target_info.get("target_name")
            if not target_name:
                continue
            if target_type == "kill" and target_name not in enemy_names:
                errors.append(f"任务 {quest_id}: 第 {stage_index} 阶段击杀目标不存在 {target_name}")
            elif target_type == "talk" and target_name not in npcs:
                errors.append(f"任务 {quest_id}: 第 {stage_index} 阶段交谈目标不存在 {target_name}")
            elif target_type == "collect" and target_name not in items:
                errors.append(f"任务 {quest_id}: 第 {stage_index} 阶段收集物品不存在 {target_name}")
        for field in ("npc", "turn_in_npc"):
            npc_name = quest_info.get(field)
            if npc_name and npc_name in npcs and not npc_room_placements.get(npc_name) and not npcs[npc_name].get("room"):
                errors.append(f"任务 {quest_id}: {field} {npc_name} 没有可到达的场景位置")

    valid_statuses = {"poison", "bleed", "stun", "shield", "armor_break", "damage_reduction", "thorns"}
    valid_skill_effects = {"status", "self_status", "combo", "mp_restore"}
    for sect_name, skill_rows in skills.items():
        for skill_info in skill_rows or []:
            if not isinstance(skill_info, dict):
                continue
            effects = skill_info.get("effects")
            if not isinstance(effects, list):
                effects = [skill_info.get("effect", {})]
            for effect in effects:
                if not isinstance(effect, dict) or not effect:
                    continue
                effect_type = effect.get("type")
                if effect_type not in valid_skill_effects:
                    errors.append(f"武学 {sect_name}/{skill_info.get('name', '未命名')}: 不支持的效果类型 {effect_type}")
                if effect_type in {"status", "self_status"} and effect.get("status") not in valid_statuses:
                    errors.append(f"武学 {sect_name}/{skill_info.get('name', '未命名')}: 状态效果不存在 {effect.get('status')}")
    for item_name, item_info in items.items():
        if not isinstance(item_info, dict):
            continue
        weapon_effect = item_info.get("weapon_effect") or {}
        if isinstance(weapon_effect, dict) and weapon_effect.get("type") == "status" and weapon_effect.get("status") not in valid_statuses:
            errors.append(f"物品 {item_name}: 武器状态效果不存在 {weapon_effect.get('status')}")
        item_effect = item_info.get("effect") or {}
        if isinstance(item_effect, dict):
            for status_field in ("status", "target_status"):
                status_info = item_effect.get(status_field)
                if isinstance(status_info, dict) and status_info.get("name") not in valid_statuses:
                    errors.append(f"物品 {item_name}: {status_field} 状态不存在 {status_info.get('name')}")

    if errors:
        print("DATA VALIDATION: FAIL")
        for e in errors: print(" -",e)
        return 1
    print("DATA VALIDATION: PASS")
    print(f"rooms={len(rooms)} npcs={len(npcs)} items={len(items)} enemies={len(enemies)} skills={len(skills)} quests={len(quests)} regions={len(world_regions)} events={len(entry_events)}")
    print(f"zones={sorted(set(r.get('zone','main') for r in rooms.values()))}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
