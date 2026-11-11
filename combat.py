# -*- coding: utf-8 -*-
"""
combat.py - 回合制战斗引擎、招式选择、胜负与奖励结算
"""

import random
from copy import deepcopy
import engine
from ui_output import BODY_WIDTH, safe_print as print, wrap_player_text
from player import request_autosave

Color = engine.Color
color_text = engine.color_text


def _emit(value):
    """战斗日志与其它界面共用同一正文折行宽度。"""
    print(wrap_player_text(value, width=BODY_WIDTH))


TELEGRAPH_MESSAGE = "【预警】{enemy}正在蓄力「{skill}」，下一回合将发动！"


def is_telegraph_skill(skill):
    """数据驱动的招牌技能判断；只有显式 telegraph=true 的招式需要预警。"""
    return isinstance(skill, dict) and skill.get("telegraph") is True


def telegraph_warning(enemy_name, skill):
    """固定格式的预警文案，调用方负责在下一回合结算原技能伤害。"""
    name = str((skill or {}).get("name", "")).strip()
    return TELEGRAPH_MESSAGE.format(enemy=enemy_name, skill=name)


def make_combat_prompt(player, enemy_name, enemy_hp, enemy_max_hp):
    """战斗提示符只保留简短气血信息，避免每回合挤占整行。"""
    hp = max(0, int(getattr(player, "hp", 0)))
    max_hp = max(1, int(getattr(player, "max_hp", 1)))
    enemy_pct = max(0, min(100, int(enemy_hp * 100 / max(1, enemy_max_hp))))
    return f"〔气血 {hp}/{max_hp}｜{enemy_name} {enemy_pct}%〕> "
draw_bar = engine.draw_bar
format_statuses = engine.format_statuses
process_status_effects = engine.process_status_effects
apply_shield = engine.apply_shield
apply_damage_reduction = engine.apply_damage_reduction
battle_pause = engine.battle_pause


def get_enemy_phases(enemy_data):
    phases = enemy_data.get("phases", []) if isinstance(enemy_data.get("phases"), list) else []
    return sorted([ph for ph in phases if isinstance(ph, dict)], key=lambda x: float(x.get("threshold", 0)), reverse=True)


def get_enemy_phase(enemy_data, hp, max_hp):
    """根据当前气血计算战斗阶段；没有 phases 时始终为 1。"""
    phases = get_enemy_phases(enemy_data)
    current = 1
    ratio = hp / max(1, max_hp)
    for idx, ph in enumerate(phases, 2):
        if ratio <= float(ph.get("threshold", 0)):
            current = idx
    return current


def get_enemy_phase_data(enemy_data, phase):
    phases = get_enemy_phases(enemy_data)
    if phase <= 1 or phase - 2 >= len(phases):
        return {}
    return phases[phase - 2]


def _ai_condition_met(skill, enemy_hp=None, enemy_max_hp=None, player=None, player_statuses=None, phase=1):
    """判断敌方技能的可用战术条件。未声明 AI 条件时保持旧行为。"""
    ai = skill.get("ai") or {}
    if not ai:
        return True

    if enemy_hp is not None and enemy_max_hp:
        ratio = enemy_hp / max(1, enemy_max_hp)
        if "enemy_hp_below" in ai and ratio >= float(ai["enemy_hp_below"]):
            return False
        if "enemy_hp_above" in ai and ratio <= float(ai["enemy_hp_above"]):
            return False

    if player is not None and player.max_hp:
        ratio = player.hp / max(1, player.max_hp)
        if "player_hp_below" in ai and ratio >= float(ai["player_hp_below"]):
            return False
        if "player_hp_above" in ai and ratio <= float(ai["player_hp_above"]):
            return False

    if int((ai.get("phase_at_least") or 1)) > int(phase):
        return False

    player_statuses = player_statuses or {}
    for status in ai.get("requires_target_status", []):
        if status not in player_statuses:
            return False
    for status in ai.get("target_status_absent", []):
        if status in player_statuses:
            return False
    return True


def pick_enemy_skill(enemy_data, enemy_hp=None, enemy_max_hp=None, player=None, player_statuses=None, phase=1):
    """选择敌方技能。

    兼容旧版：没有 ``ai`` 字段时，继续按原 chance 顺序尝试。
    新版：先按 priority 从高到低检查条件，满足条件且通过 chance 即执行；
    这样可以表达“玩家残血优先点穴”“目标未中毒才施毒”等战术。
    """
    skills = enemy_data.get("skills", [])
    if not skills:
        return None

    has_ai = any(isinstance(sk.get("ai"), dict) and sk.get("ai") for sk in skills)
    if not has_ai:
        for sk in skills:
            if random.random() < sk.get("chance", 0.3):
                return sk
        return None

    ordered = sorted(enumerate(skills), key=lambda pair: (-int((pair[1].get("ai") or {}).get("priority", 0)), pair[0]))
    for _, sk in ordered:
        if not _ai_condition_met(sk, enemy_hp, enemy_max_hp, player, player_statuses, phase):
            continue
        chance = float(sk.get("chance", 0.3))
        if random.random() < chance:
            return sk
    return None




def get_enemy_ai_style(enemy_data):
    """返回敌方战术配置键，供战斗逻辑判断。"""
    ai = enemy_data.get("ai") or {}
    return str(ai.get("style", "standard"))


def get_enemy_ai_style_label(enemy_data):
    """将内部战术配置转换为适合游戏内展示的中文。"""
    labels = {
        "standard": "常规", "elite": "精锐", "aggressive": "凶猛进攻",
        "beast": "野兽本能", "tactical": "战术应对", "boss": "首领战术",
        "ranged": "远程攻击",
    }
    return labels.get(get_enemy_ai_style(enemy_data), "常规")


