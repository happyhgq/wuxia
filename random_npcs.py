# -*- coding: utf-8 -*-
"""Alpha202：低密度随机路人。只管理临时路人，不加入固定 NPC 名册。"""
import json
import os
import random
import engine

_CONFIG = None


def get_config():
    global _CONFIG
    if _CONFIG is None:
        path = os.path.join(engine.DATA_DIR, "random_npcs.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            _CONFIG = raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            _CONFIG = {}
    return _CONFIG


def reset_config_cache():
    global _CONFIG
    _CONFIG = None


def _variables(player):
    world = getattr(player, "world_state", None)
    if not isinstance(world, dict):
        return {}
    variables = world.setdefault("variables", {})
    if not isinstance(variables, dict):
        variables = {}
        world["variables"] = variables
    return variables


def _state(player):
    variables = _variables(player)
    state = variables.get("random_pedestrians")
    if not isinstance(state, dict):
        state = {"by_room": {}, "last_check": {}, "region_population": {}, "region_population_clock": {}}
        variables["random_pedestrians"] = state
    state.setdefault("by_room", {})
    state.setdefault("last_check", {})
    state.setdefault("region_population", {})
    state.setdefault("region_population_clock", {})
    if not isinstance(state["by_room"], dict): state["by_room"] = {}
    if not isinstance(state["last_check"], dict): state["last_check"] = {}
    if not isinstance(state["region_population"], dict): state["region_population"] = {}
    if not isinstance(state["region_population_clock"], dict): state["region_population_clock"] = {}
    return state


def is_random_pedestrian(player, name):
    state = _state(player)
    for entries in state["by_room"].values():
        if isinstance(entries, list) and any(isinstance(row, dict) and row.get("name") == name for row in entries):
            return True
    return False


def get_room_pedestrians(player, room_id):
    rows = _state(player)["by_room"].get(str(room_id), [])
    if not isinstance(rows, list): return []
    return [str(row["name"]) for row in rows if isinstance(row, dict) and row.get("name")]


def _clock(player):
    try: return int(player.get_quest_clock())
    except (AttributeError, TypeError, ValueError, OverflowError): return 0


def _room_profile(config, room_id, room):
    if room.get("safe_zone") is True or room.get("map_hidden") is True:
        return None
    disabled_rooms = set(str(x) for x in config.get("disabled_rooms", []) if x)
    disabled_zones = set(str(x) for x in config.get("disabled_zones", []) if x)
    if room_id in disabled_rooms or str(room.get("zone", "main")) in disabled_zones:
        return None
    # 房间级配置优先，其次区域配置；没有配置时默认不刷新，避免无意污染特殊地图。
    rooms = config.get("rooms", {}) if isinstance(config.get("rooms"), dict) else {}
    zones = config.get("zones", {}) if isinstance(config.get("zones"), dict) else {}
    profile = rooms.get(room_id, zones.get(str(room.get("zone", "main"))))
    if not isinstance(profile, dict) or profile.get("enabled", True) is False:
        return None
    return profile


def refresh_current_room(player, room_id=None):
    """按当前场景刷新路人；区域人口用轻量计数表示，不在其他场景保存实体。"""
    room_id = str(room_id or getattr(player, "location", ""))
    room = engine.ROOMS.get(room_id)
    if not isinstance(room, dict): return []
    config = get_config()
    profile = _room_profile(config, room_id, room)
    state = _state(player)
    clock = _clock(player)
    zone = str(room.get("zone", "main"))

    # 只保留当前区域的轻量人口计数；跨区域后不后台模拟旧区域。
    for old_zone in list(state["region_population"]):
        if old_zone != zone:
            state["region_population"].pop(old_zone, None)
            state["region_population_clock"].pop(old_zone, None)

    # 离开场景时回收临时实体，但把人数转成区域级抽象人口计数，避免场景切换绕过区域上限。
    for old_room in list(state["by_room"]):
        if old_room == room_id:
            continue
        old_rows = state["by_room"].get(old_room, [])
        old_room_data = engine.ROOMS.get(old_room, {}) or {}
        old_zone = str(old_room_data.get("zone", "main"))
        if old_zone == zone and isinstance(old_rows, list):
            count = sum(1 for row in old_rows if isinstance(row, dict) and row.get("name"))
            if count:
                state["region_population"][zone] = max(0, int(state["region_population"].get(zone, 0) or 0)) + count
                state["region_population_clock"][zone] = clock
        state["by_room"].pop(old_room, None)

    existing = get_room_pedestrians(player, room_id)
    if profile is None:
        state["by_room"].pop(room_id, None)
        return []

    interval = max(1, int(config.get("refresh_interval_ticks", 4)))
    # 区域抽象人口随游戏时间缓慢散去；不生成其他场景的 NPC 实体。
    last_decay = state["region_population_clock"].get(zone, clock)
    try: last_decay = int(last_decay)
    except (TypeError, ValueError, OverflowError): last_decay = clock
    elapsed_intervals = max(0, clock - last_decay) // max(interval * 3, 1)
    if elapsed_intervals:
        population = max(0, int(state["region_population"].get(zone, 0) or 0) - elapsed_intervals)
        state["region_population"][zone] = population
        state["region_population_clock"][zone] = last_decay + elapsed_intervals * interval * 3

    last = state["last_check"].get(room_id)
    try: last = int(last)
    except (TypeError, ValueError, OverflowError): last = -10**9
    if clock - last < interval:
        return existing
    state["last_check"][room_id] = clock
    rows = state["by_room"].setdefault(room_id, [])
    max_scene = max(0, int(profile.get("scene_cap", 0)))
    max_region = max(0, int(profile.get("region_cap", max_scene)))
    current_count = sum(1 for row in rows if isinstance(row, dict) and row.get("name"))
    region_count = max(0, int(state["region_population"].get(zone, 0) or 0)) + current_count
    if current_count >= max_scene or region_count >= max_region:
        return get_room_pedestrians(player, room_id)

    # 治安只影响普通路人的出现倾向与身份构成，不把随机路人变成敌人或官府任务人物。
    security = 70
    try:
        ecology = player.get_region_ecology(zone)
        if isinstance(ecology, dict):
            security = max(0, min(100, int(ecology.get("security", 70))))
    except (AttributeError, TypeError, ValueError, OverflowError):
        pass
    security_rules = config.get("security_profiles", {})
    if not isinstance(security_rules, dict): security_rules = {}
    if security >= 76:
        band = security_rules.get("good", {})
    elif security >= 51:
        band = security_rules.get("ordinary", {})
    elif security >= 31:
        band = security_rules.get("tense", {})
    else:
        band = security_rules.get("unsafe", {})
    if not isinstance(band, dict): band = {}
    try:
        chance = float(profile.get("spawn_chance", 0.25)) * float(band.get("chance_multiplier", 1.0))
    except (TypeError, ValueError, OverflowError):
        chance = 0.25
    chance = max(0.0, min(0.45, chance))
    if random.random() >= chance: return get_room_pedestrians(player, room_id)
    pools = config.get("name_pools", {})
    roles = list(profile.get("roles") or ["行脚客", "当地百姓", "赶路人"])
    extra_roles = band.get("extra_roles", [])
    if isinstance(extra_roles, list):
        roles.extend(str(role) for role in extra_roles if role and str(role) not in roles)
    surnames = pools.get("surnames", ["沈", "陆", "周", "顾", "林", "许"])
    given_names = pools.get("given_names", ["小川", "阿成", "青禾", "远山", "明远", "阿宁"])
    existing_names = {str(row.get("name")) for room_rows in state["by_room"].values() if isinstance(room_rows, list) for row in room_rows if isinstance(row, dict)}
    for _ in range(12):
        name = random.choice(surnames) + random.choice(given_names)
        if name not in engine.NPCS and name not in existing_names:
            break
    else:
        return get_room_pedestrians(player, room_id)
    role = str(random.choice(roles)) if roles else "路人"
    rows.append({"name": name, "role": role, "room": room_id, "created_clock": clock})
    return get_room_pedestrians(player, room_id)


def talk_text(player, name):
    """返回随机路人的轻量闲谈；不进入任务、关系和固定 NPC 记忆系统。"""
    state = _state(player)
    for room_id, rows in state["by_room"].items():
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("name") == name:
                role = str(row.get("role", "路人"))
                zone = str((engine.ROOMS.get(room_id, {}) or {}).get("zone", "main"))
                lines = get_config().get("rumors", {}).get(zone) or get_config().get("default_rumors") or ["最近江湖上没什么新鲜事，还是赶路要紧。"]
                return f"{name}（{role}）随口说道：{random.choice(lines)}"
    return None
