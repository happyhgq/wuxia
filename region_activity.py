# -*- coding: utf-8 -*-
"""Alpha84：地区治安、敌人活动池与官府巡逻联动。动态状态写入 V12 variables。"""
import copy
import json
import os
import engine

_CONFIG_CACHE = None


def get_config():
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        path = os.path.join(engine.DATA_DIR, "region_activity.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _CONFIG_CACHE = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            _CONFIG_CACHE = {}
    return _CONFIG_CACHE


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
    state = variables.setdefault("region_activity", {})
    if not isinstance(state, dict):
        state = {}
        variables["region_activity"] = state
    return state


def get_permanent_region_delta(player, zone):
    """只看已写入存档的持久治安变化，不包含仍在生效的外部危机扣分。"""
    row = _state(player).get(zone, {})
    result = {}
    for key in ("security", "commerce", "travel"):
        try:
            value = int(row.get(key, 0)) if isinstance(row, dict) else 0
        except (TypeError, ValueError, OverflowError):
            value = 0
        result[key] = max(-60, min(30, value))
    return result


def get_region_delta(player, zone):
    result = get_permanent_region_delta(player, zone)
    # Alpha87：外部世界危机在有效期内持续影响指定地区，不直接改写永久治安基值。
    variables = _variables(player)
    crises = variables.get("world_crises", {})
    if isinstance(crises, dict):
        try:
            clock = int(player.get_quest_clock())
        except (AttributeError, TypeError, ValueError, OverflowError):
            clock = 0
        for crisis in crises.values():
            if not isinstance(crisis, dict):
                continue
            status = crisis.get("status")
            expires = int(crisis.get("expires_clock", 0) or 0)
            if status == "active" and clock < expires:
                factor = 1.0
            elif status == "ended" and clock < int(crisis.get("recovery_end_clock", 0) or 0):
                recovery_end = int(crisis.get("recovery_end_clock", clock) or clock)
                factor = max(0.0, min(1.0, (recovery_end - clock) / max(1, recovery_end - expires)))
            else:
                continue
            effect = (crisis.get("effects", {}) or {}).get(str(zone), {})
            if not isinstance(effect, dict):
                continue
            # Alpha88：官府/NPC 自主应对与玩家参与会削弱负面危机的持续影响。
            try:
                relief = max(0.0, min(0.70, float(crisis.get("npc_relief", 0.0)) + float(crisis.get("player_relief", 0.0))))
            except (TypeError, ValueError, OverflowError):
                relief = 0.0
            for key in ("security", "commerce", "travel"):
                try:
                    value = int(effect.get(key, 0))
                    adjusted = value * (1.0 - relief) if value < 0 else value
                    result[key] += int(round(adjusted * factor))
                except (TypeError, ValueError, OverflowError):
                    pass
    return {key: max(-60, min(30, value)) for key, value in result.items()}


def _ensure_row(player, zone):
    state = _state(player)
    row = state.get(zone)
    if not isinstance(row, dict):
        row = {"security": 0, "commerce": 0, "travel": 0, "last_recovery": 0, "events": {}}
        state[zone] = row
    row.setdefault("events", {})
    return row


def _change(player, zone, *, security=0, commerce=0, travel=0):
    row = _ensure_row(player, zone)
    for key, amount in (("security", security), ("commerce", commerce), ("travel", travel)):
        try:
            old = int(row.get(key, 0))
            row[key] = max(-60, min(30, old + int(amount)))
        except (TypeError, ValueError, OverflowError):
            row[key] = max(-60, min(30, int(amount)))
    return row


def record_criminal_defeat(player, room_id, enemy_name, enemy_data=None):
    """只对配置表明确标记的恶人计入治安贡献，并按地区/目标设置冷却，防止刷分。"""
    config = get_config()
    profile = (config.get("criminal_enemies", {}) or {}).get(str(enemy_name))
    if not isinstance(profile, dict):
        return {"applied": False, "reason": "非治安目标"}
    room = engine.ROOMS.get(room_id, {}) or {}
    zone = room.get("zone", "main")
    try:
        clock = int(player.get_quest_clock())
    except (AttributeError, TypeError, ValueError):
        clock = 0
    row = _ensure_row(player, zone)
    events = row.setdefault("events", {})
    event_key = f"恶人:{enemy_name}"
    prior = events.get(event_key, {})
    try:
        last = int(prior.get("last_reward_clock", -999999)) if isinstance(prior, dict) else -999999
        cooldown = max(1, int(profile.get("cooldown", 24)))
    except (TypeError, ValueError, OverflowError):
        last, cooldown = -999999, 24
    if clock - last < cooldown:
        return {"applied": False, "reason": "目标贡献仍在冷却"}
    _change(player, zone,
            security=max(0, int(profile.get("security_gain", 0))),
            commerce=max(0, int(profile.get("commerce_gain", 0))))
    events[event_key] = {"last_reward_clock": clock}
    # Alpha90：清剿明确登记的恶人时，可对本地区相关暴乱/劫掠危机提供有限贡献。
    # 仍使用独立冷却和次数上限，避免同一目标反复刷取危机贡献。
    variables = _variables(player)
    crises = variables.get("world_crises", {})
    if isinstance(crises, dict):
        for crisis in crises.values():
            if not isinstance(crisis, dict) or crisis.get("status") != "active":
                continue
            try:
                if clock >= int(crisis.get("expires_clock", 0) or 0):
                    continue
            except (TypeError, ValueError, OverflowError):
                continue
            if str(zone) not in (crisis.get("effects", {}) or {}):
                continue
            action = crisis.get("player_action", {})
            auto = action.get("on_criminal_defeat", {}) if isinstance(action, dict) else {}
            if not isinstance(auto, dict) or not auto.get("enabled"):
                continue
            try:
                count = max(0, int(crisis.get("criminal_defeat_actions", 0)))
                limit = max(0, int(auto.get("max_actions", 2)))
                last = int(crisis.get("last_criminal_defeat_clock", -999999))
                cooldown = max(1, int(auto.get("cooldown", 6)))
                relief = max(0.0, float(crisis.get("player_relief", 0.0)))
                step = max(0.0, float(auto.get("relief_step", 0.08)))
                cap = max(0.0, min(0.55, float(auto.get("relief_cap", 0.24))))
            except (TypeError, ValueError, OverflowError):
                continue
            if count >= limit or relief >= cap or clock - last < cooldown:
                continue
            crisis["player_relief"] = round(min(cap, relief + step), 3)
            crisis["criminal_defeat_actions"] = count + 1
            crisis["last_criminal_defeat_clock"] = clock
            shorten = max(0, int(auto.get("shorten_duration", 1)))
            minimum = max(1, int(auto.get("min_remaining", 5)))
            crisis["expires_clock"] = max(clock + minimum, int(crisis.get("expires_clock", clock)) - shorten)
            crisis["stage"] = "局势受控" if float(crisis.get("npc_relief", 0.0)) + float(crisis["player_relief"]) >= 0.35 and not crisis.get("escalated") else crisis.get("stage", "发生")
            _queue_world_crisis_announcement(player, "【清剿战果】你清除了当地恶人，相关局势略有缓和。")
            break
    # Alpha86：玩家清除当地恶人也能推进正在进行的治安事件，和官府巡逻共同完成治理。
    incident = row.get("security_incident", {})
    event_rule = (config.get("security_events", {}) or {}).get(zone, {})
    incident_progressed = False
    if isinstance(incident, dict) and incident.get("status") == "active":
        try:
            if clock < int(incident.get("expires_clock", clock)):
                required = max(1, int(incident.get("required_patrols", 2)))
                incident["progress"] = min(required, max(0, int(incident.get("progress", 0))) + 1)
                incident.setdefault("contributors", []).append("玩家清剿：" + str(enemy_name))
                incident_progressed = True
                if incident["progress"] >= required:
                    _change(player, zone,
                            security=max(0, int(event_rule.get("security_reward", 2))),
                            commerce=max(0, int(event_rule.get("commerce_reward", 1))))
                    incident["status"] = "completed"
                    incident["completed_clock"] = clock
                    incident["result_text"] = str(event_rule.get("success_text", "官府与江湖人士共同遏制了当地恶人活动。"))
                    row["last_security_event_clock"] = clock
                    _record_security_event(player, zone, incident["result_text"], clock)
        except (TypeError, ValueError, OverflowError):
            pass
    return {"applied": True, "zone": zone, "security": int(profile.get("security_gain", 0)),
            "commerce": int(profile.get("commerce_gain", 0)), "target": str(enemy_name),
            "incident_progressed": incident_progressed,
            "incident_progress": int(incident.get("progress", 0)) if isinstance(incident, dict) else 0}


def record_patrol(player, npc_name, room_id):
    """官府/守卫巡逻为所在地区提供有限治安贡献；单地区按冷却计入，避免重复刷分。"""
    profile = (get_config().get("patrol_npcs", {}) or {}).get(str(npc_name))
    if not isinstance(profile, dict):
        return False
    room = engine.ROOMS.get(room_id, {}) or {}
    zone = room.get("zone", "main")
    try:
        clock = int(player.get_quest_clock())
    except (AttributeError, TypeError, ValueError):
        clock = 0
    row = _ensure_row(player, zone)
    events = row.setdefault("events", {})
    event_key = f"官府巡逻:{npc_name}"
    prior = events.get(event_key, {})
    try:
        last = int(prior.get("last_reward_clock", -999999)) if isinstance(prior, dict) else -999999
        cooldown = max(1, int(profile.get("cooldown", 6)))
        cap = max(0, int(profile.get("max_bonus", 15)))
        gained = max(0, int(profile.get("security_gain", 1)))
    except (TypeError, ValueError, OverflowError):
        last, cooldown, cap, gained = -999999, 6, 15, 1
    if clock - last < cooldown:
        return False
    # 上限只统计持久治安变化；危机期临时扣分不能变成额外的永久巡逻加成。
    current = get_permanent_region_delta(player, zone).get("security", 0)
    if current >= cap:
        return False
    _change(player, zone, security=min(gained, cap - current))
    events[event_key] = {"last_reward_clock": clock}
    # Alpha85：巡逻不仅改善日常治安，也能推进已发生的地区治安事件。
    incident = row.get("security_incident", {})
    event_rule = (get_config().get("security_events", {}) or {}).get(zone, {})
    if isinstance(incident, dict) and incident.get("status") == "active":
        allowed_npcs = event_rule.get("patrol_npcs", []) or []
        try:
            # 巡逻与世界时钟同 Tick 结算时，先到期的事件不能再被巡逻补完成。
            expired = clock >= int(incident.get("expires_clock", clock + 1))
        except (TypeError, ValueError, OverflowError):
            expired = True
        if str(npc_name) in allowed_npcs and not expired:
            incident["progress"] = min(
                max(1, int(incident.get("required_patrols", 2))),
                max(0, int(incident.get("progress", 0))) + 1,
            )
            incident.setdefault("contributors", []).append(str(npc_name))
            required = max(1, int(incident.get("required_patrols", 2)))
            if incident["progress"] >= required:
                _change(
                    player, zone,
                    security=max(0, int(event_rule.get("security_reward", 2))),
                    commerce=max(0, int(event_rule.get("commerce_reward", 1))),
                )
                incident["status"] = "completed"
                incident["completed_clock"] = clock
                incident["result_text"] = str(event_rule.get("success_text", "巡查已完成，当地治安有所改善。"))
                row["last_security_event_clock"] = clock
                _record_security_event(player, zone, incident["result_text"], clock)
    return True


def _record_security_event(player, zone, text, clock):
    variables = _variables(player)
    log = variables.setdefault("region_security_log", [])
    if not isinstance(log, list):
        log = []
        variables["region_security_log"] = log
    log.append({"zone": str(zone), "clock": int(clock), "text": str(text)})
    del log[:-50]


def process_region_security_events(player, clock=None):
    """按地区治安启动有期限的官府/守卫巡查事件，结果保存在 V12 variables。"""
    config = get_config()
    rules = config.get("security_events", {}) or {}
    try:
        clock = int(player.get_quest_clock() if clock is None else clock)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return []
    changed = []
    for zone, rule in rules.items():
        if zone not in engine.WORLD_REGIONS or not isinstance(rule, dict):
            continue
        row = _ensure_row(player, zone)
        incident = row.get("security_incident", {})
        if isinstance(incident, dict) and incident.get("status") == "active":
            if clock >= int(incident.get("expires_clock", clock + 1)):
                incident["status"] = "expired"
                incident["result_text"] = str(rule.get("failure_text", "巡查未能及时完成，治安问题仍未解决。"))
                row["last_security_event_clock"] = clock
                _record_security_event(player, zone, incident["result_text"], clock)
                changed.append({"zone": zone, "status": "expired"})
            continue
        ecology = player.get_region_ecology(zone)
        try:
            security = int(ecology.get("security", 70))
            threshold = int(rule.get("trigger_security", 40))
            cooldown = max(1, int(rule.get("cooldown", 36)))
            last = int(row.get("last_security_event_clock", -999999))
        except (TypeError, ValueError, OverflowError):
            continue
        if security > threshold or clock - last < cooldown:
            continue
        required = max(1, int(rule.get("required_patrols", 2)))
        incident = {
            "title": str(rule.get("title", "地区治安巡查")),
            "status": "active",
            "started_clock": clock,
            "expires_clock": clock + max(1, int(rule.get("duration", 24))),
            "progress": 0,
            "required_patrols": required,
            "contributors": [],
            "result_text": str(rule.get("start_text", "当地治安恶化，官府已安排巡查。")),
        }
        row["security_incident"] = incident
        _record_security_event(player, zone, incident["result_text"], clock)
        changed.append({"zone": zone, "status": "active", "title": incident["title"]})
    return changed


def _queue_world_crisis_announcement(player, message):
    variables = _variables(player)
    queue = variables.setdefault("pending_world_crisis_announcements", [])
    if not isinstance(queue, list):
        queue = []
        variables["pending_world_crisis_announcements"] = queue
    if message and message not in queue:
        queue.append(str(message)[:240])
        del queue[:-50]


def list_world_crises(player, zone=None):
    """列出当前仍有效的外部世界局势事件，可按地区筛选。"""
    crises = _variables(player).get("world_crises", {})
    if not isinstance(crises, dict):
        return []
    try:
        clock = int(player.get_quest_clock())
    except (AttributeError, TypeError, ValueError, OverflowError):
        clock = 0
    rows = []
    for crisis in crises.values():
        if not isinstance(crisis, dict):
            continue
        status = crisis.get("status")
        if status == "active":
            if clock >= int(crisis.get("expires_clock", 0) or 0):
                continue
            remaining = max(0, int(crisis.get("expires_clock", clock)) - clock)
            row = {**crisis, "remaining": remaining, "recovery_remaining": 0}
        elif status == "ended" and clock < int(crisis.get("recovery_end_clock", 0) or 0):
            recovery_remaining = max(0, int(crisis.get("recovery_end_clock", clock)) - clock)
            row = {**crisis, "remaining": 0, "recovery_remaining": recovery_remaining}
        else:
            continue
        affected = list((crisis.get("effects", {}) or {}).keys())
        if zone is not None and str(zone) not in affected:
            continue
        rows.append(row)
    return rows


def process_external_world_crises(player, clock=None):
    """Alpha87：按世界时钟触发战争、暴乱、商路封锁等外部危机，并限时影响地区生态。"""
    config = get_config().get("external_world_events", {}) or {}
    try:
        clock = int(player.get_quest_clock() if clock is None else clock)
        interval = max(1, int(config.get("roll_interval", 24)))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return []
    variables = _variables(player)
    crises = variables.setdefault("world_crises", {})
    if not isinstance(crises, dict):
        crises = {}
        variables["world_crises"] = crises
    rows = []
    # 结束到期事件，恢复公告只发一次。
    for crisis_id, crisis in list(crises.items()):
        if not isinstance(crisis, dict) or crisis.get("status") != "active":
            continue
        if clock >= int(crisis.get("expires_clock", clock + 1)):
            crisis["status"] = "ended"
            crisis["ended_clock"] = clock
            # Alpha89：结束结果取决于官府/NPC应对、玩家援手与是否曾经恶化。
            try:
                relief = max(0.0, min(0.90, float(crisis.get("npc_relief", 0.0)) + float(crisis.get("player_relief", 0.0))))
            except (TypeError, ValueError, OverflowError):
                relief = 0.0
            if relief >= 0.35:
                crisis["outcome"] = "得到控制"
                crisis["stage"] = "局势受控"
                fade = max(3, int(config.get("recovery_fade", 12)) // 2)
                outcome_text = "各方及时应对，局势得到控制，受影响地区开始较快恢复。"
            elif crisis.get("escalated"):
                crisis["outcome"] = "留下余波"
                crisis["stage"] = "余波未平"
                fade = max(1, int(config.get("recovery_fade", 12)) * 2)
                outcome_text = "局势虽已告一段落，但此前的动荡仍在影响当地，恢复需要更多时日。"
            else:
                crisis["outcome"] = "逐步平息"
                fade = max(1, int(config.get("recovery_fade", 12)))
                outcome_text = str(crisis.get("end_announcement", "局势逐渐平息，受影响地区开始恢复秩序。"))
            crisis["recovery_end_clock"] = clock + fade
            message = str(crisis.get("end_announcement", outcome_text)) if crisis.get("outcome") == "逐步平息" else outcome_text
            _queue_world_crisis_announcement(player, "【世界局势】" + message)
            rows.append({"id": crisis_id, "status": "ended", "outcome": crisis["outcome"]})

    active = [c for c in crises.values() if isinstance(c, dict) and c.get("status") == "active" and clock < int(c.get("expires_clock", 0) or 0)]
    # NPC 自主应对：按事件配置的间隔逐步压低危机影响；不是每个指令都即时成功。
    for crisis in active:
        # 危机长期无人控制时可能升级，影响更严重；升级只发生一次并留下世界公告。
        escalation = crisis.get("escalation", {})
        if isinstance(escalation, dict) and not crisis.get("escalated"):
            try:
                escalation_after = max(1, int(escalation.get("after", 24)))
                elapsed = clock - int(crisis.get("started_clock", clock))
                multiplier = max(1.0, min(2.0, float(escalation.get("multiplier", 1.25))))
            except (TypeError, ValueError, OverflowError):
                escalation_after, elapsed, multiplier = 999999, 0, 1.0
            if elapsed >= escalation_after:
                effects = crisis.get("effects", {})
                if isinstance(effects, dict):
                    for region_effect in effects.values():
                        if not isinstance(region_effect, dict):
                            continue
                        for metric, value in list(region_effect.items()):
                            try:
                                numeric = int(value)
                            except (TypeError, ValueError, OverflowError):
                                continue
                            if numeric < 0:
                                region_effect[metric] = int(round(numeric * multiplier))
                # 配置的扩散影响只写入当前存档事件，绝不污染全局配置或其他存档。
                spread = escalation.get("spread_effects", {}) if isinstance(escalation, dict) else {}
                if isinstance(spread, dict):
                    for spread_zone, spread_values in spread.items():
                        if spread_zone not in engine.WORLD_REGIONS or not isinstance(spread_values, dict):
                            continue
                        current_effect = crisis.setdefault("effects", {}).setdefault(str(spread_zone), {})
                        if not isinstance(current_effect, dict):
                            current_effect = {}
                            crisis["effects"][str(spread_zone)] = current_effect
                        for metric, value in spread_values.items():
                            if metric not in ("security", "commerce", "travel"):
                                continue
                            try:
                                addition = int(value)
                            except (TypeError, ValueError, OverflowError):
                                continue
                            # 同一危机只扩散一次；累加仅作用于该危机的独立副本。
                            current_effect[metric] = int(current_effect.get(metric, 0) or 0) + addition
                crisis["escalated"] = True
                crisis["stage"] = "局势恶化"
                escalation_text = str(escalation.get("announcement", "局势持续恶化，当地压力进一步增加。"))
                _queue_world_crisis_announcement(player, "【局势恶化】" + escalation_text)
                rows.append({"id": crisis.get("id"), "status": "escalated"})
        response = crisis.get("npc_response", {})
        if not isinstance(response, dict) or not response:
            continue
        try:
            response_interval = max(1, int(response.get("interval", 12)))
            last_response = int(crisis.get("last_npc_response_clock", crisis.get("started_clock", clock)))
            current_relief = max(0.0, min(0.70, float(crisis.get("npc_relief", 0.0))))
            relief_step = max(0.0, float(response.get("relief_step", 0.10)))
            relief_cap = max(0.0, min(0.45, float(response.get("relief_cap", 0.30))))
        except (TypeError, ValueError, OverflowError):
            continue
        if clock - last_response < response_interval or current_relief >= relief_cap:
            continue
        crisis["npc_relief"] = round(min(relief_cap, current_relief + relief_step), 3)
        crisis["last_npc_response_clock"] = clock
        response_text = str(response.get("announcement", "官府与当地人物正在设法控制局势。"))
        if response_text and not crisis.get("npc_response_announced"):
            _queue_world_crisis_announcement(player, "【局势应对】" + response_text)
            crisis["npc_response_announced"] = True
        rows.append({"id": crisis.get("id"), "status": "npc_response", "relief": crisis["npc_relief"]})
    max_active = max(1, int(config.get("max_active", 2)))
    last_roll = int(variables.get("world_crisis_last_roll", -999999) or -999999)
    if clock - last_roll < interval or len(active) >= max_active:
        return rows
    variables["world_crisis_last_roll"] = clock
    event_rows = config.get("events", []) or []
    eligible = []
    for event in event_rows:
        if not isinstance(event, dict) or not event.get("id"):
            continue
        if not isinstance(event.get("effects"), dict) or not event.get("effects"):
            continue
        prior = crises.get(str(event["id"]), {})
        cooldown = max(1, int(event.get("cooldown", 72)))
        last_started = int(prior.get("started_clock", -999999)) if isinstance(prior, dict) else -999999
        if clock - last_started < cooldown:
            continue
        if any(set((c.get("effects", {}) or {}).keys()).intersection(event["effects"].keys()) for c in active):
            continue
        eligible.append(event)
    if not eligible:
        return rows
    # 不依赖随机全局状态；相同存档和世界时钟得到稳定结果，避免读档重复刷事件。
    import random
    rng = random.Random((clock + 17) * 7919 + len(crises) * 104729)
    chance = max(0.0, min(1.0, float(config.get("trigger_chance", 0.25))))
    if rng.random() >= chance:
        return rows
    event = eligible[rng.randrange(len(eligible))]
    duration = max(1, int(event.get("duration", 48)))
    crisis = {
        "id": str(event["id"]), "title": str(event.get("title", "江湖突发事件")),
        "type": str(event.get("type", "局势变化")), "status": "active",
        "started_clock": clock, "expires_clock": clock + duration,
        # 必须深拷贝：升级时会调整影响值，不能改写共享配置数据。
        "effects": copy.deepcopy(event["effects"]),
        "announcement": str(event.get("announcement", "江湖各地局势出现变化。")),
        "end_announcement": str(event.get("end_announcement", "局势逐渐平息，受影响地区开始恢复秩序。")),
        "npc_response": dict(event.get("npc_response", {}) or {}),
        "player_action": dict(event.get("player_action", {}) or {}),
        "escalation": dict(event.get("escalation", {}) or {}),
        "escalated": False,
        "stage": "发生",
        "last_npc_response_clock": clock,
        "npc_relief": 0.0,
        "player_relief": 0.0,
        "player_actions": 0,
        "last_player_action_clock": -999999,
    }
    crises[str(event["id"])] = crisis
    _queue_world_crisis_announcement(player, "【世界局势】" + crisis["announcement"])
    rows.append({"id": str(event["id"]), "status": "active", "title": crisis["title"]})
    return rows


def assist_world_crisis(player, zone):
    """Alpha88：玩家在受影响地区协助应对外部危机，有限削弱危机并缩短持续时间。"""
    variables = _variables(player)
    crises = variables.get("world_crises", {})
    if not isinstance(crises, dict):
        return False, "当前没有可协助处理的外部局势。", None
    try:
        clock = int(player.get_quest_clock())
    except (AttributeError, TypeError, ValueError, OverflowError):
        clock = 0
    for crisis in crises.values():
        if not isinstance(crisis, dict) or crisis.get("status") != "active":
            continue
        if clock >= int(crisis.get("expires_clock", 0) or 0):
            continue
        if str(zone) not in (crisis.get("effects", {}) or {}):
            continue
        action = crisis.get("player_action", {})
        if not isinstance(action, dict) or not action:
            continue
        try:
            cooldown = max(1, int(action.get("cooldown", 8)))
            max_actions = max(1, int(action.get("max_actions", 2)))
            actions_done = max(0, int(crisis.get("player_actions", 0)))
            last_action = int(crisis.get("last_player_action_clock", -999999))
            relief_step = max(0.0, float(action.get("relief_step", 0.20)))
            relief_cap = max(0.0, min(0.55, float(action.get("relief_cap", 0.40))))
        except (TypeError, ValueError, OverflowError):
            continue
        if actions_done >= max_actions:
            continue
        if clock - last_action < cooldown:
            return False, f"你刚刚协助过相关事务，请等待 {cooldown - (clock - last_action)} 个世界时刻再行动。", crisis
        current_relief = max(0.0, min(0.70, float(crisis.get("player_relief", 0.0))))
        if current_relief >= relief_cap:
            continue
        crisis["player_relief"] = round(min(relief_cap, current_relief + relief_step), 3)
        crisis["player_actions"] = actions_done + 1
        try:
            combined_relief = float(crisis.get("npc_relief", 0.0)) + float(crisis["player_relief"])
        except (TypeError, ValueError, OverflowError):
            combined_relief = float(crisis["player_relief"])
        if combined_relief >= 0.35 and not crisis.get("escalated"):
            crisis["stage"] = "局势受控"
        crisis["last_player_action_clock"] = clock
        shorten = max(0, int(action.get("shorten_duration", 4)))
        min_remaining = max(1, int(action.get("min_remaining", 6)))
        crisis["expires_clock"] = max(clock + min_remaining, int(crisis.get("expires_clock", clock)) - shorten)
        # Alpha91：协助行动除削弱危机持续影响外，还按事件配置即时改善当前地区指标。
        # 效果必须由事件数据明确配置，且沿用地区变化的上下限，避免无配置事件被意外增强。
        immediate = action.get("immediate_effects", {})
        local_effect = immediate.get(str(zone), {}) if isinstance(immediate, dict) else {}
        applied_effect = {key: 0 for key in ("security", "commerce", "travel")}
        if isinstance(local_effect, dict):
            try:
                applied_effect = {key: max(-3, min(3, int(local_effect.get(key, 0)))) for key in applied_effect}
                if any(applied_effect.values()):
                    _change(player, zone, **applied_effect)
            except (TypeError, ValueError, OverflowError):
                applied_effect = {key: 0 for key in ("security", "commerce", "travel")}
        message = str(action.get("success_text", "你协助当地人物应对局势，危机影响有所减轻。"))
        improved = [f"{label}{value:+d}" for key, label in (("security", "治安"), ("commerce", "商路"), ("travel", "通行"))
                    if (value := applied_effect.get(key, 0)) != 0]
        if improved:
            message += "（当地即时变化：" + "、".join(improved) + "）"
        _queue_world_crisis_announcement(player, "【江湖援手】" + message)
        return True, message, crisis
    return False, "当前地区没有可由你直接协助的外部危机，或相关事务已处理到当前上限。", None


def get_security_incident(player, zone):
    row = _state(player).get(str(zone), {})
    incident = row.get("security_incident", {}) if isinstance(row, dict) else {}
    return dict(incident) if isinstance(incident, dict) else {}


def process_crime_pressure(player, clock=None):
    """治安已很差且恶人活动持续的地区会缓慢恶化；有冷却，不会每个世界时钟都下降。"""
    config = get_config()
    rule = config.get("crime_pressure", {}) or {}
    try:
        clock = int(player.get_quest_clock() if clock is None else clock)
        threshold = int(rule.get("max_security", 35))
        interval = max(1, int(rule.get("interval", 12)))
        loss = max(0, int(rule.get("security_loss", 1)))
        commerce_loss = max(0, int(rule.get("commerce_loss", 1)))
    except (AttributeError, TypeError, ValueError, OverflowError):
        return
    for zone in rule.get("zones", []) or []:
        if zone not in engine.WORLD_REGIONS:
            continue
        current = player.get_region_ecology(zone)
        if int(current.get("security", 70)) > threshold:
            continue
        row = _ensure_row(player, zone)
        try:
            last = int(row.get("last_crime_clock", -999999))
        except (TypeError, ValueError, OverflowError):
            last = -999999
        if clock - last < interval:
            continue
        _change(player, zone, security=-loss, commerce=-commerce_loss)
        row["last_crime_clock"] = clock


def process_natural_recovery(player, clock=None):
    """长期平稳时缓慢恢复被破坏的治安；恢复只回到地区基础水平附近，不会无限加分。"""
    config = get_config()
    recovery = config.get("natural_recovery", {}) or {}
    try:
        interval = max(1, int(recovery.get("interval", 24)))
        amount = max(0, int(recovery.get("amount", 1)))
        clock = int(player.get_quest_clock() if clock is None else clock)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return
    state = _state(player)
    for zone, region in engine.WORLD_REGIONS.items():
        row = _ensure_row(player, zone)
        # 只恢复持久损伤；外部危机的临时扣分由危机结算自行消退，不能被“治成”永久加成。
        delta = get_permanent_region_delta(player, zone)
        if delta["security"] >= 0:
            continue
        try:
            last = int(row.get("last_recovery", 0))
            last_crime = int(row.get("last_crime_clock", -999999))
        except (TypeError, ValueError, OverflowError):
            last, last_crime = 0, -999999
        if clock - last < interval or clock - last_crime < interval:
            continue
        base = (region.get("region_ecology", {}) or {}).get("security_base", 70)
        current = int(base) + delta["security"]
        if current < int(base):
            _change(player, zone, security=min(amount, -delta["security"]))
            row["last_recovery"] = clock


def extra_enemies(zone, security):
    """按当前治安返回本地区额外可遭遇敌人，结果仍需由调用方校验敌人存在。"""
    pools = (get_config().get("extra_enemy_pools", {}) or {}).get(zone, []) or []
    result = []
    try:
        security = max(0, min(100, int(security)))
    except (TypeError, ValueError, OverflowError):
        security = 70
    for row in pools:
        if not isinstance(row, dict):
            continue
        try:
            threshold = int(row.get("max_security", -1))
        except (TypeError, ValueError, OverflowError):
            continue
        if security <= threshold:
            result.extend(str(name) for name in row.get("enemies", []) if name)
    # 稳定去重，防止同一敌人因多个阈值重复加权。
    return list(dict.fromkeys(result))


def security_band(security):
    try:
        security = max(0, min(100, int(security)))
    except (TypeError, ValueError, OverflowError):
        security = 70
    for band in get_config().get("security_bands", []) or []:
        try:
            if security >= int(band.get("min", 0)):
                return dict(band)
        except (TypeError, ValueError, OverflowError):
            continue
    return {"label": "治安情况不明", "criminal_activity": "不明", "patrol": "常态"}


def urban_crime_chance(zone, room_id, security):
    """治安很差时，指定城镇街巷才会发生低频街头犯罪遭遇。"""
    config = get_config()
    rule = config.get("urban_crime", {}) or {}
    if zone != rule.get("zone") or room_id not in (rule.get("rooms", []) or []):
        return 0.0
    try:
        security = max(0, min(100, int(security)))
        threshold = int(rule.get("max_security", 35))
        base = float(rule.get("base_chance", 0.04))
        slope = float(rule.get("per_missing_point", 0.004))
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if security > threshold:
        return 0.0
    return max(0.02, min(0.18, base + (threshold - security) * slope))


def urban_crime_enemies(zone, room_id, security):
    config = get_config()
    rule = config.get("urban_crime", {}) or {}
    if urban_crime_chance(zone, room_id, security) <= 0:
        return []
    try:
        security = int(security)
    except (TypeError, ValueError, OverflowError):
        return []
    result = list(rule.get("enemies", []) or [])
    if security <= int(rule.get("severe_threshold", 20)):
        result.extend(rule.get("severe_enemies", []) or [])
    return list(dict.fromkeys(str(name) for name in result if name))