def apply_world_combat_pressure(enemy_data, player):
    """把现有世界事件压力映射为本场敌人强度；只作用于战斗快照，不写存档。"""
    zone = getattr(player, "location", "")
    variables = getattr(player, "world_state", {}).get("variables", {}) if isinstance(getattr(player, "world_state", {}), dict) else {}
    pressure = 0
    if "bandit" in str(enemy_data.get("ai", {}).get("faction", "")):
        pressure = int(variables.get("world:bandit:pressure", 0) or 0)
    elif zone in ("official_road", "main") and enemy_data.get("ai", {}).get("faction") == "bandit":
        pressure = int(variables.get("world:main:bandit_pressure", 0) or 0)
    if pressure <= 0:
        return 0
    bonus = min(0.15, 0.05 * pressure)
    enemy_data["world_pressure"] = pressure
    enemy_data["hp"] = max(1, int(round(enemy_data["hp"] * (1 + bonus))))
    enemy_data["atk"] = max(0, int(round(enemy_data["atk"] * (1 + bonus))))
    enemy_data["defense"] = max(0, int(round(enemy_data["defense"] * (1 + bonus))))
    return pressure


def choose_enemy_action(enemy_data, enemy_hp, enemy_max_hp, player, player_statuses, phase=1, enemy_statuses=None):
    """返回 skill/basic/guard 三类敌方行动，统一承载战术风格。"""
    style = get_enemy_ai_style(enemy_data)
    enemy_statuses = enemy_statuses or {}
    ratio = enemy_hp / max(1, enemy_max_hp)
    if style in ("defensive", "tactical") and ratio <= 0.45 and "damage_reduction" not in enemy_statuses:
        if random.random() < (0.75 if style == "defensive" else 0.55):
            return {"action": "guard", "reduction": 35 if style == "defensive" else 25}
    skill = pick_enemy_skill(enemy_data, enemy_hp, enemy_max_hp, player, player_statuses, phase)
    if skill:
        style_bonus = {"aggressive": 0.15, "elite": 0.10, "boss": 0.15, "tactical": 0.05}.get(style, 0.0)
        if style_bonus and random.random() < style_bonus:
            return {"action": "skill", "skill": skill}
        if style in ("aggressive", "elite", "boss", "tactical"):
            return {"action": "skill", "skill": skill}
        return {"action": "skill", "skill": skill}
    return {"action": "basic"}

def _clamp(value, low, high):
    return max(low, min(high, value))


def _defeat_recovery(player, return_location="temple"):
    """统一处理战败后的恢复，返回适合玩家阅读的实际变化提示。"""
    max_hp = max(1, int(getattr(player, "max_hp", 1) or 1))
    before_hp = max(0, int(getattr(player, "hp", 0) or 0))
    recovered_hp = max(1, min(max_hp, int(max_hp * 0.5)))
    player.hp = recovered_hp
    player.location = return_location
    return f"养伤后气血恢复至 {recovered_hp}/{max_hp}，已返回古庙。"


def calculate_damage(attack, defense, multiplier=1.0):
    """百分比减伤公式：damage = max(1, 攻击 × 倍率 × 100 / (100 + 防御))。

    防御仍然有效，但不会像减法公式那样把高等级战斗压成每次 1 点伤害。
    """
    try:
        attack_value = max(0.0, float(attack) * float(multiplier))
    except (TypeError, ValueError, OverflowError):
        attack_value = 0.0
    try:
        defense_value = max(0, int(defense))
    except (TypeError, ValueError, OverflowError):
        defense_value = 0
    return max(1, int(attack_value * 100 / (100 + defense_value)))


def resolve_attack(raw_damage, attacker_hit, defender_dodge, attacker_crit, crit_bonus=0.0):
    """解析一次攻击：先判闪避，再判暴击。返回 (damage, outcome)。

    outcome: "miss" / "crit" / "hit"。
    命中率会被限制在安全区间，避免堆叠后出现 100% 命中或永远打不中。
    """
    hit_chance = _clamp(
        attacker_hit - defender_dodge,
        engine.COMBAT_DEFAULTS["min_hit"],
        engine.COMBAT_DEFAULTS["max_hit"],
    )
    if random.random() >= hit_chance:
        return 0, "miss"

    crit_chance = _clamp(attacker_crit + crit_bonus, 0.0, 0.50)
    if random.random() < crit_chance:
        return max(1, int(raw_damage * engine.COMBAT_DEFAULTS["crit_multiplier"])), "crit"
    return max(1, int(raw_damage)), "hit"


def _skill_effects(skill):
    """P2.5：兼容旧版单 effect，并允许技能声明多个 effects。"""
    effects = skill.get("effects")
    if isinstance(effects, list):
        return [e for e in effects if isinstance(e, dict) and e.get("type")]
    effect = skill.get("effect") or {}
    return [effect] if isinstance(effect, dict) and effect.get("type") else []


def has_skill_effect(skill, effect_type):
    return any(e.get("type") == effect_type for e in _skill_effects(skill))


def apply_skill_effect(skill, player, target_statuses, target_hit=True):
    """执行数据驱动的武学附加效果。目标类效果只在命中时生效；自身护体效果不受命中判定影响。"""
    messages = []
    for effect in _skill_effects(skill):
        etype = effect.get("type")
        if etype == "mp_restore":
            amount = max(0, int(effect.get("amount", 0)))
            before = player.mp
            player.mp = min(player.max_mp, player.mp + amount)
            messages.append(f"【{skill['name']}】吐纳调息，恢复 {player.mp - before} 点内力。")
        elif etype == "status":
            if not target_hit:
                continue
            chance = float(effect.get("chance", 1.0))
            if random.random() < chance:
                engine.add_status(target_statuses, effect.get("status"), int(effect.get("turns", 1)), int(effect.get("value", 0)))
                meta = engine.STATUS_EFFECTS.get(effect.get("status"), {})
                messages.append(f"【{skill['name']}】使目标陷入【{meta.get('name', effect.get('status'))}】！")
        elif etype == "self_status":
            chance = float(effect.get("chance", 1.0))
            if random.random() < chance:
                engine.add_status(engine.p_statuses_global, effect.get("status"), int(effect.get("turns", 1)), int(effect.get("value", 0)))
                meta = engine.STATUS_EFFECTS.get(effect.get("status"), {})
                messages.append(f"【{skill['name']}】运劲护体，获得【{meta.get('name', effect.get('status'))}】！")
    return messages



