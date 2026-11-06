# -*- coding: utf-8 -*-
"""Alpha82：尸体/复活计时与 NPC 死亡策略。状态保存在 V12 world_state.variables 内。"""
import time

NORMAL_SECONDS = 60
BOSS_SECONDS = 300
NORMAL_CORPSE_SECONDS = 60
BOSS_CORPSE_SECONDS = 120

def _records(player):
    world = getattr(player, "world_state", None)
    if not isinstance(world, dict):
        return {}
    variables = world.setdefault("variables", {})
    if not isinstance(variables, dict):
        variables = {}; world["variables"] = variables
    records = variables.setdefault("dead_entities", {})
    if not isinstance(records, dict):
        records = {}; variables["dead_entities"] = records
    return records

def death_key(room_id, name, kind="enemy"):
    return f"{kind}:{room_id}:{name}"

def _respawn_delays(tier, respawn_seconds=None, corpse_seconds=None):
    """按敌人档位给出默认计时；允许 data 中的敌人单独覆盖。"""
    is_boss = str(tier).strip().lower() == "boss"
    respawn = BOSS_SECONDS if is_boss else NORMAL_SECONDS
    corpse = BOSS_CORPSE_SECONDS if is_boss else NORMAL_CORPSE_SECONDS
    for raw, field in ((respawn_seconds, "respawn"), (corpse_seconds, "corpse")):
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            continue
        if value <= 0:
            continue
        if field == "respawn":
            respawn = value
        else:
            corpse = value
    return respawn, corpse

def record_death(player, room_id, name, tier="normal", kind="enemy", now=None, respawn_seconds=None, corpse_seconds=None):
    now = time.time() if now is None else float(now)
    respawn_delay, corpse_delay = _respawn_delays(tier, respawn_seconds, corpse_seconds)
    _records(player)[death_key(room_id, name, kind)] = {
        "name": str(name), "room_id": str(room_id), "kind": str(kind), "tier": str(tier),
        "death_at": now, "corpse_until": now + corpse_delay, "respawn_at": now + respawn_delay,
        "respawn_seconds": respawn_delay, "corpse_seconds": corpse_delay,
    }

def entity_state(player, room_id, name, kind="enemy", now=None):
    now = time.time() if now is None else float(now)
    key = death_key(room_id, name, kind)
    records = _records(player)
    row = records.get(key)
    if not isinstance(row, dict): return "alive", None
    try:
        # 兼容早期存档中只记录死亡时间、尚未保存完整计时字段的实体记录。
        # 不能把缺失字段默认成 0，否则读档后敌人会立即被当作已复活。
        is_boss = str(row.get("tier", "normal")).strip().lower() == "boss"
        respawn_delay = float(row.get("respawn_seconds", BOSS_SECONDS if is_boss else NORMAL_SECONDS))
        corpse_delay = float(row.get("corpse_seconds", BOSS_CORPSE_SECONDS if is_boss else NORMAL_CORPSE_SECONDS))
        death_at = float(row.get("death_at", now))
        respawn_at = float(row.get("respawn_at", death_at + respawn_delay))
        corpse_until = float(row.get("corpse_until", death_at + corpse_delay))
    except (TypeError, ValueError, OverflowError):
        records.pop(key, None); return "alive", None
    if now >= respawn_at:
        records.pop(key, None)
        return "alive", None
    if now < corpse_until:
        return "corpse", row
    return "dead", row

def visible_enemies(player, room_id, names, now=None):
    alive=[]; corpses=[]
    for name in names or []:
        state,row=entity_state(player, room_id, name, "enemy", now)
        if state == "alive": alive.append(name)
        elif state == "corpse": corpses.append(row)
    return alive, corpses


def calculate_encounter_chance(security, travel, base=0.18):
    """计算进入危险场景时的额外随机遭遇率。普通赶路不应频繁强制打断。"""
    try: security = max(0, min(100, int(security)))
    except (TypeError, ValueError, OverflowError): security = 70
    try: travel = max(0, min(100, int(travel)))
    except (TypeError, ValueError, OverflowError): travel = 70
    try: base = max(0.0, min(0.45, float(base)))
    except (TypeError, ValueError, OverflowError): base = 0.18
    chance = base + (50 - security) * 0.0025 + (50 - travel) * 0.0015
    return max(0.05, min(0.45, chance))


def random_encounter_candidates(names, enemy_data):
    """过滤随机遭遇候选：多人同场时不随机强制触发首领战。单一首领房仍可按原规则遭遇。"""
    candidates = [name for name in (names or []) if name in (enemy_data or {})]
    if len(candidates) <= 1:
        return candidates
    ordinary = [name for name in candidates
                if str((enemy_data.get(name) or {}).get("tier", "normal")).lower() not in ("boss", "首领")]
    return ordinary


NPC_POLICY_PROTECTED = "protected"
NPC_POLICY_RESPAWN = "respawn"
NPC_POLICY_NONE = "none"

def npc_death_policy(npc_data):
    """按 NPC 静态配置判断死亡策略；默认保护剧情/服务角色，绝不擅自让关键 NPC 复活。

    只有明确配置 death_policy='respawn' 的普通 NPC 才允许进入定时复活流程。
    """
    data = npc_data if isinstance(npc_data, dict) else {}
    policy = str(data.get("death_policy", "") or "").strip().lower()
    if policy == NPC_POLICY_RESPAWN:
        return NPC_POLICY_RESPAWN
    if policy == NPC_POLICY_NONE:
        return NPC_POLICY_NONE
    # 默认安全策略：未明确声明可死亡的 NPC 均受保护。
    return NPC_POLICY_PROTECTED

def record_npc_death(player, room_id, name, npc_data=None, now=None):
    """记录 NPC 死亡。未明确允许复活的 NPC 拒绝记录，避免破坏任务与服务链。"""
    policy = npc_death_policy(npc_data)
    if policy != NPC_POLICY_RESPAWN:
        return False, policy
    record_death(player, room_id, name, tier="normal", kind="npc", now=now)
    return True, policy