def apply_weapon_combat_effect(player, target_statuses, target_hit=True):
    """按当前装备武器的数据应用一次命中特效；不写入存档，旧存档无需迁移。"""
    if not target_hit:
        return []
    equipment = getattr(player, "equipment", {}) or {}
    weapon_name = equipment.get("weapon")
    weapon = engine.ITEMS.get(weapon_name, {}) if weapon_name else {}
    effect = weapon.get("weapon_effect") if isinstance(weapon, dict) else None
    # 品质变体可复用基础武器的特效定义，避免每个变体重复维护配置。
    if not isinstance(effect, dict):
        base_name = weapon.get("base_item") if isinstance(weapon, dict) else None
        base_weapon = engine.ITEMS.get(base_name, {}) if base_name else {}
        effect = base_weapon.get("weapon_effect") if isinstance(base_weapon, dict) else None
    if not isinstance(effect, dict) or effect.get("type") != "status":
        return []
    status = effect.get("status")
    if status not in engine.STATUS_EFFECTS:
        return []
    try:
        chance = max(0.0, min(1.0, float(effect.get("chance", 0.0))))
        turns = max(1, min(5, int(effect.get("turns", 1))))
        value = max(0, min(50, int(effect.get("value", 0))))
    except (TypeError, ValueError):
        return []
    if random.random() >= chance:
        return []
    engine.add_status(target_statuses, status, turns, value)
    meta = engine.STATUS_EFFECTS.get(status, {})
    return [f"【{weapon_name}】发挥兵刃特性，使对手陷入【{meta.get('name', status)}】！"]


def _combo_damage(raw_damage, skill, hit_chance, dodge, crit, crit_bonus=0.0):
    """判定武学额外连击，返回 [(damage, outcome), ...]。"""
    combo = next((e for e in _skill_effects(skill) if e.get("type") == "combo"), None)
    if not combo:
        return []
    if random.random() >= float(combo.get("chance", 0.0)):
        return []
    hits = max(1, min(3, int(combo.get("hits", 2))))
    ratio = max(0.1, min(1.0, float(combo.get("damage_ratio", 0.6))))
    results = []
    for _ in range(hits - 1):
        results.append(resolve_attack(max(1, int(raw_damage * ratio)), hit_chance, dodge, crit, crit_bonus))
    return results


def _roll_reward_amount(spec, default=0):
    """解析 P2.8 奖励数值；兼容旧版固定整数。"""
    if isinstance(spec, bool):
        return int(spec)
    if isinstance(spec, (int, float)):
        return max(0, int(spec))
    if isinstance(spec, dict):
        if "amount" in spec:
            return max(0, int(spec.get("amount", default)))
        try:
            low = int(spec.get("min", spec.get("max", default)))
            high = int(spec.get("max", low))
        except (TypeError, ValueError):
            return max(0, int(default))
        low, high = max(0, low), max(0, high)
        if low > high:
            low, high = high, low
        return random.randint(low, high)
    return max(0, int(default))


def _resolve_drop_quantity(drop):
    """解析单项掉落数量；旧数据默认每次掉落 1 件。"""
    if "quantity" in drop:
        try:
            return max(1, int(drop.get("quantity", 1)))
        except (TypeError, ValueError):
            return 1
    try:
        low = int(drop.get("min_qty", 1))
        high = int(drop.get("max_qty", low))
    except (TypeError, ValueError):
        return 1
    low, high = max(1, low), max(1, high)
    if low > high:
        low, high = high, low
    return random.randint(low, high)


def _resolve_drop_quality(drop):
    """P2.15：解析可选品质池；未命中时保持基础物品。

    quality_pool 使用独立权重 chance，总和无需等于 1；剩余概率代表普通品质。
    只在基础物品声明 quality_variants 时生效，因此旧掉落数据完全不受影响。
    """
    pool = drop.get("quality_pool", []) or []
    if not isinstance(pool, list) or not pool:
        return None
    roll = random.random()
    cursor = 0.0
    for entry in pool:
        if not isinstance(entry, dict):
            continue
        quality = entry.get("quality")
        try:
            chance = max(0.0, min(1.0, float(entry.get("chance", 0.0))))
        except (TypeError, ValueError):
            chance = 0.0
        cursor += chance
        if roll < cursor:
            return quality
    return None


def _resolve_drop_item(drop):
    """P2.15：把基础装备按品质池解析成实际物品名。"""
    base_item = drop["item"]
    base_info = engine.ITEMS.get(base_item, {})
    quality = _resolve_drop_quality(drop)
    variants = base_info.get("quality_variants", {})
    if quality and isinstance(variants, dict):
        variant = variants.get(quality)
        if variant in engine.ITEMS:
            return variant
    return base_item


def resolve_enemy_rewards(enemy_data):
    """P2.15：统一解析战斗奖励。

    兼容 P2.8-P2.14 全部掉落字段，并新增可选 quality_pool：
    - exp/gold：固定整数，或 {"amount": n}，或 {"min": n, "max": n}
    - drops[].guaranteed：必掉；未声明时沿用 chance 判定
    - drops[].quantity：固定数量
    - drops[].min_qty/max_qty：随机数量
    - drops[].rolls：同一掉落表最多独立判定多次
    - drops[].quality_pool：可选品质池，未命中则掉落基础物品
    - equipment_quality_pool：穿戴装备掉落命中后，按品质池升级为对应变体
    """
    exp = _roll_reward_amount(enemy_data.get("exp", 10), 10)
    gold = _roll_reward_amount(enemy_data.get("gold", 5), 5)
    resolved_drops = []

    for drop in enemy_data.get("drops", []) or []:
        if not isinstance(drop, dict) or not drop.get("item"):
            continue
        # 装备只从实际穿戴栏掉落，避免旧掉落表把装备当普通材料高频刷出。
        if isinstance(enemy_data.get("equipment"), dict) and engine.ITEMS.get(drop.get("item"), {}).get("type") in ("weapon", "armor"):
            continue
        try:
            rolls = max(1, int(drop.get("rolls", 1)))
        except (TypeError, ValueError):
            rolls = 1
        guaranteed = bool(drop.get("guaranteed", False))
        try:
            chance = max(0.0, min(1.0, float(drop.get("chance", 1.0 if guaranteed else 0.0))))
        except (TypeError, ValueError):
            chance = 1.0 if guaranteed else 0.0
        for _ in range(rolls):
            if guaranteed or random.random() < chance:
                resolved_drops.append({
                    "item": _resolve_drop_item(drop),
                    "quantity": _resolve_drop_quantity(drop),
                })

    # 低爆率装备掉落：每次击败最多掉一件，且只能来自敌人当前实际穿戴的装备。
    # 未配置 equipment/equipment_drop_chance 的旧敌人完全保持原行为。
    # equipment_quality_pool 可选：命中后按品质池把该件装备升级为精良/稀有/史诗变体。
    equipment = enemy_data.get("equipment", {})
    try:
        gear_chance = max(0.0, min(0.25, float(enemy_data.get("equipment_drop_chance", 0.0))))
    except (TypeError, ValueError):
        gear_chance = 0.0
    worn = []
    if isinstance(equipment, dict):
        for slot in ("weapon", "armor"):
            item_name = equipment.get(slot)
            if item_name and engine.ITEMS.get(item_name, {}).get("type") in ("weapon", "armor"):
                worn.append(str(item_name))
    if worn and gear_chance > 0 and random.random() < gear_chance:
        chosen = random.choice(worn)
        quality_pool = enemy_data.get("equipment_quality_pool", []) or []
        resolved_drops.append({
            "item": _resolve_drop_item({"item": chosen, "quality_pool": quality_pool}),
            "quantity": 1,
        })

    # 武学秘籍使用独立、极低概率；只有显式配置了有效秘籍物品的敌人才参与判定。
    manual = enemy_data.get("manual_drop")
    if isinstance(manual, dict) and manual.get("item") in engine.ITEMS:
        try:
            manual_chance = max(0.0, min(0.01, float(manual.get("chance", 0.0))))
        except (TypeError, ValueError):
            manual_chance = 0.0
        if manual_chance > 0 and random.random() < manual_chance:
            resolved_drops.append({"item": manual["item"], "quantity": 1})

    return {"exp": exp, "gold": gold, "drops": resolved_drops}


def _player_combat_stats(player):
    return player.get_hit_chance(), player.get_crit_chance(), player.get_dodge_chance()


def get_enemy_tier_label(tier):
    return {
        "normal": "普通", "ranged": "远程", "elite": "精英", "boss": "Boss",
    }.get(tier, "普通")


def get_enemy_growth_rates(tier):
    """返回敌人每高于基础等级 1 级的成长率（气血/攻击/防御）。"""
    return {
        "normal": (0.10, 0.07, 0.06),
        "ranged": (0.10, 0.08, 0.05),
        "elite": (0.13, 0.09, 0.08),
        "boss": (0.16, 0.11, 0.10),
    }.get(tier, (0.10, 0.07, 0.06))


def get_enemy_profile(enemy_name, room_id=None):
    """根据敌人基础等级与当前区域难度生成本场战斗的敌人档案。

    该计算只存在于当前战斗，不写入存档。未声明新字段时完全兼容旧敌人。
    """
    base = deepcopy(engine.ENEMIES.get(enemy_name, {}))
    if not base:
        return {}
    # 同类人形敌人可从数据配置中抽取少量装备/招式变化；原始配置不被修改，也不写入存档。
    variants = base.pop("loadout_variants", []) or []
    if isinstance(variants, list) and variants:
        valid = [v for v in variants if isinstance(v, dict) and isinstance(v.get("equipment", {}), dict)]
        if valid:
            weights = []
            for variant in valid:
                try:
                    weights.append(max(0.0, float(variant.get("weight", 1.0))))
                except (TypeError, ValueError):
                    weights.append(1.0)
            if sum(weights) <= 0:
                weights = [1.0] * len(valid)
            chosen = random.choices(valid, weights=weights, k=1)[0]
            base["equipment"] = deepcopy(chosen.get("equipment", base.get("equipment", {})))
            if isinstance(chosen.get("skills"), list):
                base["skills"] = deepcopy(chosen["skills"])
    room = engine.ROOMS.get(room_id or "", {})
    base_level = max(1, int(base.get("level", 1)))
    raw_zone_level = room.get("difficulty_level") or room.get("recommended_level") or 1
    try:
        zone_level = max(1, int(raw_zone_level))
    except (TypeError, ValueError, OverflowError):
        zone_level = 1
    level = max(base_level, zone_level)
    tier = base.get("tier", "normal")
    growth_levels = max(0, level - base_level)
    hp_rate, atk_rate, def_rate = get_enemy_growth_rates(tier)
    base["base_level"] = base_level
    base["level"] = level
    base["tier"] = tier
    base["tier_label"] = get_enemy_tier_label(tier)
    base["difficulty_level"] = zone_level
    base["difficulty_label"] = room.get("difficulty_label", "普通")
    base["base_hp"] = int(base.get("hp", 1))
    base["base_atk"] = int(base.get("atk", 0))
    base["base_defense"] = int(base.get("defense", 0))
    base["hp"] = max(1, int(round(base["base_hp"] * (1 + hp_rate * growth_levels))))
    base["atk"] = max(0, int(round(base["base_atk"] * (1 + atk_rate * growth_levels))))
    base["defense"] = max(0, int(round(base["base_defense"] * (1 + def_rate * growth_levels))))
    # 敌人装备会真实影响战斗属性，但采用折算系数，避免把玩家装备完整数值叠加到既有敌人面板后导致难度失控。
    worn = base.get("equipment", {})
    equipment_bonus = {"atk": 0, "defense": 0}
    if isinstance(worn, dict):
        weapon = engine.ITEMS.get(worn.get("weapon"), {})
        armor = engine.ITEMS.get(worn.get("armor"), {})
        if weapon.get("type") == "weapon":
            equipment_bonus["atk"] += max(0, min(6, int(round(float(weapon.get("atk", 0) or 0) * 0.25))))
        if armor.get("type") == "armor":
            equipment_bonus["defense"] += max(0, min(4, int(round(float(armor.get("defense", 0) or 0) * 0.25))))
    base["atk"] += equipment_bonus["atk"]
    base["defense"] += equipment_bonus["defense"]
    base["equipment_bonus"] = equipment_bonus
    base["exp"] = max(0, int(round(_roll_reward_amount(base.get("exp", 0), 0) * (1 + 0.08 * growth_levels))))
    base["gold"] = max(0, int(round(_roll_reward_amount(base.get("gold", 0), 0) * (1 + 0.06 * growth_levels))))
    base["growth_levels"] = growth_levels
    return base


def _enemy_combat_stats(enemy_data):
    return (
        float(enemy_data.get("hit", engine.COMBAT_DEFAULTS["hit"])),
        float(enemy_data.get("crit", engine.COMBAT_DEFAULTS["crit"])),
        float(enemy_data.get("dodge", engine.COMBAT_DEFAULTS["dodge"])),
    )


def experience_decay_multiplier(player_level, enemy_level):
    """低级敌人经验衰减：等级差 ≤1 全额，2 为 85%，3–4 为 70%，5–6 为 45%，7–9 为 25%，≥10 为 10%。"""
    try:
        diff = int(player_level) - int(enemy_level)
    except (TypeError, ValueError, OverflowError):
        diff = 0
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 0.85
    if diff <= 4:
        return 0.70
    if diff <= 6:
        return 0.45
    if diff <= 9:
        return 0.25
    return 0.10


def apply_experience_decay(rewards, player, enemy_data):
    """按玩家与敌人等级差折算战斗经验，最低仍保留 1 点。"""
    if not isinstance(rewards, dict):
        return rewards
    base_exp = rewards.get("exp", 0)
    try:
        base_exp = int(base_exp)
    except (TypeError, ValueError, OverflowError):
        base_exp = 0
    if base_exp <= 0:
        return rewards
    multiplier = experience_decay_multiplier(
        getattr(player, "level", 1), enemy_data.get("level", 1)
    )
    if multiplier >= 1.0:
        return rewards
    adjusted = dict(rewards)
    adjusted["exp"] = max(1, int(round(base_exp * multiplier)))
    return adjusted


def _finish_combat_victory(player, room_id, enemy_name, e_data):
    """统一结算胜利，确保普通攻击与持续伤害击倒都发放奖励。"""
    from world_lifecycle import entity_state, record_death

    # 防御重复进入结算路径：同一地点同名敌人已经死亡/仍在尸体期时，
    # 不得再次发放经验、银两或战利品。正常战斗入口也会检查此状态，
    # 这里再做一次兜底，避免其他结算入口重复调用造成奖励膨胀。
    state, _ = entity_state(player, room_id, enemy_name, "enemy")
    if state != "alive":
        print(f"【{enemy_name}】的战斗结果已经结算，不会重复发放奖励。")
        return

    print(f"\n{Color.BRIGHT_GREEN}你击败了【{enemy_name}】！{Color.RESET}")
    engine.clear_statuses()
    rewards = resolve_enemy_rewards(e_data)
    rewards = apply_experience_decay(rewards, player, e_data)
    from rewards import apply_reward_bundle
    result = apply_reward_bundle(player, rewards, source="战斗奖励")
    # 奖励包校验/结算失败时，不提交任务、死亡记录或地区功绩，避免
    # “奖励未发放但敌人已永久死亡”的不可恢复断点。实体状态仍保持可重试。
    if not result.get("ok"):
        print(f"{Color.RED}战斗奖励暂时无法结算，本次战斗记录未提交，可稍后重新挑战。{Color.RESET}")
        return

    player.update_quest_progress(enemy_name)
    tier = str(e_data.get("tier", "normal"))
    timers = {
        field: e_data[field]
        for field in ("respawn_seconds", "corpse_seconds")
        if e_data.get(field) is not None
    }
    record_death(player, room_id, enemy_name, tier=tier, kind="enemy", **timers)
    # 击败配置为治安目标的恶人，可改善所在地区治安；普通野兽不计入治安功绩。
    try:
        from region_activity import record_criminal_defeat
        activity_result = record_criminal_defeat(player, room_id, enemy_name, e_data)
        if activity_result.get("applied"):
            if hasattr(player, "process_region_ecology"):
                player.process_region_ecology()
            security_gain = int(activity_result.get("security", 0))
            commerce_gain = int(activity_result.get("commerce", 0))
            parts = []
            if security_gain:
                parts.append(f"当地治安改善 {security_gain} 点")
            if commerce_gain:
                parts.append(f"商路稳定度改善 {commerce_gain} 点")
            if activity_result.get("incident_progressed"):
                parts.append(f"治安事件进度 {activity_result.get('incident_progress', 0)}")
            if parts:
                print(f"{Color.GREEN}清除恶人势力：{'，'.join(parts)}。{Color.RESET}")
            if activity_result.get("incident_progressed"):
                print(f"{Color.CYAN}你的行动已计入当地治安事件。可输入“治安”查看进展。{Color.RESET}")
    except (ImportError, TypeError, ValueError):
        pass
    if not rewards["drops"]:
        print(f"{Color.WHITE}此战没有搜到额外战利品。{Color.RESET}")
    request_autosave(player)


def _combat_impl(player, enemy_name):
    from world_lifecycle import entity_state, record_death
    room_id = getattr(player, "location", None)
    state, corpse = entity_state(player, room_id, enemy_name, "enemy")
    if state != "alive":
        print(f"【{enemy_name}】已经倒下，暂时无法再次交战。")
        return
    e_data = get_enemy_profile(enemy_name, room_id)
    if not e_data:
        print(f"找不到关于【{enemy_name}】的战斗数据！")
        return
    world_pressure = apply_world_combat_pressure(e_data, player)

    e_hp, e_max_hp = e_data["hp"], e_data["hp"]
    e_atk, e_def = e_data["atk"], e_data["defense"]
    e_hit, e_crit, e_dodge = _enemy_combat_stats(e_data)

    # P2.5：所有战斗状态严格属于当前战斗，防止跨战斗泄漏。
    engine.clear_statuses()
    p_statuses = engine.p_statuses_global
    e_statuses = {}
    p_hit, p_crit, p_dodge = _player_combat_stats(player)

    battle_phase = 1
    phase_announced = set()
    # 招牌技能只在本场战斗内蓄力：逃跑、胜利或退出战斗函数后自然清理。
    pending_telegraph = None

    print(f"\n{Color.BRIGHT_RED}========== 战斗开始：{enemy_name} =========={Color.RESET}")
    print(f"敌人等级：{e_data.get("level", 1)} | 类型：{e_data.get("tier_label", "普通")} | 行为：{get_enemy_ai_style_label(e_data)} | 区域难度：{e_data.get("difficulty_label", "普通")}")
    worn = e_data.get("equipment", {})
    if isinstance(worn, dict) and worn:
        worn_text = "、".join(f"{slot_label}：{worn[slot]}" for slot, slot_label in (("weapon", "兵器"), ("armor", "护具")) if worn.get(slot))
        if worn_text:
            print(f"随身装备：{worn_text}")
    if e_data.get("skills"):
        skill_names = [str(sk.get("name")) for sk in e_data["skills"] if isinstance(sk, dict) and sk.get("name")]
        if skill_names:
            print(f"所习招式：{'、'.join(skill_names)}")
    if world_pressure > 0:
        print(f"世界战况：该势力压力 {world_pressure}，本场敌人进入强化状态。")
    if e_data.get("growth_levels", 0) > 0:
        print(f"区域成长：基础等级 {e_data.get("base_level", 1)} → 本场等级 {e_data.get("level", 1)}，属性已提升。")

    while player.hp > 0 and e_hp > 0:
        print("\n--------------------------------------------")
        print(f"{player.name}：气血 {draw_bar(player.hp, player.max_hp, fill_color=Color.RED)} "
              f"内力 {draw_bar(player.mp, player.max_mp, fill_color=Color.BLUE)}")
        print(f"{enemy_name}：气血 {draw_bar(e_hp, e_max_hp, fill_color=Color.BRIGHT_RED)}")
        print(f"自身状态：{format_statuses(p_statuses)} | 敌人状态：{format_statuses(e_statuses)}")

        p_dmg, p_stun, p_msgs = process_status_effects(p_statuses)
        e_dmg, e_stun, e_msgs = process_status_effects(e_statuses)
        player.hp = max(0, player.hp + p_dmg)
        e_hp = max(0, e_hp + e_dmg)

        for m in p_msgs: print(f"你：{m}")
        for m in e_msgs: print(f"{enemy_name}：{m}")

        if player.hp <= 0 or e_hp <= 0: break

        # P2.7：Boss 阶段检测只存在于当前战斗，不进入存档。
        new_phase = get_enemy_phase(e_data, e_hp, e_max_hp)
        if new_phase > battle_phase:
            battle_phase = new_phase
            ph = get_enemy_phase_data(e_data, battle_phase)
            phase_announced.add(battle_phase)
            msg = ph.get("message") or f"【{enemy_name}】进入第 {battle_phase} 阶段！"
            _emit(engine.style(msg, "phase"))
            heal_pct = max(0.0, float(ph.get("heal_percent", 0.0)))
            if heal_pct > 0:
                heal = max(1, int(e_max_hp * heal_pct))
                e_hp = min(e_max_hp, e_hp + heal)
                _emit(f"{enemy_name} 借势回气，恢复 {heal} 点气血！")

        # 玩家回合
        player_action_committed = True
        if not p_stun:
            # P2.1：只有“有效行动”才消耗一个战斗回合。
            # 非法指令、取消选择、物品/武学选择无效或内力不足时，重新选择，敌人不会趁机攻击。
            player_action_committed = False
            while not player_action_committed:
                print("\n行动选项：[1] 普通攻击  [2] 武学招式  [3] 使用物品  [4] 尝试逃跑")
                act = input(make_combat_prompt(player, enemy_name, e_hp, e_max_hp)).strip().lower()

                if act == "1":
                    phase_def_bonus = int(get_enemy_phase_data(e_data, battle_phase).get("defense_bonus", 0))
                    raw_dmg = calculate_damage(player.get_total_atk(), engine.get_effective_defense(e_def + phase_def_bonus, e_statuses))
                    dmg, outcome = resolve_attack(raw_dmg, p_hit, e_dodge, p_crit)
                    if outcome != "miss":
                        dmg = apply_damage_reduction(e_statuses, dmg)
                    if outcome == "miss":
                        print("你挥舞兵刃发起攻击，却被对方闪开了！")
                    elif outcome == "crit":
                        e_hp = max(0, e_hp - dmg)
                        print(f"{engine.style('会心一击！', 'crit')}你这一击造成 {dmg} 点暴击伤害！")
                    else:
                        e_hp = max(0, e_hp - dmg)
                        print(f"你挥舞兵刃发起攻击，造成 {dmg} 点伤害！")
                    for msg in apply_weapon_combat_effect(player, e_statuses, target_hit=outcome != "miss"):
                        _emit(engine.style(msg, "skill"))
                    player_action_committed = True

                elif act == "4":
                    if random.random() < 0.55:
                        print(f"{Color.GREEN}你拔腿施展轻功，成功摆脱敌人！{Color.RESET}")
                        engine.clear_statuses()
                        request_autosave(player)
                        return
                    print(f"{Color.RED}逃跑失败，被对方一把拦住去路！{Color.RESET}")
                    # 逃跑尝试本身消耗回合。
                    player_action_committed = True

                elif act == "3":
                    from actions import apply_consumable
                    consumables = [
                        i for i in list(dict.fromkeys(player.inventory))
                        if engine.ITEMS.get(i, {}).get("type") == "consumable"
                    ]
                    if not consumables:
                        print("行囊中无可用消耗品，请重新选择行动。")
                        continue

                    for idx, item in enumerate(consumables, 1):
                        print(f"  {idx}. {item}")
                    use_c = input("使用物品序号（0取消）：").strip()
                    if use_c == "0":
                        print("已取消使用物品，请重新选择行动。")
                        continue
                    if not use_c.isdigit() or not (0 < int(use_c) <= len(consumables)):
                        print("无效的物品序号，本回合未消耗行动。")
                        continue
                    item_name = consumables[int(use_c) - 1]
                    battle_item_context = {
                        "enemy_hp": e_hp,
                        "enemy_statuses": e_statuses,
                        "enemy_name": enemy_name,
                    }
                    if apply_consumable(player, item_name, battle_item_context):
                        e_hp = max(0, int(battle_item_context.get("enemy_hp", e_hp)))
                        player_action_committed = True
                    else:
                        print("该物品无法使用，请重新选择行动。")

                elif act == "2":
                    avail = player.get_available_skills()
                    if not avail:
                        print("当前没有可用武学，请重新选择行动。")
                        continue
                    for idx, sk in enumerate(avail, 1):
                        hint = f"；{sk.get('combat_hint')}" if sk.get('combat_hint') else ""
                        print(f"  {idx}. {sk['name']} (耗内 {sk['mp_cost']} / 威力 {int(sk['power']*100)}%){hint}")
                    sk_c = input("选择招式序号（0取消）：").strip()
                    if sk_c == "0":
                        print("已取消施展武学，请重新选择行动。")
                        continue
                    if not sk_c.isdigit() or not (0 < int(sk_c) <= len(avail)):
                        print("无效的招式序号，本回合未消耗行动。")
                        continue
                    sk = avail[int(sk_c) - 1]
                    if player.mp < sk["mp_cost"]:
                        print(f"{Color.RED}内力不足，无法施展【{sk['name']}】；本回合未消耗行动。{Color.RESET}")
                        continue
                    player.mp -= sk["mp_cost"]
                    # 仅有回气效果的招式（如基础吐纳）作为纯调息处理；带回气又有伤害的招式照常出招。
                    if has_skill_effect(sk, "mp_restore") and float(sk.get("power", 0) or 0) <= 0:
                        for msg in apply_skill_effect(sk, player, e_statuses):
                            _emit(engine.style(msg, "skill"))
                        progress = player.record_skill_use(sk["name"], True)
                        print(f"熟练度：{progress['mastery']}/{progress['mastery_max']}（武学等级 {progress['level']}）")
                        player_action_committed = True
                    else:
                        phase_def_bonus = int(get_enemy_phase_data(e_data, battle_phase).get("defense_bonus", 0))
                        raw_dmg = calculate_damage(player.get_total_atk(), engine.get_effective_defense(e_def + phase_def_bonus, e_statuses), sk["power"])
                        dmg, outcome = resolve_attack(
                            raw_dmg, p_hit, e_dodge, p_crit, float(sk.get("crit_bonus", 0.0))
                        )
                        if outcome != "miss":
                            dmg = apply_damage_reduction(e_statuses, dmg)
                        if outcome == "miss":
                            _emit(f"你一式【{sk['name']}】出手，却被对方闪开了！")
                        else:
                            e_hp = max(0, e_hp - dmg)
                            if outcome == "crit":
                                print(f"{engine.style('会心一击！', 'crit')}【{sk['name']}】造成 {dmg} 点暴击伤害！")
                            else:
                                print(f"你一式【{sk['name']}】轰出，造成 {dmg} 点伤害！")
                            if e_hp > 0:
                                for extra_dmg, extra_outcome in _combo_damage(raw_dmg, sk, p_hit, e_dodge, p_crit, float(sk.get("crit_bonus", 0.0))):
                                    if extra_outcome == "miss":
                                        _emit(f"【{sk['name']}】后续剑势被对方闪开！")
                                        continue
                                    extra_dmg = apply_damage_reduction(e_statuses, extra_dmg)
                                    e_hp = max(0, e_hp - extra_dmg)
                                    label = "暴击！" if extra_outcome == "crit" else "追加一击！"
                                    _emit(f"{label}【{sk['name']}】追加造成 {extra_dmg} 点伤害！")
                            for msg in apply_skill_effect(sk, player, e_statuses, target_hit=outcome != "miss"):
                                _emit(engine.style(msg, "skill"))
                            for msg in apply_weapon_combat_effect(player, e_statuses, target_hit=outcome != "miss"):
                                _emit(engine.style(msg, "skill"))
                            progress = player.record_skill_use(sk["name"], outcome != "miss")
                            if outcome != "miss":
                                print(f"熟练度：{progress['mastery']}/{progress['mastery_max']}（武学等级 {progress['level']}）")
                        player_action_committed = True

                else:
                    print(f"{Color.RED}无效行动：请输入 1、2、3 或 4。无效输入不消耗战斗回合。{Color.RESET}")

        # 玩家刚才的攻击可能直接跨过 Boss 阶段阈值；必须在敌人行动前立即切换。
        if e_hp > 0:
            new_phase = get_enemy_phase(e_data, e_hp, e_max_hp)
            if new_phase > battle_phase:
                battle_phase = new_phase
                ph = get_enemy_phase_data(e_data, battle_phase)
                phase_announced.add(battle_phase)
                msg = ph.get("message") or f"【{enemy_name}】进入第 {battle_phase} 阶段！"
                _emit(engine.style(msg, "phase"))
                heal_pct = max(0.0, float(ph.get("heal_percent", 0.0)))
                if heal_pct > 0:
                    heal = max(1, int(e_max_hp * heal_pct))
                    e_hp = min(e_max_hp, e_hp + heal)
                    _emit(f"{enemy_name} 借势回气，恢复 {heal} 点气血！")

        if e_hp <= 0:
            _finish_combat_victory(player, room_id, enemy_name, e_data)
            return

        # 敌人回合：玩家本回合刚施加的眩晕立即生效。
        e_stun_now = "stun" in e_statuses
        if not e_stun_now:
            from engine import add_status
            if pending_telegraph is not None:
                # 上一回合已经预警；本回合不再重新抽取技能，直接结算原技能伤害。
                e_skill = pending_telegraph
                pending_telegraph = None
                decision = {"action": "skill", "skill": e_skill}
            else:
                decision = choose_enemy_action(
                    e_data, e_hp, e_max_hp, player, p_statuses, battle_phase, e_statuses
                )
                e_skill = decision.get("skill") if decision.get("action") == "skill" else None
                if e_skill and is_telegraph_skill(e_skill):
                    pending_telegraph = e_skill
                    _emit(engine.style(telegraph_warning(enemy_name, e_skill), "warning"))
                    decision = {"action": "telegraph"}
                    e_skill = None
            if decision.get("action") == "guard":
                add_status(e_statuses, "damage_reduction", 2, int(decision.get("reduction", 25)))
                _emit(f"{engine.style(enemy_name, 'enemy')} 采取守势，下次受到的伤害降低 {decision.get('reduction', 25)}%。")
            elif e_skill:
                p_pwr = e_skill.get("power", 1.2)
                ph = get_enemy_phase_data(e_data, battle_phase)
                phase_atk_mult = max(0.1, float(ph.get("atk_mult", 1.0)))
                raw_dmg = calculate_damage(e_atk * phase_atk_mult, player.get_total_defense(), p_pwr)
                _emit(f"{engine.style(enemy_name, 'enemy')}施展出技能{engine.style('【' + e_skill['name'] + '】', 'skill')}！")
                dmg, outcome = resolve_attack(
                    raw_dmg, e_hit, p_dodge, e_crit, float(e_skill.get("crit_bonus", 0.0))
                )
                if outcome == "miss":
                    print(f"{enemy_name}的【{e_skill['name']}】被你闪开了！")
                else:
                    dmg = apply_damage_reduction(p_statuses, dmg)
                    dmg = apply_shield(p_statuses, dmg)
                    if dmg > 0:
                        player.hp = max(0, player.hp - dmg)
                        label = "暴击！" if outcome == "crit" else ""
                        print(f"{label}{enemy_name}的【{e_skill['name']}】对你造成 {Color.RED}{dmg}{Color.RESET} 点伤害！")
                        reflect = engine.apply_thorns(p_statuses, dmg)
                        if reflect > 0:
                            e_hp = max(0, e_hp - reflect)
                            _emit(engine.style(f"【反震】护体真劲将 {reflect} 点劲力震回{enemy_name}身上！", "warning"))
                if "effect" in e_skill and outcome != "miss":
                    add_status(p_statuses, e_skill["effect"], e_skill.get("turns", 2), e_skill.get("value", 3))
            elif decision.get("action") == "telegraph":
                pass
            else:
                ph = get_enemy_phase_data(e_data, battle_phase)
                phase_atk_mult = max(0.1, float(ph.get("atk_mult", 1.0)))
                raw_dmg = calculate_damage(e_atk * phase_atk_mult, player.get_total_defense())
                dmg, outcome = resolve_attack(raw_dmg, e_hit, p_dodge, e_crit)
                if outcome == "miss":
                    print(f"你侧身一闪，躲过了【{enemy_name}】的攻击！")
                else:
                    dmg = apply_damage_reduction(p_statuses, dmg)
                    dmg = apply_shield(p_statuses, dmg)
                    if dmg > 0:
                        player.hp = max(0, player.hp - dmg)
                        label = "暴击！" if outcome == "crit" else ""
                        print(f"{label}{enemy_name} 发起攻击，对你造成 {dmg} 点伤害！")
                        reflect = engine.apply_thorns(p_statuses, dmg)
                        if reflect > 0:
                            e_hp = max(0, e_hp - reflect)
                            _emit(engine.style(f"【反震】护体真劲将 {reflect} 点劲力震回{enemy_name}身上！", "warning"))
        else:
            _emit(f"{engine.style('【' + enemy_name + '】', 'enemy')}身中眩晕，脚步踉跄，本回合无法行动！")

        battle_pause(0.5)

    if player.hp <= 0:
        print(f"\n{Color.BRIGHT_RED}你重伤倒地，晕厥过去……热心村民将你抬回古庙养伤。{Color.RESET}")
        recovery_message = _defeat_recovery(player, "temple")
        from engine import clear_statuses
        clear_statuses()
        request_autosave(player)
        print(f"{Color.BRIGHT_YELLOW}{recovery_message}状态已清理。{Color.RESET}")
    elif e_hp <= 0:
        # 中毒、流血等持续伤害可能在回合开始时直接击倒敌人；也必须走完整胜利结算。
        _finish_combat_victory(player, room_id, enemy_name, e_data)


def combat(player, enemy_name):
    """战斗入口：标记战斗状态，结束后在安全场景补写挂起的自动存档。"""
    player._in_combat = True
    try:
        return _combat_impl(player, enemy_name)
    finally:
        player._in_combat = False
        flush_autosave = getattr(player, "flush_autosave", None)
        if callable(flush_autosave):
            try:
                flush_autosave()
            except (OSError, TypeError, ValueError):
                pass


def handle_attack(player, args):
    room = engine.ROOMS.get(player.location, {})
    from world_lifecycle import visible_enemies
    enemies, _ = visible_enemies(player, player.location, room.get("enemies", []))
    npcs = room.get("npcs", [])

    if not args:
        if enemies:
            combat(player, enemies[0])
            return True
        print("这里没有可以攻击的敌对目标。")
        return False

    target = args[0]
    for e in enemies:
        if target in e:
            combat(player, e)
            return True

    for n in npcs:
        if target in n:
            print(f"{Color.YELLOW}【{n}】并非可战之敌，不可胡乱出手！{Color.RESET}")
            return False

    print(f"未在此处找到目标【{target}】。")
    return False
