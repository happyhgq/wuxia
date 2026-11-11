# -*- coding: utf-8 -*-
"""
player.py - 玩家类、属性计算、经验成长与存档持久化
"""

import os
import json
import inspect
import tempfile
import engine
import npc_behavior
import npc_utility
import actor_display
from ui_output import safe_print as print
from world_time import world_hour

SAVE_PATH = engine.SAVE_PATH

# 自动存档按世界时刻节流：同一时刻内的多项结算只落盘一次，最多每 10 个时刻写一次。
AUTO_SAVE_INTERVAL_TICKS = 10


def request_autosave(player, verbose=True):
    """统一自动存档入口；只有真实玩家具备按 Tick 节流的 autosave。"""
    autosave = getattr(player, "autosave", None)
    if not callable(autosave):
        return player.save_to_file()
    try:
        parameters = inspect.signature(autosave).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_verbose = "verbose" in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )
    if accepts_verbose:
        return autosave(verbose=verbose)
    return autosave()


QUALITY_UPGRADE_TIERS = ("精良", "稀有", "史诗")


def get_quality_upgrade_cost(base_price, target_quality):
    """品质升阶消耗：目标品质越高、基础物品越贵，铁矿石与银两越多。"""
    try:
        base = max(0, int(base_price))
    except (TypeError, ValueError):
        base = 0
    if target_quality == "精良":
        return 3, max(80, base)
    if target_quality == "稀有":
        return 6, max(240, base * 2)
    if target_quality == "史诗":
        return 10, max(600, base * 3)
    return 0, 0



# Alpha285 成长节奏：Lv1–15 采用分阶段经验曲线，Lv16 起沿用 1.35 倍增长。
# 新表每一项均不低于旧表，旧存档载入后不会额外升级，V12 存档结构不变。
LEVEL_EXP_TABLE = (150, 185, 225, 275, 335, 410, 500, 610, 745, 910, 1110, 1500, 2000, 2650, 3500)


def exp_needed_for_level(level):
    """返回指定等级升到下一级所需的经验值。"""
    try:
        level = max(1, int(level))
    except (TypeError, ValueError, OverflowError):
        level = 1
    if level <= len(LEVEL_EXP_TABLE):
        return LEVEL_EXP_TABLE[level - 1]
    required = LEVEL_EXP_TABLE[-1]
    for _ in range(level - len(LEVEL_EXP_TABLE)):
        required = max(required + 1, int(required * 1.35))
    return required


def _safe_int_value(value, default=0, minimum=None, maximum=None):
    """把共用状态中的数值转成安全整数；布尔与异常字符串使用默认值。"""
    if isinstance(value, bool):
        value = default
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def normalize_follow_up(follow_up):
    """把情报的后续行动整理为 {npc, room, hint}；没有可行动目标时返回 None。"""
    if not isinstance(follow_up, dict):
        return None
    npc = str(follow_up.get("npc", "") or "").strip()
    room = str(follow_up.get("room", "") or "").strip()
    hint = str(follow_up.get("hint", "") or "").strip()
    if not npc and not room:
        return None
    result = {}
    if npc:
        result["npc"] = npc
    if room:
        result["room"] = room
    if hint:
        result["hint"] = hint
    return result


class Player:
    def __init__(self, name="无名侠客", sect="散人"):
        self.name = name
        self.sect = sect
        self.level = 1
        self.exp = 0
        self.exp_to_level = exp_needed_for_level(1)
        self.hp = 100
        self.max_hp = 100
        self.mp = 50
        self.max_mp = 50
        self.atk = 10
        self.defense = 5
        self.gold = 50
        self.inventory = ["疗伤药", "铁矿石", "草药"]
        # P3.2：背包容量采用物品格计数；旧 V12 存档不需要新增字段即可兼容。
        self.inventory_capacity = 100
        self.equipment = {"weapon": "木剑", "armor": "布衣"}
        self.equip_enhance = {"weapon": 0, "armor": 0}
        # P2.13：角色 Build 属性。旧 V12 存档缺失时按历史等级补发应得点数。
        self.attributes = {"strength": 0, "constitution": 0, "internal": 0, "agility": 0, "insight": 0}
        self.attribute_points = 0
        self.location = "village_gate"
        # 运行期战斗标记，仅用于阻止战斗中的自动存档，不写入 V12 存档。
        self._in_combat = False

        self.active_quests = {}
        self.quest_states = {}
        self.completed_quests = []
        self.world_state = {"flags": {}, "variables": {}}
        self.economy_state = {}
        # NPC 移动动态仅在当前运行会话中排队显示，不写入存档；按人物名去重，
        # 同一时段同一人物的多次移动只保留最后一条。
        self._pending_npc_movement_messages = {}
        # 与文本平行的结构化信息，供世界播报按同方向、同出口合并同类移动。
        self._pending_npc_movement_details = {}

        if sect == "少林":
            self.max_hp += 20; self.hp += 20; self.defense += 3
        elif sect == "武当":
            self.max_mp += 20; self.mp += 20; self.atk += 2
        elif sect == "华山":
            self.atk += 5
        self._ensure_sect_state()
        self._ensure_skill_state()
        current_skills = engine.SKILLS.get(self.get_sect(), []) or []
        for skill in current_skills:
            if isinstance(skill, dict) and int(skill.get("learn_min_reputation", 0)) == 0 and int(skill.get("learn_min_rank", 0)) == 0 and self.level >= int(skill.get("level", 1)):
                self._skill_state()[skill.get("name", "")]["learned"] = True
                self._skill_state()[skill.get("name", "")]["mastery"] = max(1, int(self._skill_state()[skill.get("name", "")].get("mastery", 0)))

    # P3.1.3：江湖路线倾向。数据写入既有 V12 world_state.variables，不新增存档顶层字段。
    JIANGHU_PATHS = ("侠客", "官府", "商会", "黑市", "独行")

    def _jianghu_profile(self):
        variables = self.world_state.setdefault("variables", {})
        profile = variables.get("jianghu_profile")
        if not isinstance(profile, dict):
            profile = {}
        raw_paths = profile.get("paths", {})
        paths = {}
        for name in self.JIANGHU_PATHS:
            try:
                paths[name] = max(0, min(100, int(raw_paths.get(name, 0)))) if isinstance(raw_paths, dict) else 0
            except (TypeError, ValueError):
                paths[name] = 0
        try:
            honor = max(0, int(profile.get("honor", 0)))
        except (TypeError, ValueError):
            honor = 0
        try:
            infamy = max(0, int(profile.get("infamy", 0)))
        except (TypeError, ValueError):
            infamy = 0
        profile = {"title": str(profile.get("title", "无名侠客")), "honor": honor, "infamy": infamy, "paths": paths}
        variables["jianghu_profile"] = profile
        return profile

    PLAYER_PROFILE_DEFAULTS = {"gender": "male", "age_desc": "二十来岁", "face_attire": ""}

    def get_player_profile(self):
        """读取玩家形貌档案；旧 V12 存档没有该字段时使用默认值。"""
        world_state = getattr(self, "world_state", {})
        variables = world_state.get("variables", {}) if isinstance(world_state, dict) else {}
        raw = variables.get("player_profile") if isinstance(variables, dict) else None
        if not isinstance(raw, dict):
            raw = {}
        gender = str(raw.get("gender", "")).strip().lower()
        if gender not in ("male", "female", "neutral"):
            gender = self.PLAYER_PROFILE_DEFAULTS["gender"]
        age_desc = str(raw.get("age_desc", "")).strip() or self.PLAYER_PROFILE_DEFAULTS["age_desc"]
        face_attire = str(raw.get("face_attire", "")).strip()
        return {"gender": gender, "age_desc": age_desc, "face_attire": face_attire}

    def set_player_profile(self, gender=None, age_desc=None, face_attire=None):
        """写入玩家形貌档案；只改既有 world_state.variables，不新增存档顶层字段。"""
        profile = self.get_player_profile()
        if gender is not None:
            gender = str(gender).strip().lower()
            if gender in ("male", "female", "neutral"):
                profile["gender"] = gender
        if age_desc is not None:
            age_desc = str(age_desc).strip()
            if age_desc:
                profile["age_desc"] = age_desc
        if face_attire is not None:
            profile["face_attire"] = str(face_attire).strip()
        variables = self.world_state.setdefault("variables", {})
        variables["player_profile"] = profile
        return True

    def record_jianghu_action(self, action, amount=1):
        """根据明确的玩家行为累计路线倾向；未知行为不产生影响。"""
        action_map = {
            "help_people": {"侠客": 5}, "rescue_npc": {"侠客": 4},
            "assist_officials": {"官府": 5, "侠客": 1},
            "escort_trade": {"商会": 5, "侠客": 2},
            "black_market_trade": {"黑市": 5},
            "refuse_factions": {"独行": 4}, "solo_explore": {"独行": 2},
        }
        deltas = action_map.get(str(action))
        if not deltas:
            return False
        try:
            scale = max(1, min(5, int(amount)))
        except (TypeError, ValueError):
            scale = 1
        profile = self._jianghu_profile()
        for path, delta in deltas.items():
            profile["paths"][path] = min(100, profile["paths"].get(path, 0) + delta * scale)
        return True

    def get_jianghu_path_summary(self):
        profile = self._jianghu_profile()
        paths = profile["paths"]
        ranked = sorted(paths.items(), key=lambda item: (-item[1], self.JIANGHU_PATHS.index(item[0])))
        top_name, top_value = ranked[0]
        second_value = ranked[1][1]
        if top_value < 10:
            current = "尚未形成"
        elif top_value - second_value < 5:
            current = "多方兼顾"
        else:
            current = f"{top_name}倾向"
        return {"paths": dict(paths), "current": current}

    def add_jianghu_reputation(self, honor=0, infamy=0):
        """统一调整侠名/恶名，并限制数值下界，兼容旧 V12 存档。"""
        profile = self._jianghu_profile()
        try:
            profile["honor"] = max(0, min(9999, profile["honor"] + int(honor)))
            profile["infamy"] = max(0, min(9999, profile["infamy"] + int(infamy)))
        except (TypeError, ValueError):
            return False
        return True

    def get_jianghu_identity_title(self):
        """依据名声与主要行为倾向给出动态身份称号，不覆盖门派身份。"""
        profile = self._jianghu_profile()
        paths = profile["paths"]
        honor, infamy = profile["honor"], profile["infamy"]
        dominant = max(paths, key=lambda name: (paths[name], -self.JIANGHU_PATHS.index(name)))
        value = paths[dominant]
        if infamy >= 100:
            return "凶名在外之人"
        if infamy >= 50:
            return "江湖危险人物"
        if dominant == "官府" and value >= 20:
            return "官府协力之人"
        if dominant == "商会" and value >= 20:
            return "护商义士"
        if dominant == "黑市" and value >= 20:
            return "黑市行者"
        if dominant == "独行" and value >= 20:
            return "独行游侠"
        if dominant == "侠客" and honor >= 100 and value >= 20:
            return "一方豪侠"
        if dominant == "侠客" and honor >= 50 and value >= 15:
            return "地方侠客"
        if honor >= 10:
            return "略有善名之人"
        return "无名侠客"

    def get_jianghu_npc_reaction(self):
        """返回供 NPC 对话使用的简短名声反应；未达门槛时不额外插话。"""
        profile = self._jianghu_profile()
        honor, infamy = profile["honor"], profile["infamy"]
        if infamy >= 50:
            return "听闻你凶名在外，对方下意识与你保持距离。"
        if infamy >= 20 and infamy > honor:
            return "对方听过一些关于你的负面传闻，言语间多了几分戒备。"
        if honor >= 50 and infamy >= 20:
            return "对方听闻你既有侠义善举，也背着一些恶名，态度敬重中带着戒心。"
        if honor >= 50:
            return "对方似乎听过你的善举，称呼间多了几分敬意。"
        if honor >= 20:
            return "对方听说过你做过的好事，态度略显亲切。"
        return ""

    def apply_jianghu_effects(self, effects):
        """应用 NPC/剧情配置的江湖效果；未配置相关字段时保持原行为。"""
        if not isinstance(effects, dict):
            return False
        changed = False
        action = effects.get("jianghu_action")
        if action:
            changed = self.record_jianghu_action(action, effects.get("jianghu_amount", 1)) or changed
        if "honor_delta" in effects or "infamy_delta" in effects:
            changed = self.add_jianghu_reputation(effects.get("honor_delta", 0), effects.get("infamy_delta", 0)) or changed
        return changed

    def get_jianghu_reputation_labels(self):
        profile = self._jianghu_profile()
        honor, infamy = profile["honor"], profile["infamy"]
        honor_label = "默默无闻" if honor < 10 else "略有善名" if honor < 50 else "江湖侠客" if honor < 100 else "一代豪侠"
        infamy_label = "清白之身" if infamy == 0 else "行迹可疑" if infamy < 10 else "危险人物" if infamy < 50 else "凶名在外" if infamy < 100 else "魔道巨擘"
        return honor_label, infamy_label

    def inventory_count(self, item_name):
        """返回背包中指定物品数量。"""
        return self.inventory.count(item_name)

    def remove_inventory_items(self, item_name, quantity=1):
        """从背包原子移除指定数量；数量不足时不修改背包。"""
        quantity = int(quantity)
        if quantity < 1:
            return False
        if self.inventory.count(item_name) < quantity:
            return False
        for _ in range(quantity):
            self.inventory.remove(item_name)
        return True

    def get_equipment_stats(self, slot):
        """返回指定装备槽的基础属性、强化等级和词条加成。

        slot 仅接受 weapon / armor / accessory；未知槽位返回空字典，避免 UI 或
        旧存档数据异常时中断游戏。饰品不参与强化。P2.14 的词条完全由
        items.json 驱动，不写入存档。
        """
        if slot not in ("weapon", "armor", "accessory"):
            return {}
        item_name = self.equipment.get(slot)
        if not item_name:
            return {"name": None, "slot": slot, "enhance": 0, "atk": 0, "defense": 0}
        info = engine.ITEMS.get(item_name, {})
        weapon_effect = info.get("weapon_effect") if isinstance(info, dict) else None
        if slot == "weapon" and not isinstance(weapon_effect, dict):
            base_name = info.get("base_item") if isinstance(info, dict) else None
            base_info = engine.ITEMS.get(base_name, {}) if base_name else {}
            weapon_effect = base_info.get("weapon_effect") if isinstance(base_info, dict) else None
        enhance = max(0, int(self.equip_enhance.get(slot, 0)))
        enhance_atk = enhance * 3 if slot == "weapon" else 0
        enhance_def = enhance * 2 if slot == "armor" else 0
        return {
            "name": item_name,
            "slot": slot,
            "enhance": enhance,
            "atk": int(info.get("atk", 0)) + enhance_atk,
            "defense": int(info.get("defense", 0)) + enhance_def,
            "base_atk": int(info.get("atk", 0)),
            "base_defense": int(info.get("defense", 0)),
            "price": int(info.get("price", 0)),
            "desc": info.get("desc", ""),
            "quality": info.get("quality", "普通"),
            "base_item": info.get("base_item", item_name),
            "affix_count": int(info.get("affix_count", 0)),
            "enhance_max": max(0, int(info.get("enhance_max", 5))),
            "enhance_ore_cost": max(1, int(info.get("enhance_ore_cost", 1))),
            "enhance_gold_cost": max(0, int(info.get("enhance_gold_cost", 30))),
            "accuracy_bonus": float(info.get("accuracy_bonus", 0.0)),
            "crit_bonus": float(info.get("crit_bonus", 0.0)),
            "dodge_bonus": float(info.get("dodge_bonus", 0.0)),
            "attribute_bonus": dict(info.get("attribute_bonus", {})) if isinstance(info.get("attribute_bonus", {}), dict) else {},
            "weapon_effect": dict(weapon_effect) if isinstance(weapon_effect, dict) else {},
        }

    def get_enhancement_preview(self, slot):
        """返回当前装备下一次强化的完整预览，不修改任何状态。

        该 API 专门供终端 UI、测试及未来自动化界面使用；强化仍由
        actions.handle_forge 执行，因此预览不会产生材料/银两副作用。
        """
        if slot not in ("weapon", "armor"):
            return {}
        info = self.get_equipment_stats(slot)
        if not info.get("name"):
            return {"slot": slot, "available": False, "reason": "empty"}
        current = max(0, int(info.get("enhance", 0)))
        maximum = max(0, int(info.get("enhance_max", 5)))
        if current >= maximum:
            return {
                "slot": slot, "available": False, "reason": "max",
                "name": info["name"], "current_level": current,
                "max_level": maximum, "ore_cost": info.get("enhance_ore_cost", 1),
                "gold_cost": info.get("enhance_gold_cost", 30),
                "current_stat": info.get("atk", 0) if slot == "weapon" else info.get("defense", 0),
            }
        stat_key = "atk" if slot == "weapon" else "defense"
        per_level = 3 if slot == "weapon" else 2
        current_stat = int(info.get(stat_key, 0))
        next_stat = current_stat + per_level
        return {
            "slot": slot, "available": True, "name": info["name"],
            "current_level": current, "next_level": current + 1, "max_level": maximum,
            "stat_key": stat_key, "current_stat": current_stat,
            "next_stat": next_stat, "stat_delta": per_level,
            "ore_cost": int(info.get("enhance_ore_cost", 1)),
            "gold_cost": int(info.get("enhance_gold_cost", 30)),
            "quality": info.get("quality", "普通"),
        }

    def get_quality_upgrade_preview(self, slot):
        """返回当前装备下一次品质升阶的预览，不修改任何状态。

        品质链取自基础物品的 quality_variants：普通 → 精良 → 稀有 → 史诗，
        缺档时自动跳到下一档（如玄铁重剑直接从普通升稀有）。强化等级保留。
        """
        if slot not in ("weapon", "armor"):
            return {}
        item_name = self.equipment.get(slot)
        if not item_name:
            return {"slot": slot, "available": False, "reason": "empty"}
        info = engine.ITEMS.get(item_name, {})
        if not isinstance(info, dict) or info.get("type") not in ("weapon", "armor"):
            return {"slot": slot, "available": False, "reason": "invalid", "name": item_name}
        base_name = info.get("base_item") or item_name
        base_info = engine.ITEMS.get(base_name, {})
        variants = base_info.get("quality_variants", {}) if isinstance(base_info, dict) else {}
        if not isinstance(variants, dict) or not variants:
            return {"slot": slot, "available": False, "reason": "no_variant", "name": item_name}
        order = ("精良", "稀有", "史诗")
        current_quality = info.get("quality", "普通")
        try:
            start = order.index(current_quality) + 1
        except ValueError:
            start = 0
        next_quality = next(
            (quality for quality in order[start:] if variants.get(quality) in engine.ITEMS), None
        )
        if not next_quality:
            return {
                "slot": slot, "available": False, "reason": "max",
                "name": item_name, "quality": current_quality,
            }
        next_item = variants[next_quality]
        next_info = engine.ITEMS[next_item]
        stat_key = "atk" if slot == "weapon" else "defense"
        per_level = 3 if slot == "weapon" else 2
        enhance = max(0, int(self.equip_enhance.get(slot, 0)))
        current_stat = int(info.get(stat_key, 0)) + enhance * per_level
        next_stat = int(next_info.get(stat_key, 0)) + enhance * per_level
        ore_cost, gold_cost = get_quality_upgrade_cost(
            base_info.get("price", info.get("price", 0)), next_quality
        )
        return {
            "slot": slot, "available": True, "name": item_name,
            "quality": current_quality, "next_quality": next_quality,
            "next_item": next_item, "stat_key": stat_key,
            "current_stat": current_stat, "next_stat": next_stat,
            "stat_delta": next_stat - current_stat,
            "ore_cost": ore_cost, "gold_cost": gold_cost,
            "enhance": enhance,
            "enhance_max": int(next_info.get("enhance_max", 5)),
        }

    def get_equipment_power_breakdown(self, slot):
        """返回装备基础属性与强化贡献，便于明确解释最终数值来源。"""
        info = self.get_equipment_stats(slot)
        if not info.get("name"):
            return {}
        if slot == "weapon":
            return {
                "name": info["name"], "quality": info.get("quality", "普通"),
                "enhance": info.get("enhance", 0), "base": info.get("base_atk", 0),
                "enhance_bonus": info.get("atk", 0) - info.get("base_atk", 0),
                "total": info.get("atk", 0),
            }
        return {
            "name": info["name"], "quality": info.get("quality", "普通"),
            "enhance": info.get("enhance", 0), "base": info.get("base_defense", 0),
            "enhance_bonus": info.get("defense", 0) - info.get("base_defense", 0),
            "total": info.get("defense", 0),
        }

    def get_equipment_affixes(self):
        """汇总当前装备的 P2.14 词条，不改变存档结构。"""
        totals = {"accuracy_bonus": 0.0, "crit_bonus": 0.0, "dodge_bonus": 0.0,
                  "attribute_bonus": {k: 0 for k in self.attributes}}
        for slot in ("weapon", "armor", "accessory"):
            info = self.get_equipment_stats(slot)
            totals["accuracy_bonus"] += info.get("accuracy_bonus", 0.0)
            totals["crit_bonus"] += info.get("crit_bonus", 0.0)
            totals["dodge_bonus"] += info.get("dodge_bonus", 0.0)
            for key, value in info.get("attribute_bonus", {}).items():
                if key in totals["attribute_bonus"]:
                    try:
                        totals["attribute_bonus"][key] += int(value)
                    except (TypeError, ValueError):
                        pass
        return totals

    def get_effective_attribute(self, name):
        """角色面板属性 + 装备词条属性；基础存档属性本身保持不变。"""
        base = self.get_attribute(name)
        bonus = self.get_equipment_affixes()["attribute_bonus"].get(name, 0)
        return base + bonus

    def _evaluate_build_profiles(self, equipment=None):
        """按当前/指定装备与有效属性评估 Build 流派；纯计算，不修改存档。"""
        equipment = equipment or self.equipment
        results = []
        for name, profile in getattr(engine, "BUILD_PROFILES", {}).items():
            required = profile.get("required", {}) or {}
            ok = True
            weapon_base = required.get("weapon_base")
            armor_base = required.get("armor_base")
            if weapon_base:
                weapon_name = equipment.get("weapon")
                weapon_info = engine.ITEMS.get(weapon_name, {}) if weapon_name else {}
                if weapon_info.get("base_item", weapon_name) != weapon_base:
                    ok = False
            if armor_base:
                armor_name = equipment.get("armor")
                armor_info = engine.ITEMS.get(armor_name, {}) if armor_name else {}
                if armor_info.get("base_item", armor_name) != armor_base:
                    ok = False
            # Build 预览可能传入候选装备；属性门槛必须按候选装备计算，
            # 不能误用角色当前装备的词条，否则会出现“换装预览仍显示旧流派”或
            # “候选装备明明补足属性却无法激活流派”的情况。
            candidate_attributes = dict(self.attributes)
            for candidate_slot in ("weapon", "armor"):
                candidate_name = equipment.get(candidate_slot)
                candidate_info = engine.ITEMS.get(candidate_name, {}) if candidate_name else {}
                candidate_bonus = candidate_info.get("attribute_bonus", {}) if isinstance(candidate_info, dict) else {}
                if isinstance(candidate_bonus, dict):
                    for attr_name, value in candidate_bonus.items():
                        try:
                            candidate_attributes[attr_name] = int(candidate_attributes.get(attr_name, 0)) + int(value)
                        except (TypeError, ValueError, OverflowError):
                            continue
            for attr, minimum in (required.get("attributes", {}) or {}).items():
                try:
                    effective_value = int(candidate_attributes.get(attr, 0))
                    required_value = int(minimum)
                except (TypeError, ValueError, OverflowError):
                    ok = False
                    continue
                if effective_value < required_value:
                    ok = False
            if ok:
                bonuses = dict(profile.get("bonuses", {}) or {})
                results.append({
                    "name": name,
                    "description": profile.get("description", ""),
                    "bonuses": bonuses,
                    "score": sum(int(v) for v in (required.get("attributes", {}) or {}).values())
                })
        results.sort(key=lambda x: (x["score"], x["name"]), reverse=True)
        return results

    def get_active_build(self):
        """返回当前激活流派；未满足条件时返回 None。"""
        profiles = self._evaluate_build_profiles()
        return profiles[0] if profiles else None

    def get_build_bonuses(self):
        """汇总当前流派战斗加成；Build 加成不写入存档。"""
        active = self.get_active_build()
        bonuses = {"atk": 0, "defense": 0, "hit_bonus": 0.0, "crit_bonus": 0.0, "dodge_bonus": 0.0}
        if active:
            for key in bonuses:
                if key in active.get("bonuses", {}):
                    value = active["bonuses"][key]
                    bonuses[key] = int(value) if key in ("atk", "defense") else float(value)
        return bonuses

    def get_build_preview_for_item(self, item_name):
        """计算换上指定背包装备后的流派变化，不实际换装。"""
        info = engine.ITEMS.get(item_name, {})
        slot = info.get("type")
        if slot not in ("weapon", "armor", "accessory"):
            return None
        candidate = dict(self.equipment)
        candidate[slot] = item_name
        before = self.get_active_build()
        candidates = self._evaluate_build_profiles(candidate)
        after = candidates[0] if candidates else None
        return {
            "before": before,
            "after": after,
            "changed": (before or {}).get("name") != (after or {}).get("name")
        }

    def get_equipment_score(self, item_name, include_current_enhance=False):
        """计算装备综合评分；仅用于比较/推荐，不直接参与战斗公式。"""
        info = engine.ITEMS.get(item_name, {})
        if info.get("type") not in ("weapon", "armor", "accessory"):
            return 0
        quality_weight = {"普通": 0, "精良": 8, "稀有": 18, "史诗": 30}
        score = quality_weight.get(info.get("quality", "普通"), 0)
        slot = info.get("type")
        base_stat = int(info.get("atk", 0)) if slot == "weapon" else int(info.get("defense", 0))
        score += base_stat * (2 if slot == "weapon" else 2)
        aff = {
            "accuracy_bonus": float(info.get("accuracy_bonus", 0.0)),
            "crit_bonus": float(info.get("crit_bonus", 0.0)),
            "dodge_bonus": float(info.get("dodge_bonus", 0.0)),
            "attribute_bonus": info.get("attribute_bonus", {}) if isinstance(info.get("attribute_bonus", {}), dict) else {},
        }
        score += round((aff["accuracy_bonus"] + aff["crit_bonus"] + aff["dodge_bonus"]) * 100)
        attr_weights = {"strength": 4, "constitution": 4, "internal": 3, "agility": 3, "insight": 3}
        for key, value in aff["attribute_bonus"].items():
            try:
                score += int(value) * attr_weights.get(key, 1)
            except (TypeError, ValueError):
                pass
        if include_current_enhance:
            current = self.equipment.get(slot)
            if current == item_name:
                score += int(self.equip_enhance.get(slot, 0)) * (6 if slot == "weapon" else 4)
        preview = self.get_build_preview_for_item(item_name)
        if preview and preview.get("after"):
            score += 10
            before_build = preview.get("before") or {}
            after_build = preview.get("after") or {}
            if before_build.get("name") == after_build.get("name"):
                score += 5
        return max(0, int(score))

    def evaluate_equipment(self, item_name):
        """返回掉落装备的可读价值评估；不修改装备、背包或存档。"""
        info = engine.ITEMS.get(item_name, {})
        if info.get("type") not in ("weapon", "armor", "accessory"):
            return None
        slot = info["type"]
        current_name = self.equipment.get(slot)
        current_score = self.get_equipment_score(current_name, True) if current_name else 0
        candidate_score = self.get_equipment_score(item_name, False)
        preview = self.get_build_preview_for_item(item_name)
        delta = candidate_score - current_score
        recommendation = "upgrade" if delta > 0 else ("sidegrade" if delta == 0 else "downgrade")
        if preview and preview.get("after") and preview.get("after", {}).get("name") != (preview.get("before") or {}).get("name"):
            recommendation = "build_upgrade" if delta >= 0 else "build_tradeoff"
        return {
            "item": item_name,
            "slot": slot,
            "quality": info.get("quality", "普通"),
            "score": candidate_score,
            "current_item": current_name,
            "current_score": current_score,
            "score_delta": delta,
            "recommendation": recommendation,
            "build_before": (preview or {}).get("before"),
            "build_after": (preview or {}).get("after"),
        }

    def compare_equipment(self, item_name):
        """比较背包中的装备与当前同槽装备，返回可供终端 UI 使用的数据。"""
        info = engine.ITEMS.get(item_name, {})
        slot = info.get("type")
        if slot not in ("weapon", "armor", "accessory"):
            return None
        current = self.get_equipment_stats(slot)
        candidate_atk = int(info.get("atk", 0))
        candidate_def = int(info.get("defense", 0))
        candidate_affixes = {
            "accuracy_bonus": float(info.get("accuracy_bonus", 0.0)),
            "crit_bonus": float(info.get("crit_bonus", 0.0)),
            "dodge_bonus": float(info.get("dodge_bonus", 0.0)),
            "attribute_bonus": dict(info.get("attribute_bonus", {})) if isinstance(info.get("attribute_bonus", {}), dict) else {},
        }
        return {
            "item": item_name,
            "slot": slot,
            "current": current,
            "candidate_atk": candidate_atk,
            "candidate_defense": candidate_def,
            "delta_atk": candidate_atk - current.get("atk", 0),
            "delta_defense": candidate_def - current.get("defense", 0),
            "candidate_affixes": candidate_affixes,
            "quality": info.get("quality", "普通"),
            "base_item": info.get("base_item", item_name),
            "affix_count": int(info.get("affix_count", 0)),
            "price": int(info.get("price", 0)),
            "candidate_score": self.get_equipment_score(item_name, False),
            "current_score": self.get_equipment_score(current.get("name"), True) if current.get("name") else 0,
        }

    def equip_item(self, item_name):
        """装备背包中的武器/防具/饰品；返回 (success, message)。"""
        if item_name not in self.inventory:
            return False, f"你的背包里没有【{item_name}】。"
        info = engine.ITEMS.get(item_name, {})
        item_type = info.get("type")
        if item_type in ("weapon", "armor"):
            slot = item_type
        elif item_type == "accessory" and info.get("slot") == "accessory":
            slot = "accessory"
        else:
            return False, f"【{item_name}】不是可装备的武器、防具或饰品。"
        old = self.equipment.get(slot)
        if old:
            self.inventory.append(old)
        self.inventory.remove(item_name)
        self.equipment[slot] = item_name
        # 保持 V12 原有“换装后该槽强化等级归零”的行为，避免改变旧存档语义。
        if slot in ("weapon", "armor"):
            self.equip_enhance[slot] = 0
        label = {"weapon": "武器", "armor": "防具", "accessory": "饰品"}[slot]
        return True, f"装备了{label}：【{item_name}】！"

    def unequip_item(self, slot):
        """卸下指定装备槽；不改变 V12 存档结构。"""
        if slot not in ("weapon", "armor", "accessory"):
            return False, "只能卸下 weapon/armor/accessory 装备槽。"
        item_name = self.equipment.get(slot)
        if not item_name:
            label = {"weapon": "武器", "armor": "防具", "accessory": "饰品"}[slot]
            return False, f"当前没有装备{label}。"
        self.inventory.append(item_name)
        self.equipment[slot] = None
        if slot in ("weapon", "armor"):
            self.equip_enhance[slot] = 0
        return True, f"已卸下【{item_name}】。"

    def get_total_atk(self):
        w_name = self.equipment.get("weapon")
        base = engine.ITEMS.get(w_name, {}).get("atk", 0) if w_name else 0
        enhance_bonus = self.equip_enhance.get("weapon", 0) * 3
        return self.atk + self.get_effective_attribute("strength") * 2 + base + enhance_bonus + self.get_build_bonuses()["atk"]

    def get_total_defense(self):
        a_name = self.equipment.get("armor")
        base = engine.ITEMS.get(a_name, {}).get("defense", 0) if a_name else 0
        enhance_bonus = self.equip_enhance.get("armor", 0) * 2
        accessory_name = self.equipment.get("accessory")
        accessory_defense = engine.ITEMS.get(accessory_name, {}).get("defense", 0) if accessory_name else 0
        return self.defense + self.get_effective_attribute("constitution") + base + enhance_bonus + accessory_defense + self.get_build_bonuses()["defense"]

    def get_attribute(self, name):
        return int(self.attributes.get(name, 0))

    # ==================== P2.23 门派系统 ====================
    def _sect_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("sect_state", {})
        if not isinstance(state, dict):
            state = {}
            variables["sect_state"] = state
        return state

    def _ensure_sect_state(self):
        state = self._sect_state()
        current = state.get("current_sect")
        if not isinstance(current, str) or current not in engine.SECTS:
            current = self.sect if self.sect in engine.SECTS else "散人"
            state["current_sect"] = current
        rep = state.setdefault("reputation", {})
        if not isinstance(rep, dict):
            rep = {}
            state["reputation"] = rep
        for sect_name, info in engine.SECTS.items():
            if sect_name not in rep:
                try:
                    rep[sect_name] = int(info.get("initial_reputation", 0))
                except (TypeError, ValueError):
                    rep[sect_name] = 0
        return state

    def get_sect(self):
        state = self._ensure_sect_state()
        return state.get("current_sect", self.sect)

    def get_sect_reputation(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        state = self._ensure_sect_state()
        try:
            return int(state.get("reputation", {}).get(sect_name, 0))
        except (TypeError, ValueError):
            return 0

    def get_sect_rank(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        info = engine.SECTS.get(sect_name, {})
        ranks = info.get("ranks", []) or []
        rep = self.get_sect_reputation(sect_name)
        current = ranks[0] if ranks else {"name": "散人", "min_reputation": 0}
        for rank in ranks:
            try:
                if rep >= int(rank.get("min_reputation", 0)):
                    current = rank
            except (TypeError, ValueError):
                continue
        return current.get("name", "散人")

    def change_sect_reputation(self, sect_name, delta):
        if sect_name not in engine.SECTS:
            return 0
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return self.get_sect_reputation(sect_name)
        state = self._ensure_sect_state()
        rep = state.setdefault("reputation", {})
        old = self.get_sect_reputation(sect_name)
        rep[sect_name] = max(-1000, min(1000, old + delta))
        return rep[sect_name]

    def _sect_progress_state(self):
        state = self._ensure_sect_state()
        progress = state.setdefault("progress", {})
        if not isinstance(progress, dict):
            progress = {}
            state["progress"] = progress
        return progress

    def get_sect_mentorship(self, sect_name=None):
        """读取门派师承记录；保存在现有 V12 world_state.variables 中。"""
        sect_name = sect_name or self.get_sect()
        progress = self._sect_progress_state()
        record = progress.get(sect_name, {})
        if not isinstance(record, dict):
            return {}
        mentorship = record.get("mentorship", {})
        return mentorship if isinstance(mentorship, dict) else {}

    def establish_sect_mentorship(self, mentor_name=None, sect_name=None):
        sect_name = sect_name or self.get_sect()
        if sect_name != self.get_sect() or sect_name == "散人":
            return False, "只有本门弟子才能建立师承关系。"
        # 师承必须与当前门派匹配，不能借其他门派的师长建立错误身份记录。
        training = (engine.SECTS.get(sect_name, {}) or {}).get("training", {}) or {}
        expected_mentor = training.get("lesson_teacher") or {
            "少林": "少林传功师父",
            "武当": "武当传功师父",
            "华山": "华山授业师父",
            "铁衣门": "铁衣门传功师父",
        }.get(sect_name)
        if not expected_mentor:
            return False, "当前门派尚未设置正式授业师长。"
        mentor_name = mentor_name or expected_mentor
        if mentor_name != expected_mentor:
            return False, f"【{sect_name}】弟子应向本门授业师长【{expected_mentor}】行礼，不能建立其他门派的师承。"
        if mentor_name not in engine.NPCS:
            return False, "没有找到这位授业师长。"
        existing = self.get_sect_mentorship(sect_name)
        if existing.get("mentor"):
            if existing.get("mentor") == mentor_name:
                return False, f"你已拜【{mentor_name}】为师，无需重复行礼。"
            return False, "你已有正式师承；如需更换师承，须先完成门派认可的转师流程。"
        progress = self._sect_progress_state()
        record = progress.setdefault(sect_name, {})
        record["mentorship"] = {"mentor": mentor_name, "bond": 0, "lessons": 0, "established": True}
        self.change_relation(mentor_name, 10)
        return True, f"你向【{mentor_name}】行拜师礼，正式建立师承关系。师父嘱你先打牢基础，再求武学精进。"

    def record_mentorship_lesson(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        # 防止旧存档残留或内部调用参数错误，让玩家在非本门身份下推进其他门派师承。
        if sect_name != self.get_sect() or sect_name == "散人":
            return False, "只有当前门派的正式弟子，才能接受本门师长指点。"
        record = self._sect_progress_state().get(sect_name, {})
        mentorship = record.get("mentorship", {}) if isinstance(record, dict) else {}
        training = (engine.SECTS.get(sect_name, {}) or {}).get("training", {}) or {}
        expected_mentor = training.get("lesson_teacher") or {
            "少林": "少林传功师父",
            "武当": "武当传功师父",
            "华山": "华山授业师父",
            "铁衣门": "铁衣门传功师父",
        }.get(sect_name)
        if not isinstance(mentorship, dict) or not mentorship.get("mentor"):
            return False, "你尚未建立师承关系。"
        if not expected_mentor or mentorship.get("mentor") != expected_mentor:
            return False, "师承记录与当前门派不一致，暂不能接受指点；请先核实本门师承。"
        # 防止反复输入命令刷取师门默契与声望：同一世界时钟内只能请教一次，
        # 两次有效请教至少间隔 3 个世界 Tick。冷却记录复用现有师承字典。
        now = self.get_quest_clock()
        last = mentorship.get("last_lesson_clock")
        if last is not None:
            try:
                elapsed = now - int(last)
            except (TypeError, ValueError):
                elapsed = 3
            if elapsed < 3:
                return False, f"师父让你先自行练习、体会方才所授招式；还需经过 {3 - max(0, elapsed)} 个世界时刻，才能再次请教。"
        # 指点内容与弟子当前实际掌握的本门武学关联，避免每次请教都得到相同的空泛反馈。
        sect_info = engine.SECTS.get(sect_name, {}) or {}
        sect_skills = list(sect_info.get("exclusive_skills", []) or [])
        known = []
        for skill_name in sect_skills:
            skill_progress = self.get_skill_progress(skill_name)
            if skill_progress.get("learned"):
                known.append((skill_progress.get("mastery", 0), skill_name, skill_progress))
        if known:
            known.sort(key=lambda item: (item[0], item[1]))
            _, focus_skill, focus_progress = known[-1]
            focus_text = f"师父针对你正在修习的【{focus_skill}】指出招式衔接与发力上的不足；当前熟练度为{focus_progress.get('mastery', 0)}，宜继续勤练。"
        else:
            focus_skill = sect_skills[0] if sect_skills else "本门基础功"
            focus_text = f"你尚未真正掌握本门武学，师父先从【{focus_skill}】的基本架势与起手式讲起。"
        mentorship["lessons"] = max(0, int(mentorship.get("lessons", 0))) + 1
        mentorship["bond"] = min(100, max(0, int(mentorship.get("bond", 0))) + 5)
        mentorship["last_lesson_clock"] = now
        mentorship["last_lesson_skill"] = focus_skill
        self.change_relation(mentorship["mentor"], 2)
        return True, f"{focus_text}师门默契提升至 {mentorship['bond']}。"

    def get_sect_official_rank_index(self, sect_name=None):
        """返回正式授阶；旧 V12 存档没有授阶记录时按既有声望推算，避免旧角色降阶。"""
        sect_name = sect_name or self.get_sect()
        ranks = (engine.SECTS.get(sect_name, {}) or {}).get("ranks", []) or []
        if not ranks:
            return 0
        progress = self._sect_progress_state()
        record = progress.get(sect_name)
        if isinstance(record, dict) and "official_rank_index" in record:
            try:
                return max(0, min(len(ranks) - 1, int(record["official_rank_index"])))
            except (TypeError, ValueError):
                pass
        # 旧存档兼容：此前身份由声望自动决定，不强制旧玩家重新补办晋升。
        reputation = self.get_sect_reputation(sect_name)
        index = 0
        for i, rank in enumerate(ranks):
            try:
                if reputation >= int(rank.get("min_reputation", 0)):
                    index = i
            except (TypeError, ValueError):
                continue
        return index

    def get_sect_official_rank(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        ranks = (engine.SECTS.get(sect_name, {}) or {}).get("ranks", []) or []
        index = self.get_sect_official_rank_index(sect_name)
        return ranks[index].get("name", "散人") if ranks else "散人"

    def get_sect_promotion_requirements(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        ranks = (engine.SECTS.get(sect_name, {}) or {}).get("ranks", []) or []
        current = self.get_sect_official_rank_index(sect_name)
        if sect_name == "散人" or current >= len(ranks) - 1:
            return {"available": False, "reason": "当前没有可办理的下一阶门派身份。", "current_index": current}
        target = ranks[current + 1]
        required_rep = int(target.get("min_reputation", 0))
        # 晋升门槛优先读取门派数据，旧数据或缺项时回退到历史默认值，
        # 便于各门派独立调校成长节奏，同时兼容旧 V12 存档和旧 sects.json。
        default_level = {1: 5, 2: 10, 3: 15, 4: 25}.get(current + 1, 1)
        default_mastery = {1: 10, 2: 30, 3: 50, 4: 80}.get(current + 1, 10)
        promotion_table = (engine.SECTS.get(sect_name, {}) or {}).get("promotion_requirements", {}) or {}
        rank_rule = promotion_table.get(str(current + 1), promotion_table.get(current + 1, {})) or {}
        required_level = int(rank_rule.get("level", default_level))
        required_mastery = int(rank_rule.get("mastery", default_mastery))
        basic_skill = (engine.SECTS.get(sect_name, {}) or {}).get("exclusive_skills", [""])[0]
        mastery = self.get_skill_progress(basic_skill).get("mastery", 0) if basic_skill else 0
        mentorship = self.get_sect_mentorship(sect_name)
        mentor_bond = max(0, min(100, int(mentorship.get("bond", 0) or 0)))
        # 只有已开放正式师承玩法的华山检查师承认可；其他门派不得被尚未开放的功能卡住。
        required_mentor_bond = 15 if sect_name == "华山" and current + 1 >= 3 else 0
        # 少林前两阶分别对应沙弥入门与正式受戒，必须先在讲经堂完成对应仪礼。
        required_ordination = None
        if sect_name == "少林" and current + 1 == 1:
            required_ordination = "sect:shaolin:ordination:novice"
        elif sect_name == "少林" and current + 1 == 2:
            required_ordination = "sect:shaolin:ordination:full"
        # 各门派的真传考核必须使用本门历练，不可误套用华山任务或要求不存在的任务。
        sect_trial_quests = {
            "少林": "少林历练·黑风除恶",
            "武当": "武当历练·以静制动",
            "华山": "华山历练·磨剑黑风",
            "铁衣门": "铁衣门历练·护路除匪",
        }
        required_quests = []
        if current + 1 >= 3 and sect_name in sect_trial_quests:
            required_quests.append(sect_trial_quests[sect_name])
        # 华山核心传人还需完成本门调查；其他门派暂不绑定尚未设计的调查剧情。
        if current + 1 >= 4 and sect_name == "华山":
            required_quests.append("青锋疑云")
        # 部分门派阶位还要求完成特定剧情或仪礼；统一由门派数据 promotion_flags 提供，
        # 避免继续在晋升逻辑中按门派硬编码标记。
        promotion_flags = (engine.SECTS.get(sect_name, {}) or {}).get("promotion_flags", {}) or {}
        required_flags = list(promotion_flags.get(str(current + 1), []) or [])
        requirements = {
            "available": True, "current_index": current, "target_index": current + 1,
            "target_rank": target.get("name", "更高身份"), "required_reputation": required_rep,
            "current_reputation": self.get_sect_reputation(sect_name), "required_level": required_level,
            "current_level": int(self.level), "required_mastery": required_mastery,
            "current_mastery": int(mastery), "basic_skill": basic_skill,
            "required_mentor_bond": required_mentor_bond, "current_mentor_bond": mentor_bond,
            "required_ordination": required_ordination,
            "requires_quest": required_quests[-1] if required_quests else None,
            "required_quests": required_quests,
            "required_flags": required_flags,
        }
        return requirements

    def promote_sect_rank(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        if sect_name != self.get_sect() or sect_name == "散人":
            return False, "只有本门弟子才能办理门派晋升。"
        req = self.get_sect_promotion_requirements(sect_name)
        if not req.get("available"):
            return False, req.get("reason", "当前没有可办理的晋升。")
        missing = []
        if req["current_reputation"] < req["required_reputation"]:
            missing.append(f"门派声望需达到 {req['required_reputation']}（当前 {req['current_reputation']}）")
        if req["current_level"] < req["required_level"]:
            missing.append(f"人物等级需达到 {req['required_level']} 级（当前 {req['current_level']} 级）")
        if req["current_mastery"] < req["required_mastery"]:
            missing.append(f"需将【{req['basic_skill']}】练至熟练度 {req['required_mastery']}（当前 {req['current_mastery']}）")
        if req.get("required_mentor_bond", 0) and req.get("current_mentor_bond", 0) < req["required_mentor_bond"]:
            missing.append(f"需获得师承认可（师门默契需达到 {req['required_mentor_bond']}，当前 {req['current_mentor_bond']}；请完成正式拜师并接受师父指点）")
        if req.get("required_ordination") and not self.get_flag(req["required_ordination"], False):
            missing.append("须先到少林讲经堂，在戒律僧面前完成相应受戒仪礼（输入“门派 受戒”）")
        required_quests = req.get("required_quests") or ([req["requires_quest"]] if req.get("requires_quest") else [])
        for quest_name in required_quests:
            if quest_name not in self.completed_quests:
                purpose = "门派调查任务" if quest_name == "青锋疑云" else "本门历练任务"
                missing.append(f"需完成{purpose}《{engine.quest_display_name(quest_name)}》")
        for flag_name in req.get("required_flags", []):
            if not self.get_flag(flag_name, False):
                missing.append(
                    getattr(engine, "PROGRESS_FLAG_HINTS", {}).get(
                        flag_name, "尚有门派前置剧情或仪礼尚未完成"
                    )
                )
        if missing:
            return False, "晋升条件尚未满足：" + "；".join(missing) + "。"
        progress = self._sect_progress_state()
        record = progress.setdefault(sect_name, {})
        record["official_rank_index"] = req["target_index"]
        record.setdefault("promotion_history", []).append({
            "rank": req["target_rank"], "level": int(self.level),
            "reputation": self.get_sect_reputation(sect_name),
        })
        # 正式授阶同时写入既有 world_state.flags，供后续身份任务判断。
        # 不新增存档顶层结构；退门时会清除这些身份标记。
        rank_prefix = {"少林": "shaolin", "武当": "wudang", "华山": "huashan", "铁衣门": "tieyi"}.get(sect_name, sect_name)
        self.set_flag(f"sect:{rank_prefix}:rank:{req['target_index']}", True)
        training = (engine.SECTS.get(sect_name, {}) or {}).get("training", {}) or {}
        examiner = training.get("promotion_teacher")
        examiner_title = training.get("promotion_title")
        if not examiner_title:
            examiner_title = "传功师父" if sect_name == "铁衣门" else "传功师兄"
        if examiner:
            return True, f"经{examiner_title}考核（{examiner}），你正式晋升为【{req['target_rank']}】。门派身份已记录。"
        return True, f"经{examiner_title}考核，你正式晋升为【{req['target_rank']}】。门派身份已记录。"

    def get_sect_relation(self, other_sect):
        current = self.get_sect()
        if other_sect == current:
            return 100
        info = engine.SECTS.get(current, {})
        relations = info.get("relations", {}) or {}
        try:
            return int(relations.get(other_sect, 0))
        except (TypeError, ValueError):
            return 0

    def can_join_sect(self, sect_name):
        if sect_name not in engine.SECTS or sect_name == "散人":
            return False, "请选择实际门派加入。"
        if self.get_sect() != "散人":
            return False, f"你当前已经属于【{self.get_sect()}】，需先离开现有门派。"
        info = engine.SECTS[sect_name]
        required_level = int(info.get("entry_level", 1))
        if self.level < required_level:
            return False, f"拜师失败：等级需达到 {required_level} 级，当前 {self.level} 级。"
        return True, "可以加入"

    def join_sect(self, sect_name):
        ok, reason = self.can_join_sect(sect_name)
        if not ok:
            return False, reason
        state = self._ensure_sect_state()
        state["current_sect"] = sect_name
        self.sect = sect_name
        progress = self._sect_progress_state()
        # 新加入的角色从记名弟子开始逐阶授予；既有 V12 存档不补写此字段，沿用旧身份。
        progress.setdefault(sect_name, {"official_rank_index": 0, "promotion_history": []})
        skill_state = self._ensure_skill_state()
        for skill in engine.SKILLS.get(sect_name, []) or []:
            if isinstance(skill, dict) and int(skill.get("learn_min_reputation", 0)) == 0 and int(skill.get("learn_min_rank", 0)) == 0 and self.level >= int(skill.get("level", 1)):
                entry = skill_state.setdefault(skill.get("name", ""), {"learned": False, "mastery": 0})
                entry["learned"] = True
                entry["mastery"] = max(1, int(entry.get("mastery", 0)))
                break
        message = f"正式拜入【{sect_name}】门下。"
        served_prefixes = {"少林": "shaolin", "武当": "wudang", "华山": "huashan", "铁衣门": "tieyi"}
        served_elsewhere = any(
            self.get_flag(f"world:sect_l15:{prefix}", False)
            for other, prefix in served_prefixes.items()
            if other != sect_name
        )
        reputation = self.get_sect_reputation(sect_name)
        if served_elsewhere and reputation < 0:
            message += (
                f" 门中翻过你的旧档：你曾替别派在断魂岭出手，{sect_name}对你的声望为 {reputation:+d}；"
                "入门后需先修复这段嫌隙。"
            )
        return True, message

    def leave_sect(self):
        current = self.get_sect()
        if current == "散人":
            return False, "你本就是散人，无需退门。"
        state = self._ensure_sect_state()
        progress = self._sect_progress_state()
        record = progress.get(current)
        if isinstance(record, dict):
            # 退门解除有效职位与师承，但保留声望和历练历史。
            record["official_rank_index"] = 0
            record.pop("mentorship", None)
        state["current_sect"] = "散人"
        self.sect = "散人"
        # 兼容旧记录中以门派中文名或内部短名存储的标记。
        prefix = {"少林": "shaolin", "武当": "wudang", "华山": "huashan", "铁衣门": "tieyi"}.get(current, current)
        for flag_prefix in {current, prefix}:
            # 退门后清除只在当前门派身份下有效的入门、受戒与专门阅览许可。
            # 这些标记会影响后续晋升门槛，不能因转投或重新拜入而沿用旧身份许可。
            for suffix in (
                "joined", "entry_interview", "ordination:novice", "ordination:full",
                "scripture_catalogue_reviewed",
            ):
                self.set_flag(f"sect:{flag_prefix}:{suffix}", False)
            # 退门后旧的正式授阶标记不再有效，避免重新拜入时被旧身份任务误判。
            rank_flags = [
                key for key in (self.world_state.get("flags") or {})
                if str(key).startswith(f"sect:{flag_prefix}:rank:")
            ]
            for key in rank_flags:
                self.set_flag(key, False)
        message = f"你已离开【{current}】，恢复江湖散人身份。本门正式职位与师承已解除；既往声望和历练记录仍予保留。"
        served_prefixes = {"少林": "shaolin", "武当": "wudang", "华山": "huashan", "铁衣门": "tieyi"}
        served = [
            name for name, prefix in served_prefixes.items()
            if self.get_flag(f"world:sect_l15:{prefix}", False)
        ]
        if served:
            marks = [
                f"{name}{self.get_sect_reputation(name):+d}"
                for name in ("少林", "武当", "华山", "铁衣门")
                if name != current
            ]
            message += (
                f" 你替【{'、'.join(served)}】在断魂岭出手的立场，江湖各门都记着："
                + "、".join(marks)
                + "。转投他门时，这些旧账不会随退门一笔勾销。"
            )
        return True, message

    def get_sect_summary(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        info = engine.SECTS.get(sect_name, {})
        return {
            "name": sect_name,
            "title": info.get("title", sect_name),
            "desc": info.get("desc", ""),
            "alignment": info.get("alignment", "中立"),
            "reputation": self.get_sect_reputation(sect_name),
            # 对外展示统一使用正式授阶；get_sect_rank 保留声望推算语义，兼容旧调用方。
            "rank": self.get_sect_official_rank(sect_name),
            "exclusive_skills": list(info.get("exclusive_skills", []) or []),
            "relations": dict(info.get("relations", {}) or {}),
            "quest_tags": list(info.get("quest_tags", []) or [])
        }

    def get_sect_questline_summary(self, sect_name=None):
        """按门派数据列出任务线状态，供门派面板用自然语言展示。

        只读取 questline 配置，不在代码里硬编码门派任务；未知任务直接跳过，
        避免旧存档或数据回退时面板报错。
        """
        sect_name = sect_name or self.get_sect()
        info = engine.SECTS.get(sect_name, {}) or {}
        entries = info.get("questline", []) or []
        summary = []
        for raw in entries:
            if isinstance(raw, dict):
                quest_name = raw.get("quest", "")
                optional = bool(raw.get("optional", False))
            else:
                quest_name = str(raw)
                optional = False
            quest = engine.QUESTS.get(quest_name)
            if not isinstance(quest, dict):
                continue
            giver = quest.get("npc", "") or ""
            room_id = self.get_npc_home_location(giver) if giver else None
            location = ""
            if room_id:
                location = (engine.ROOMS.get(room_id, {}) or {}).get("name", room_id)
            if quest_name in self.completed_quests:
                status, missing = "completed", []
            elif quest_name in self.active_quests:
                status, missing = "active", []
            else:
                requires = quest.get("requires")
                if engine.check_conditions(requires, self.world_state, self.completed_quests, self):
                    status, missing = "available", []
                else:
                    status = "locked"
                    missing = engine.explain_condition_failures(
                        requires, self.world_state, self.completed_quests, self
                    )
            summary.append({
                "quest": quest_name,
                "title": engine.quest_display_name(quest_name),
                "status": status,
                "optional": optional,
                "giver": giver,
                "location": location,
                "missing": missing,
            })
        return summary

    # ==================== P2.24 门派武学成长系统 ====================
    def _skill_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("skill_progress", {})
        if not isinstance(state, dict):
            state = {}
            variables["skill_progress"] = state
        return state

    def _all_skill_map(self):
        result = {}
        for group in engine.SKILLS.values():
            if not isinstance(group, list):
                continue
            for skill in group:
                if isinstance(skill, dict) and skill.get("name"):
                    result[skill["name"]] = skill
        return result

    def get_skill_info(self, skill_name):
        for skill in engine.SKILLS.get(self.get_sect(), []) or []:
            if isinstance(skill, dict) and skill.get("name") == skill_name:
                return skill
        return self._all_skill_map().get(skill_name, {})

    def _skill_rank_index(self, sect_name=None):
        sect_name = sect_name or self.get_sect()
        progress = self._sect_progress_state()
        record = progress.get(sect_name)
        if isinstance(record, dict) and "official_rank_index" in record:
            try:
                return max(0, min(len((engine.SECTS.get(sect_name, {}) or {}).get("ranks", []) or []) - 1, int(record["official_rank_index"])))
            except (TypeError, ValueError):
                pass
        # 旧 V12 角色继续按既有声望规则判定，避免无故失去原有武学资格。
        info = engine.SECTS.get(sect_name, {})
        ranks = info.get("ranks", []) or []
        rep = self.get_sect_reputation(sect_name)
        index = 0
        for i, rank in enumerate(ranks):
            try:
                if rep >= int(rank.get("min_reputation", 0)):
                    index = i
            except (TypeError, ValueError):
                continue
        return index

    def _ensure_skill_state(self):
        state = self._skill_state()
        # 先规范化所有已保存武学（包括非当前门派的历史武学）。合法 JSON 中
        # 仍可能出现 mastery="bad" 或 learned=[]；不能等到查看/使用武学时才崩溃。
        skill_map = self._all_skill_map()
        for name, raw_entry in list(state.items()):
            if not isinstance(raw_entry, dict):
                raw_entry = {"learned": False, "mastery": 0}
            entry = dict(raw_entry)
            entry["learned"] = entry.get("learned") if isinstance(entry.get("learned"), bool) else False
            try:
                maximum = max(1, int(skill_map.get(name, {}).get("mastery_max", 100) or 100))
                mastery = int(entry.get("mastery", 0))
                entry["mastery"] = max(0, min(maximum, mastery))
            except (TypeError, ValueError, OverflowError):
                entry["mastery"] = 0
            state[name] = entry
        # 兼容旧 V12：进入 P2.24 后，只为当前门派自动登记可用的首门武学，
        # 不把未来高阶武学直接塞入存档。
        current = self.get_sect()
        for skill in engine.SKILLS.get(current, []) or []:
            if not isinstance(skill, dict) or not skill.get("name"):
                continue
            name = skill["name"]
            entry = state.get(name)
            if not isinstance(entry, dict):
                entry = {"learned": False, "mastery": 0}
            entry.setdefault("learned", False)
            entry.setdefault("mastery", 0)
            try:
                entry["mastery"] = max(0, min(int(skill.get("mastery_max", 100)), int(entry["mastery"])))
            except (TypeError, ValueError, OverflowError):
                entry["mastery"] = 0
            state[name] = entry
        # 散人基础吐纳作为历史兼容的默认起手武学。
        if current == "散人":
            for skill in engine.SKILLS.get("散人", []) or []:
                if skill.get("name") == "基础吐纳":
                    state[skill["name"]]["learned"] = True
                    if state[skill["name"]].get("mastery", 0) <= 0:
                        state[skill["name"]]["mastery"] = 1
        return state

    def get_character_realm_title(self):
        """根据现有人物等级给出武侠风格称号；不改变经验曲线和战斗数值。"""
        try:
            level = max(1, int(self.level))
        except (TypeError, ValueError):
            level = 1
        ranks = (
            (50, "武林宗师"),
            (40, "一代高手"),
            (30, "名动一方"),
            (20, "出类拔萃"),
            (15, "渐入佳境"),
            (10, "略有小成"),
            (5, "初窥门径"),
            (1, "初入江湖"),
        )
        return next(title for minimum, title in ranks if level >= minimum)

    @staticmethod
    def get_skill_mastery_title(mastery, mastery_max=100, learned=True):
        """把已有熟练度转换为可读称号，不改变原有武学等级计算。"""
        if not learned:
            return "尚未入门"
        try:
            maximum = max(1, int(mastery_max))
            value = max(0, min(maximum, int(mastery)))
        except (TypeError, ValueError):
            value, maximum = 0, 100
        ratio = value / maximum
        if ratio >= 1.0:
            return "返璞归真"
        if ratio >= 0.8:
            return "登峰造极"
        if ratio >= 0.6:
            return "炉火纯青"
        if ratio >= 0.4:
            return "融会贯通"
        if ratio >= 0.25:
            return "驾轻就熟"
        if ratio >= 0.1:
            return "略有小成"
        return "初学乍练"

    def get_skill_progress(self, skill_name):
        self._ensure_skill_state()
        info = self.get_skill_info(skill_name)
        state = self._skill_state().get(skill_name, {})
        mastery = max(0, int(state.get("mastery", 0)))
        maximum = max(1, int(info.get("mastery_max", 100) or 100))
        mastery = min(maximum, mastery)
        # 熟练度 0~100 对应武学等级 1~5；未学习时等级为 0。
        learned = bool(state.get("learned", False))
        if not learned:
            level = 0
        elif mastery >= 80:
            level = 5
        elif mastery >= 50:
            level = 4
        elif mastery >= 30:
            level = 3
        elif mastery >= 10:
            level = 2
        else:
            level = 1
        return {
            "name": skill_name,
            "learned": learned,
            "mastery": mastery,
            "mastery_max": maximum,
            "level": level,
            "title": self.get_skill_mastery_title(mastery, maximum, learned),
        }

    def can_learn_skill(self, skill_name):
        info = self.get_skill_info(skill_name)
        if not info:
            return False, "不存在这门武学。"
        owner = next((sect for sect, skills in engine.SKILLS.items() if any(isinstance(x, dict) and x.get("name") == skill_name for x in (skills or []))), None)
        if owner != self.get_sect():
            return False, f"【{skill_name}】并非你当前门派可学武学。"
        progress = self.get_skill_progress(skill_name)
        if progress["learned"]:
            return False, f"你已经学会【{skill_name}】。"
        if self.level < int(info.get("level", 1)):
            return False, f"等级不足，需要达到 {info.get('level', 1)} 级。"
        rep_need = int(info.get("learn_min_reputation", 0))
        if self.get_sect_reputation() < rep_need:
            return False, f"门派声望不足，需要 {rep_need}，当前为 {self.get_sect_reputation()}。"
        rank_need = int(info.get("learn_min_rank", 0))
        if self._skill_rank_index() < rank_need:
            ranks = (engine.SECTS.get(self.get_sect(), {}) or {}).get("ranks", []) or []
            rank_name = ranks[rank_need].get("name", f"第 {rank_need + 1} 阶身份") if 0 <= rank_need < len(ranks) else f"第 {rank_need + 1} 阶身份"
            return False, f"门派身份不足，需正式晋升为【{rank_name}】后才能学习。"
        return True, "可以学习"

    def learn_skill(self, skill_name):
        ok, reason = self.can_learn_skill(skill_name)
        if not ok:
            return False, reason
        state = self._ensure_skill_state()
        state[skill_name] = {"learned": True, "mastery": 1}
        return True, f"你已学会【{skill_name}】，当前武学等级 1。"

    def learn_skill_from_manual(self, skill_name):
        """通过实体秘籍学习明确标记为 manual_learnable 的江湖武学；记录复用既有 V12 技能状态。"""
        info = self.get_skill_info(skill_name)
        if not info or not info.get("manual_learnable"):
            return False, "这本秘籍记载的内容暂时无法研习。"
        state = self._skill_state()
        entry = state.get(skill_name, {})
        if isinstance(entry, dict) and entry.get("learned"):
            return False, f"你已经学会【{skill_name}】，无需重复研习。"
        try:
            required_level = max(1, int(info.get("level", 1)))
        except (TypeError, ValueError):
            required_level = 1
        if int(getattr(self, "level", 1) or 1) < required_level:
            return False, f"你的阅历不足，需要达到 {required_level} 级才能领会这门武学。"
        state[skill_name] = {"learned": True, "mastery": 1}
        return True, f"你从秘籍中领会了【{skill_name}】，当前武学熟练度为初学乍练。"

    def forget_skill(self, skill_name):
        info = self.get_skill_info(skill_name)
        if not info:
            return False, "不存在这门武学。"
        owner = next((sect for sect, skills in engine.SKILLS.items()
                      if any(isinstance(x, dict) and x.get("name") == skill_name for x in (skills or []))), None)
        if owner != self.get_sect():
            return False, f"【{skill_name}】属于其他门派的传承武学；当前身份下不能遗忘或修改这段历史修习记录。"
        progress = self.get_skill_progress(skill_name)
        if not progress["learned"]:
            return False, f"你尚未学会【{skill_name}】。"
        # 基础门派武学允许遗忘；重新学习仍需满足原门槛，熟练度会重置。
        self._skill_state()[skill_name] = {"learned": False, "mastery": 0}
        return True, f"你已暂时遗忘【{skill_name}】。"

    def get_available_skills(self):
        self._ensure_skill_state()
        result = []
        for skill in engine.SKILLS.get(self.get_sect(), []) or []:
            if not isinstance(skill, dict) or not skill.get("name"):
                continue
            progress = self.get_skill_progress(skill["name"])
            if not progress["learned"]:
                continue
            # 历史学会记录不等于当前身份下仍可施展：退门会重置正式职位，
            # 重新拜入后必须重新达到该武学的职位门槛，避免旧高阶武学绕过门规。
            try:
                required_rank = max(0, int(skill.get("learn_min_rank", 0)))
            except (TypeError, ValueError):
                required_rank = 0
            if self._skill_rank_index() < required_rank:
                continue
            runtime = dict(skill)
            mastery_level = progress["level"]
            runtime["mastery_level"] = mastery_level
            runtime["mastery"] = progress["mastery"]
            runtime["mp_cost"] = max(1, int(skill.get("mp_cost", 0)) - max(0, mastery_level - 1) * int(skill.get("mastery_mp_reduction", 1)))
            runtime["power"] = float(skill.get("power", 0)) + max(0, mastery_level - 1) * float(skill.get("mastery_power_per_level", 0.04))
            result.append(runtime)
        # 秘籍学得的江湖武学可跨门派使用，但必须显式标记为可由秘籍习得。
        known = {entry.get("name") for entry in result if isinstance(entry, dict)}
        for group in engine.SKILLS.values():
            if not isinstance(group, list):
                continue
            for skill in group:
                if not isinstance(skill, dict) or not skill.get("manual_learnable") or skill.get("name") in known:
                    continue
                progress = self.get_skill_progress(skill["name"])
                if not progress["learned"]:
                    continue
                runtime = dict(skill)
                mastery_level = progress["level"]
                runtime["mastery_level"] = mastery_level
                runtime["mastery"] = progress["mastery"]
                runtime["mp_cost"] = max(1, int(skill.get("mp_cost", 0)) - max(0, mastery_level - 1) * int(skill.get("mastery_mp_reduction", 1)))
                runtime["power"] = float(skill.get("power", 0)) + max(0, mastery_level - 1) * float(skill.get("mastery_power_per_level", 0.04))
                result.append(runtime)
                known.add(skill["name"])
        return result

    def record_skill_use(self, skill_name, success=True):
        info = self.get_skill_info(skill_name)
        if not info:
            return {"name": skill_name, "learned": False, "mastery": 0, "level": 0, "mastery_max": 100}
        # 熟练度只能由当前门派实际使用本门武学时增长；防止旧存档或异常调用
        # 让退门后的旧门派武学继续获得成长。
        owner = next((sect for sect, skills in engine.SKILLS.items()
                      if any(isinstance(x, dict) and x.get("name") == skill_name for x in (skills or []))), None)
        if owner != self.get_sect() and not (info.get("manual_learnable") and owner is not None):
            return self.get_skill_progress(skill_name)
        if not success:
            return self.get_skill_progress(skill_name)
        state = self._ensure_skill_state()
        entry = state.get(skill_name)
        if not isinstance(entry, dict) or not entry.get("learned"):
            return self.get_skill_progress(skill_name)
        before = int(entry.get("mastery", 0))
        maximum = max(1, int(info.get("mastery_max", 100) or 100))
        gain = max(1, int(info.get("mastery_gain", 10) or 10))
        entry["mastery"] = min(maximum, before + gain)
        return self.get_skill_progress(skill_name)

    def get_skill_summary(self):
        self._ensure_skill_state()
        result = []
        for skill in engine.SKILLS.get(self.get_sect(), []) or []:
            if not isinstance(skill, dict):
                continue
            progress = self.get_skill_progress(skill.get("name", ""))
            try:
                required_rank = max(0, int(skill.get("learn_min_rank", 0)))
            except (TypeError, ValueError):
                required_rank = 0
            usable = bool(progress["learned"] and self._skill_rank_index() >= required_rank)
            result.append({
                "name": skill.get("name", ""),
                "character_level": int(skill.get("level", 1)),
                "learn_min_reputation": int(skill.get("learn_min_reputation", 0)),
                "learn_min_rank": required_rank,
                "usable": usable,
                **progress,
            })
        known = {entry.get("name") for entry in result if isinstance(entry, dict)}
        for group in engine.SKILLS.values():
            if not isinstance(group, list):
                continue
            for skill in group:
                if not isinstance(skill, dict) or not skill.get("manual_learnable") or skill.get("name") in known:
                    continue
                progress = self.get_skill_progress(skill["name"])
                if progress["learned"]:
                    result.append({"name": skill.get("name", ""), "character_level": int(skill.get("level", 1)),
                                   "learn_min_reputation": 0, "learn_min_rank": 0, "usable": True, **progress})
                    known.add(skill["name"])
        return result

    # ==================== P2.22 NPC 关系系统 ====================
    def _relation_map(self):
        variables = self.world_state.setdefault("variables", {})
        relations = variables.setdefault("npc_relations", {})
        if not isinstance(relations, dict):
            relations = {}
            variables["npc_relations"] = relations
        return relations

    def get_relation(self, npc_name):
        relations = self._relation_map()
        raw = relations.get(npc_name, engine.NPCS.get(npc_name, {}).get("initial_relation", 0))
        try:
            return max(engine.RELATION_MIN, min(engine.RELATION_MAX, int(raw)))
        except (TypeError, ValueError):
            return 0

    def get_relation_status(self, npc_name):
        return engine.relation_status(self.get_relation(npc_name))

    # ==================== P2.41 NPC 势力关系生态 ====================
    def _faction_relation_map(self):
        variables = self.world_state.setdefault("variables", {})
        relations = variables.setdefault("faction_relations", {})
        if not isinstance(relations, dict):
            relations = {}
            variables["faction_relations"] = relations
        return relations

    def get_npc_faction(self, npc_name):
        info = engine.NPCS.get(npc_name, {}) or {}
        faction = info.get("faction", "")
        return str(faction) if faction in engine.FACTIONS else ""

    def get_faction_relation(self, faction_a, faction_b):
        faction_a, faction_b = str(faction_a), str(faction_b)
        if faction_a == faction_b and faction_a in engine.FACTIONS:
            return 100
        if faction_a not in engine.FACTIONS or faction_b not in engine.FACTIONS:
            return 0
        key = f"{faction_a}:{faction_b}"
        reverse = f"{faction_b}:{faction_a}"
        relations = self._faction_relation_map()
        if key in relations:
            raw = relations[key]
        elif reverse in relations:
            raw = relations[reverse]
        else:
            raw = (engine.FACTIONS.get(faction_a, {}).get("relations", {}) or {}).get(faction_b, 0)
        try:
            return max(-100, min(100, int(raw)))
        except (TypeError, ValueError):
            return 0

    def get_faction_stance(self, faction_a, faction_b):
        value = self.get_faction_relation(faction_a, faction_b)
        if value <= -60: return "敌对"
        if value <= -20: return "紧张"
        if value < 20: return "中立"
        if value < 60: return "友好"
        return "盟友"

    def change_faction_relation(self, faction_a, faction_b, delta, symmetric=True):
        faction_a, faction_b = str(faction_a), str(faction_b)
        if faction_a not in engine.FACTIONS or faction_b not in engine.FACTIONS or faction_a == faction_b:
            return self.get_faction_relation(faction_a, faction_b)
        if isinstance(delta, bool):
            return self.get_faction_relation(faction_a, faction_b)
        try:
            delta = int(delta)
        except (TypeError, ValueError, OverflowError):
            return self.get_faction_relation(faction_a, faction_b)
        relations = self._faction_relation_map()
        old = self.get_faction_relation(faction_a, faction_b)
        new = max(-100, min(100, old + delta))
        relations[f"{faction_a}:{faction_b}"] = new
        if symmetric:
            relations[f"{faction_b}:{faction_a}"] = new
        return new

    # ==================== P2.45 玩家世界影响系统 ====================
    def _player_faction_influence_map(self):
        variables = self.world_state.setdefault("variables", {})
        data = variables.setdefault("player_faction_influence", {})
        if not isinstance(data, dict):
            data = {}
            variables["player_faction_influence"] = data
        return data

    def get_player_faction_influence(self, faction_name):
        data = self._player_faction_influence_map()
        try:
            return max(-100, min(100, int(data.get(str(faction_name), 0))))
        except (TypeError, ValueError):
            return 0

    def change_player_faction_influence(self, faction_name, delta):
        if str(faction_name) not in engine.FACTIONS:
            return 0
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            delta = 0
        data = self._player_faction_influence_map()
        old = self.get_player_faction_influence(faction_name)
        data[str(faction_name)] = max(-100, min(100, old + delta))
        return data[str(faction_name)]

    def apply_world_influence(self, faction_name, relation_delta=0, influence_delta=0):
        self.change_player_faction_influence(faction_name, influence_delta)
        return self.change_faction_relation("玩家", faction_name, relation_delta) if False else self.get_player_faction_influence(faction_name)

    def get_player_world_influence_summary(self):
        return [{"faction": f, "influence": self.get_player_faction_influence(f)} for f in engine.FACTIONS]

    def get_faction_influence(self, faction_name):
        try:
            return max(0, min(100, int((engine.FACTIONS.get(str(faction_name), {}) or {}).get("influence", 0))))
        except (TypeError, ValueError):
            return 0

    def get_faction_summary(self):
        result = []
        for faction_name, info in engine.FACTIONS.items():
            if not isinstance(info, dict): continue
            relations = []
            for other in engine.FACTIONS:
                if other == faction_name: continue
                relations.append({"faction": other, "relation": self.get_faction_relation(faction_name, other), "stance": self.get_faction_stance(faction_name, other)})
            relations.sort(key=lambda x: (x["relation"], x["faction"]))
            result.append({"faction": faction_name, "title": info.get("title", faction_name), "stance": info.get("stance", ""), "influence": self.get_faction_influence(faction_name), "relations": relations})
        return result

    # ==================== P2.42 势力主动行动与冲突生态 ====================
    def _faction_action_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("faction_actions", {})
        if not isinstance(state, dict):
            state = {}
            variables["faction_actions"] = state
        return state

    def _faction_action_log(self):
        variables = self.world_state.setdefault("variables", {})
        log = variables.setdefault("faction_action_log", [])
        if not isinstance(log, list):
            log = []
            variables["faction_action_log"] = log
        return log

    def get_faction_action_log(self, limit=10):
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 10
        return list(self._faction_action_log()[-limit:])

    def _faction_action_allowed(self, faction_name, action):
        if not isinstance(action, dict) or faction_name not in engine.FACTIONS:
            return False
        if not engine.check_conditions(action.get("requires"), self.world_state, self.completed_quests, self):
            return False
        state = self._faction_action_state().get(faction_name, {})
        if not isinstance(state, dict):
            state = {}
        history = state.get("history", {})
        if not isinstance(history, dict):
            history = {}
        action_id = str(action.get("id", ""))
        last = history.get(action_id)
        if action.get("once", False) and last is not None:
            return False
        clock = self.get_quest_clock()
        interval = max(0, int(action.get("interval", 0) or 0))
        if last is not None and interval:
            try:
                if clock - int(last) < interval:
                    return False
            except (TypeError, ValueError):
                pass
        cooldown = max(0, int(action.get("cooldown", 0) or 0))
        if last is not None and cooldown:
            try:
                if clock - int(last) < cooldown:
                    return False
            except (TypeError, ValueError):
                pass
        return bool(action_id)

    def _apply_faction_action(self, faction_name, action):
        action_id = str(action.get("id", ""))
        text = str(action.get("text", action.get("title", "势力采取了一项行动。")))
        effects = action.get("effects", {}) or {}
        engine.apply_world_effects(self.world_state, effects)

        for entry in action.get("npc_information", []) or []:
            if not isinstance(entry, dict) or entry.get("npc") not in engine.NPCS or not entry.get("topic"):
                continue
            self.learn_npc_information(
                entry["npc"], entry["topic"], entry.get("text", text), entry.get("source", faction_name),
                entry.get("confidence", 70), entry.get("ttl", 0), entry.get("sentiment", "neutral"), entry.get("follow_up")
            )
        player_info = action.get("player_information")
        if isinstance(player_info, dict) and player_info.get("topic"):
            self.learn_player_information(
                player_info["topic"], player_info.get("text", text), player_info.get("source", faction_name),
                player_info.get("confidence", 70), player_info.get("ttl", 0), player_info.get("sentiment", "neutral"),
                player_info.get("follow_up")
            )
        reactions = action.get("npc_reactions", []) or []
        if isinstance(reactions, list):
            self._apply_npc_reactions(reactions, f"faction:{faction_name}:{action_id}")
        memory = action.get("remember_player_action")
        if isinstance(memory, dict) and memory.get("npc") in engine.NPCS:
            self.remember_player_action(
                memory["npc"], memory.get("id", f"faction_action:{faction_name}:{action_id}"),
                memory.get("text", text), memory.get("sentiment", "neutral"),
                memory.get("strength", 35), memory.get("ttl", 0), event_type="faction_action"
            )

        clock = self.get_quest_clock()
        state = self._faction_action_state().setdefault(faction_name, {})
        history = state.setdefault("history", {})
        history[action_id] = clock
        record = {
            "clock": clock,
            "faction": faction_name,
            "action_id": action_id,
            "title": str(action.get("title", action_id)),
            "type": str(action.get("type", "world")),
            "target_faction": str(action.get("target_faction", "")),
            "text": text,
        }
        log = self._faction_action_log()
        log.append(record)
        del log[:-100]
        return record

    # ==================== P2.43 势力冲突升级与世界局势 ====================
    def _faction_conflict_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("faction_conflicts", {})
        if not isinstance(state, dict):
            state = {}
            variables["faction_conflicts"] = state
        return state

    def _faction_conflict_key(self, faction_a, faction_b):
        return ":".join(sorted((str(faction_a), str(faction_b))))

    def _faction_conflict_level(self, pressure):
        pressure = int(pressure)
        if pressure >= 150: return "war"
        if pressure >= 110: return "escalation"
        if pressure >= 75: return "conflict"
        if pressure >= 45: return "confrontation"
        if pressure >= 20: return "tension"
        return "calm"

    def get_faction_conflicts(self):
        result = []
        state = self._faction_conflict_state()
        for key, record in state.items():
            if not isinstance(record, dict):
                continue
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            result.append({
                "key": key, "factions": parts,
                "relation": int(record.get("relation", self.get_faction_relation(*parts))),
                "pressure": int(record.get("pressure", 0)),
                "level": str(record.get("level", "calm")),
                "last_change": int(record.get("last_change", 0) or 0),
            })
        result.sort(key=lambda x: (-x["pressure"], x["key"]))
        return result

    def _faction_members(self, faction_name):
        return [name for name, info in engine.NPCS.items() if isinstance(info, dict) and info.get("faction") == faction_name]

    def _apply_faction_conflict_level(self, faction_a, faction_b, old_level, new_level, pressure):
        if old_level == new_level:
            return []
        clock = self.get_quest_clock()
        applied = []
        severity = {"calm": 0, "tension": 1, "confrontation": 2, "conflict": 3, "escalation": 4, "war": 5}.get(new_level, 0)
        if severity >= 2:
            for faction in (faction_a, faction_b):
                members = self._faction_members(faction)
                for npc in members[:2]:
                    state = "fear" if severity >= 5 else "busy"
                    reason = f"{faction_a}与{faction_b}局势升级至{new_level}"
                    if self.set_npc_state(npc, state, 4, reason, f"faction_conflict:{faction_a}:{faction_b}"):
                        applied.append(npc)
        topic = f"faction_conflict:{faction_a}:{faction_b}"
        self.learn_player_information(topic, f"{faction_a}与{faction_b}的势力冲突升级为【{new_level}】。", "世界局势", 85 if severity >= 4 else 70, 12, "negative")
        self.world_state.setdefault("variables", {}).setdefault("faction_conflict_log", []).append({
            "clock": clock, "factions": [faction_a, faction_b], "old_level": old_level, "level": new_level, "pressure": pressure
        })
        log = self.world_state["variables"]["faction_conflict_log"]
        del log[:-100]
        return applied

    def process_faction_conflicts(self):
        """根据势力关系与近期势力行动积累冲突压力，并在跨等级时改变世界状态。"""
        state = self._faction_conflict_state()
        factions = list(engine.FACTIONS.keys())
        clock = self.get_quest_clock()
        action_log = self._faction_action_log()
        results = []
        for i, faction_a in enumerate(factions):
            for faction_b in factions[i + 1:]:
                relation = self.get_faction_relation(faction_a, faction_b)
                key = self._faction_conflict_key(faction_a, faction_b)
                record = state.setdefault(key, {"pressure": 0, "level": "calm", "last_change": clock, "history": []})
                old_level = str(record.get("level", "calm"))
                if old_level not in {"calm", "tension", "confrontation", "conflict", "escalation", "war"}:
                    old_level = "calm"
                try:
                    old_relation = max(-100, min(100, int(record.get("relation", relation))))
                except (TypeError, ValueError, OverflowError):
                    old_relation = relation
                try:
                    pressure = max(0, min(200, int(record.get("pressure", 0))))
                except (TypeError, ValueError, OverflowError):
                    pressure = 0
                if relation <= -20:
                    # 只计算当前世界 Tick 新发生的冲突行动；旧日志仍可用于历史展示，
                    # 但不能每个 Tick 被重复计入压力，否则冲突疲劳永远无法发挥作用。
                    recent_conflicts = sum(1 for row in action_log[-20:] if isinstance(row, dict) and row.get("type") == "conflict" and row.get("clock") == clock and {row.get("faction"), row.get("target_faction")} == {faction_a, faction_b})
                    # 高压冲突若没有新的冲突行动，不再仅因旧有敌对关系持续自动加压；
                    # 让动态稳定层的疲劳恢复真正生效，避免战争永久锁死在高压状态。
                    if pressure < 110:
                        pressure += max(1, (-relation - 10) // 15)
                    pressure += min(4, recent_conflicts)
                    if relation < old_relation:
                        pressure += min(5, (old_relation - relation) // 10)
                else:
                    pressure = max(0, pressure - (3 if relation >= 20 else 1))
                pressure = max(0, min(200, pressure))
                new_level = self._faction_conflict_level(pressure)
                record.update({"relation": relation, "pressure": pressure, "level": new_level, "last_change": clock})
                if new_level != old_level:
                    if not isinstance(record.get("history"), list):
                        record["history"] = []
                    record["history"].append({"clock": clock, "from": old_level, "to": new_level, "pressure": pressure})
                    del record["history"][:-20]
                    applied = self._apply_faction_conflict_level(faction_a, faction_b, old_level, new_level, pressure)
                    results.append({"key": key, "factions": [faction_a, faction_b], "level": new_level, "pressure": pressure, "npcs": applied})
        # 汇总供任务/世界事件直接引用；仍只存于既有 variables。
        active = [r for r in self.get_faction_conflicts() if r["level"] != "calm"]
        self.world_state.setdefault("variables", {})["world_tension"] = sum(min(5, {"tension":1,"confrontation":2,"conflict":3,"escalation":4,"war":5}.get(r["level"],0)) for r in active)
        return results

    def process_faction_actions(self):
        """按世界时钟推进势力主动行动；结果只写入既有 V12 world_state.variables。"""
        results = []
        for faction_name, info in engine.FACTIONS.items():
            if not isinstance(info, dict):
                continue
            actions = info.get("actions", []) or []
            if not isinstance(actions, list):
                continue
            for action in actions:
                if self._faction_action_allowed(faction_name, action):
                    results.append(self._apply_faction_action(faction_name, action))
                    break
        return results

    # ==================== P2.46 动态世界稳定层 ====================
    def _dynamic_world_stability_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("dynamic_world_stability", {})
        if not isinstance(state, dict):
            state = {}
            variables["dynamic_world_stability"] = state
        return state

    def _trim_dynamic_world_histories(self):
        """限制动态世界历史长度，防止长期 Tick 导致存档无界增长。"""
        variables = self.world_state.setdefault("variables", {})
        limits = {
            "faction_action_log": 100,
            "faction_conflict_log": 100,
            "npc_action_log": 100,
            "npc_proactive_events": 100,
            "quest_interventions": 100,
            "quest_competitions": 100,
        }
        for key, limit in limits.items():
            value = variables.get(key)
            if isinstance(value, list) and len(value) > limit:
                del value[:-limit]

        conflicts = variables.get("faction_conflicts")
        if isinstance(conflicts, dict):
            for record in conflicts.values():
                if isinstance(record, dict) and isinstance(record.get("history"), list) and len(record["history"]) > 20:
                    del record["history"][:-20]

        region_state = variables.get("region_ecology")
        if isinstance(region_state, dict):
            for record in region_state.values():
                if isinstance(record, dict):
                    for key in ("security", "commerce", "travel", "tension"):
                        if key in record:
                            try:
                                record[key] = max(0, min(100, int(record[key])))
                            except (TypeError, ValueError):
                                record[key] = 0

    def _stabilize_faction_conflicts(self):
        """让长期冲突具备疲劳、停火与恢复能力，避免永久战争。"""
        variables = self.world_state.setdefault("variables", {})
        state = variables.get("faction_conflicts", {})
        if not isinstance(state, dict):
            return []
        stability = self._dynamic_world_stability_state()
        last_recovery = stability.setdefault("faction_recovery", {})
        action_log = self._faction_action_log()
        clock = self.get_quest_clock()
        recovered = []
        level_score = self.REGION_LEVEL_SCORE if hasattr(self, "REGION_LEVEL_SCORE") else {
            "calm": 0, "tension": 1, "confrontation": 2, "conflict": 3, "escalation": 4, "war": 5
        }
        for key, record in state.items():
            if not isinstance(record, dict) or ":" not in str(key):
                continue
            parts = str(key).split(":", 1)
            if len(parts) != 2 or parts[0] not in engine.FACTIONS or parts[1] not in engine.FACTIONS:
                continue
            try:
                pressure = max(0, min(200, int(record.get("pressure", 0))))
            except (TypeError, ValueError):
                pressure = 0
            if pressure < 45:
                continue
            last = int(last_recovery.get(key, -9999) or -9999)
            if clock - last < 6:
                continue
            recent = [r for r in action_log[-6:] if isinstance(r, dict) and r.get("type") == "conflict"
                      and {r.get("faction"), r.get("target_faction")} == set(parts)]
            # 高压状态即使仍有冲突行动，也会产生疲劳；只有中低压时才要求近期没有新冲突。
            if recent and pressure < 110:
                continue
            old_level = str(record.get("level", self._faction_conflict_level(pressure)))
            relation = self.get_faction_relation(*parts)
            recovery = 8 if pressure >= 150 else 6 if pressure >= 110 else 4
            new_pressure = max(0, pressure - recovery)
            record["pressure"] = max(0, min(200, new_pressure))
            record["relation"] = relation
            new_level = self._faction_conflict_level(new_pressure)
            record["level"] = new_level
            record["last_change"] = clock
            last_recovery[key] = clock
            if new_level != old_level:
                record.setdefault("history", []).append({"clock": clock, "from": old_level, "to": new_level, "pressure": new_pressure, "reason": "conflict_fatigue"})
                del record["history"][:-20]
                self._apply_faction_conflict_level(parts[0], parts[1], old_level, new_level, new_pressure)
            recovered.append({"key": key, "from": old_level, "level": new_level, "pressure": new_pressure})
        # 高压疲劳也会缓慢修复关系，避免永久锁死在极端敌对值。
        for key, record in state.items():
            if not isinstance(record, dict) or ":" not in str(key):
                continue
            parts = str(key).split(":", 1)
            try:
                pressure = int(record.get("pressure", 0))
            except (TypeError, ValueError):
                continue
            if pressure < 110:
                continue
            last = int(last_recovery.get(f"relation:{key}", -9999) or -9999)
            if clock - last < 12:
                continue
            relation = self.get_faction_relation(*parts)
            if relation < 0:
                self.change_faction_relation(parts[0], parts[1], min(3, -relation))
                record["relation"] = self.get_faction_relation(*parts)
                last_recovery[f"relation:{key}"] = clock
        return recovered

    def process_dynamic_world_stability(self):
        """P2.46：长期运行维护、信息过期清理、冲突疲劳恢复与状态边界收敛。"""
        self.cleanup_information()
        self.cleanup_npc_memories()
        recovered = self._stabilize_faction_conflicts()
        self._trim_dynamic_world_histories()
        variables = self.world_state.setdefault("variables", {})
        # 势力行动产生的长期计数器只作为生态指标，限制其增长避免存档无界膨胀。
        for key in ("village_alert", "law_enforcement_pressure", "black_market_activity", "merchant_mediation", "jianghu_rumor_wave", "shen_mansion_pressure"):
            if key in variables:
                try:
                    variables[key] = max(0, min(1000, int(variables[key])))
                except (TypeError, ValueError):
                    variables[key] = 0
        active = [r for r in self.get_faction_conflicts() if r["level"] != "calm"]
        variables["world_tension"] = sum(min(5, {"tension":1, "confrontation":2, "conflict":3, "escalation":4, "war":5}.get(r["level"], 0)) for r in active)
        variables["dynamic_world_last_stability_tick"] = self.get_quest_clock()
        return recovered

    # ==================== P2.44 区域局势与地图生态联动 ====================
    REGION_LEVEL_SCORE = {"calm": 0, "tension": 1, "confrontation": 2, "conflict": 3, "escalation": 4, "war": 5}

    def _region_ecology_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("region_ecology", {})
        if not isinstance(state, dict):
            state = {}
            variables["region_ecology"] = state
        return state

    def get_region_ecology(self, zone=None):
        zone = zone or engine.ROOMS.get(self.location, {}).get("zone", "main")
        info = engine.WORLD_REGIONS.get(zone, {}) or {}
        base = info.get("region_ecology", {}) or {}
        state = self._region_ecology_state().get(zone, {})
        if not isinstance(state, dict): state = {}
        # 区域态势同时供场景描述、巡逻、危机与战斗遭遇读取；任何一项异常
        # 都应回退到地区基础值，而不是让整个世界 Tick 或场景显示失败。
        result = {
            "zone": zone,
            "name": info.get("name", zone),
            "security": _safe_int_value(state.get("security"), _safe_int_value(base.get("security_base"), 70), 0, 100),
            "commerce": _safe_int_value(state.get("commerce"), _safe_int_value(base.get("commerce_base"), 70), 0, 100),
            "travel": _safe_int_value(state.get("travel"), _safe_int_value(base.get("travel_base"), 70), 0, 100),
            "tension": _safe_int_value(state.get("tension"), 0, 0),
            "danger": str(state.get("danger", info.get("danger", "normal"))),
            "level": str(state.get("level", "calm")),
            "last_change": _safe_int_value(state.get("last_change"), 0, 0),
        }
        return result

    def _region_conflict_level(self, zone):
        info = engine.WORLD_REGIONS.get(zone, {}) or {}
        exposure = set(info.get("faction_exposure", []) or [])
        if not exposure: return "calm", 0
        rows = []
        for row in self.get_faction_conflicts():
            if exposure.intersection(row.get("factions", [])):
                rows.append(row)
        if not rows: return "calm", 0
        level = max(rows, key=lambda r: self.REGION_LEVEL_SCORE.get(r.get("level", "calm"), 0))
        score = sum(self.REGION_LEVEL_SCORE.get(r.get("level", "calm"), 0) for r in rows)
        return level.get("level", "calm"), min(15, score)

    def _region_danger_from_security(self, security, base_danger="normal", thresholds=None):
        thresholds = thresholds or {"high": 35, "extreme": 20}
        if security <= int(thresholds.get("extreme", 20)): return "extreme"
        if security <= int(thresholds.get("high", 35)): return "high"
        if base_danger in ("extreme", "high"): return base_danger
        if security < 60: return "dangerous"
        return base_danger if base_danger in ("safe", "normal", "dangerous") else "normal"

    def process_region_ecology(self):
        """把势力冲突映射到具体地图区域；只使用 V12 variables 保存动态结果。"""
        state = self._region_ecology_state()
        clock = self.get_quest_clock()
        changed = []
        from region_activity import get_region_delta, process_crime_pressure, process_natural_recovery, process_external_world_crises
        process_external_world_crises(self, clock)
        process_crime_pressure(self, clock)
        process_natural_recovery(self, clock)
        for zone, info in engine.WORLD_REGIONS.items():
            base = info.get("region_ecology", {}) or {}
            level, tension = self._region_conflict_level(zone)
            effects = info.get("conflict_effects", {}) or {}
            modifier = effects.get(level, {}) or {}
            old = state.get(zone, {}) if isinstance(state.get(zone, {}), dict) else {}
            old_level = str(old.get("level", "calm"))
            activity_delta = get_region_delta(self, zone)
            security = max(0, min(100, int(base.get("security_base", 70)) + int(modifier.get("security", 0)) + activity_delta["security"]))
            commerce = max(0, min(100, int(base.get("commerce_base", 70)) + int(modifier.get("commerce", 0)) + activity_delta["commerce"]))
            travel = max(0, min(100, int(base.get("travel_base", 70)) + int(modifier.get("travel", 0)) + activity_delta["travel"]))
            danger = self._region_danger_from_security(security, info.get("danger", "normal"), info.get("danger_thresholds"))
            state[zone] = {"security": security, "commerce": commerce, "travel": travel, "tension": tension, "danger": danger, "level": level, "last_change": clock}
            if level != old_level:
                changed.append({"zone": zone, "from": old_level, "level": level, "security": security})
                self.learn_player_information(
                    f"region:{zone}", f"{info.get('name', zone)}局势变为【{level}】，安全度约为{security}。",
                    "区域局势", 80 if level in ("conflict", "escalation", "war") else 65, 10, "negative" if level != "calm" else "neutral"
                )
        # Alpha85：地区安全值更新后，再判断是否需要启动官府/守卫治安事件。
        try:
            from region_activity import process_region_security_events
            process_region_security_events(self, clock)
        except (ImportError, TypeError, ValueError):
            pass
        variables = self.world_state.setdefault("variables", {})
        variables["world_region_tension"] = sum(v.get("tension", 0) for v in state.values() if isinstance(v, dict))
        variables["world_region_security"] = {z: int(v.get("security", 0)) for z, v in state.items() if isinstance(v, dict)}
        return changed

    def get_region_exploration_event(self, zone, events):
        """在原有探索事件基础上按区域局势附加数据驱动事件。"""
        info = engine.WORLD_REGIONS.get(zone, {}) or {}
        ecology = self.get_region_ecology(zone)
        candidates = list(events or [])
        for entry in info.get("conflict_events", []) or []:
            if not isinstance(entry, dict): continue
            required = str(entry.get("requires_level", "calm"))
            if self.REGION_LEVEL_SCORE.get(ecology.get("level", "calm"), 0) < self.REGION_LEVEL_SCORE.get(required, 0):
                continue
            candidates.append({"text": entry.get("text", "局势似乎有些不寻常。"), "effects": {"increment_variables": {f"region_event:{zone}": 1}}})
        return candidates

    # ==================== P2.28 NPC 状态生态 ====================
    NPC_STATE_DEFAULT = "normal"
    NPC_STATE_ALLOWED = {"normal", "busy", "injured", "fear", "angry", "away", "event_affected"}
    NPC_INJURY_LEVELS = {"light", "serious", "critical"}

    def _npc_state_map(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("npc_states", {})
        if not isinstance(state, dict):
            state = {}
            variables["npc_states"] = state
        return state

    def _npc_location_map(self):
        variables = self.world_state.setdefault("variables", {})
        locations = variables.setdefault("npc_locations", {})
        if not isinstance(locations, dict):
            locations = {}
            variables["npc_locations"] = locations
        return locations

    def get_npc_home_location(self, npc_name):
        """优先使用 NPC 明确配置的居所；兼容旧数据中仅在场景登记 NPC 的形式。"""
        info = engine.NPCS.get(npc_name, {})
        configured_home = info.get("home_room") if isinstance(info, dict) else None
        if configured_home in engine.ROOMS:
            return configured_home
        for room_id, room in engine.ROOMS.items():
            if npc_name in (room.get("npcs", []) or []):
                return room_id
        return None

    def _peek_npc_state_record(self, npc_name):
        """只读查看临时状态，不写入 world_state；过期状态视为不存在。"""
        variables = self.world_state.get("variables", {}) if isinstance(self.world_state, dict) else {}
        records = variables.get("npc_states", {}) if isinstance(variables, dict) else {}
        raw = records.get(npc_name, {}) if isinstance(records, dict) else {}
        if not isinstance(raw, dict):
            return {}
        try:
            until = raw.get("until_clock")
            if until is not None and self.get_quest_clock() >= int(until):
                return {}
        except (TypeError, ValueError, OverflowError):
            pass
        return dict(raw)

    def _peek_npc_location(self, npc_name):
        """只读查看已记录的实际位置；离场记录返回 None。"""
        variables = self.world_state.get("variables", {}) if isinstance(self.world_state, dict) else {}
        locations = variables.get("npc_locations", {}) if isinstance(variables, dict) else {}
        raw = locations.get(npc_name) if isinstance(locations, dict) else None
        if isinstance(raw, dict):
            if raw.get("offstage"):
                return None
            location = raw.get("location")
        else:
            location = raw
        return location if location in engine.ROOMS else None

    def get_npc_public_state(self, npc_name):
        """只读计算 NPC 当前公开状态；不刷新日程、不移动人物、不写存档。"""
        info = engine.NPCS.get(npc_name)
        if not isinstance(info, dict):
            return None
        state = npc_utility.get_npc_current_state(info, self.get_quest_clock())
        record = self._peek_npc_state_record(npc_name)
        source = str(record.get("source", ""))
        if source not in ("", "schedule") and str(record.get("reason", "")).strip():
            location = self._peek_npc_location(npc_name) or state.get("room_id")
            return {
                "room_id": location,
                "status": str(record.get("reason", "")).strip(),
                "state": str(record.get("state", self.NPC_STATE_DEFAULT)),
                "tier": state.get("tier", ""),
                "offstage": location is None,
                "always_available": state.get("always_available", False),
            }
        return state

    def _npc_schedule_entry(self, npc_name, clock=None):
        info = engine.NPCS.get(npc_name, {})
        schedule = info.get("daily_schedule", []) or []
        if not isinstance(schedule, list):
            return None
        hour = world_hour(self.get_quest_clock() if clock is None else clock)
        for entry in schedule:
            if not isinstance(entry, dict):
                continue
            try:
                start = int(entry.get("start", 0)) % 24
                end = int(entry.get("end", 0)) % 24
            except (TypeError, ValueError):
                continue
            active = (start <= hour < end) if start < end else (hour >= start or hour < end)
            if active:
                return entry
        return None

    def _npc_schedule_location(self, npc_name, entry=None):
        if isinstance(entry, dict):
            location = entry.get("location")
            if location in engine.ROOMS:
                return str(location)
            # 显式写出的 null 表示人物离场（T2 换班/收摊），不能再回落成住址。
            if "location" in entry:
                return None
        return self.get_npc_home_location(npc_name)

    def _npc_on_scheduled_post(self, npc_name, clock=None):
        """NPC 是否正停在当前作息规定的地点；在岗时自主行动不擅自离岗。"""
        entry = self._npc_schedule_entry(npc_name, clock)
        if not isinstance(entry, dict):
            return False
        target = self._npc_schedule_location(npc_name, entry)
        if not target:
            return False
        return self.get_npc_location(npc_name, refresh=False) == target

    def get_npc_daily_activity(self, npc_name):
        """返回人物当前公开的日常活动，用于场景描述；不暴露内部状态标识。"""
        if npc_name not in engine.NPCS:
            return None
        info = engine.NPCS.get(npc_name, {})
        state_record = self._peek_npc_state_record(npc_name)
        if isinstance(state_record, dict) and state_record.get("source") not in (None, "schedule"):
            reason = str(state_record.get("reason", "")).strip()
            if reason:
                return {"reason": reason, "location": self._peek_npc_location(npc_name),
                        "state": str(state_record.get("state", self.NPC_STATE_DEFAULT))}
        utility = self._npc_utility_profile(npc_name)
        if utility.get("enabled") is True:
            record = self._npc_utility_map().get(npc_name, {})
            if isinstance(record, dict) and record.get("reason"):
                try:
                    fresh = 0 <= self.get_quest_clock() - int(record.get("last_clock", -999999)) <= 3
                except (TypeError, ValueError):
                    fresh = False
                if fresh:
                    return {
                        "reason": str(record.get("reason")),
                        "location": self._peek_npc_location(npc_name),
                        "state": self.get_npc_state(npc_name),
                        "action": str(record.get("last_action", "")),
                    }
        public = self.get_npc_public_state(npc_name)
        if isinstance(public, dict):
            reason = str(public.get("status", "")).strip()
            return {
                "reason": reason or "在附近活动",
                "location": public.get("room_id"),
                "state": str(public.get("state", self.NPC_STATE_DEFAULT)),
            }
        home = self.get_npc_home_location(npc_name)
        return {"reason": "在附近活动" if home else "行踪不定", "location": home, "state": self.NPC_STATE_DEFAULT}

    def get_npc_location(self, npc_name, refresh=True):
        if npc_name not in engine.NPCS:
            return None
        if refresh:
            self.refresh_npc_schedules()
        locations = self._npc_location_map()
        raw = locations.get(npc_name)
        if isinstance(raw, dict) and raw.get("offstage"):
            return None
        location = raw.get("location") if isinstance(raw, dict) else raw
        if location in engine.ROOMS:
            return location
        public = self.get_npc_public_state(npc_name)
        if isinstance(public, dict):
            if public.get("offstage"):
                return None
            if public.get("room_id") in engine.ROOMS:
                return str(public.get("room_id"))
        return self.get_npc_home_location(npc_name)

    @staticmethod
    def _npc_room_path(start, goal):
        """仅沿真实 exits 做 BFS，返回从 start 出发的首个 (方向, 房间)；不可达则返回 None。"""
        if start not in engine.ROOMS or goal not in engine.ROOMS or start == goal:
            return None
        queue = [(start, None)]
        visited = {start}
        while queue:
            room_id, first_step = queue.pop(0)
            exits = engine.ROOMS.get(room_id, {}).get("exits", {}) or {}
            for direction, target in exits.items():
                if target not in engine.ROOMS or target in visited:
                    continue
                step = (str(direction), target) if first_step is None else first_step
                if target == goal:
                    return step
                visited.add(target)
                queue.append((target, step))
        return None

    def _queue_npc_movement_message(self, npc_name, old_room, new_room, source=""):
        if not old_room or not new_room or old_room == new_room:
            return
        player_room = self.location
        source_text = str(source or "")
        source_lower = source_text.lower()
        label = actor_display.prose_name(npc_name, engine.NPCS.get(npc_name))
        special = any(token in source_lower for token in ("teleport", "vanish", "disappear", "return", "indoors"))
        if source_text.startswith(("event:", "quest:")) and not special:
            # 事件/任务若恰好移动到真实相邻出口，仍按方向提示；跨房间强制改位则明确视为特殊移动。
            step = self._npc_room_path(old_room, new_room)
            special = not step or step[1] != new_room
        detail = {"kind": "special"}
        if player_room == old_room:
            if special:
                destination = engine.ROOMS.get(new_room, {}).get("name", "")
                if source_lower.startswith(("return", "indoors")):
                    text = f"{label}转身回了{destination}。" if destination else f"{label}转身回去了。"
                elif source_lower.startswith(("vanish", "disappear")):
                    text = f"{label}悄然消失在人群中。"
                elif source_lower.startswith("teleport"):
                    text = f"{label}被传送离开了。"
                else:
                    text = f"{label}离开了这里。"
            else:
                step = self._npc_room_path(old_room, new_room)
                if step:
                    direction, exit_room = step
                    if direction == "上":
                        text = f"{label}上楼去了。"
                        detail = {"kind": "up_out"}
                    elif direction == "下":
                        text = f"{label}下楼去了。"
                        detail = {"kind": "down_out"}
                    else:
                        exit_name = engine.ROOMS.get(exit_room, {}).get("name", "")
                        suffix = f"（{exit_name}）" if exit_name else ""
                        text = f"{label}往{direction}边{suffix}去了。"
                        detail = {"kind": "out", "direction": direction, "place": exit_name}
                else:
                    destination = engine.ROOMS.get(new_room, {}).get("name", "")
                    text = f"{label}前往{destination}了。" if destination else f"{label}离开了这里。"
        elif player_room == new_room:
            if special:
                if source_lower.startswith(("vanish", "disappear")):
                    text = f"{label}突然出现在这里。"
                elif source_lower.startswith("teleport"):
                    text = f"{label}被传送到了这里。"
                else:
                    text = f"{label}来到了这里。"
            else:
                step = self._npc_room_path(new_room, old_room)
                if step:
                    direction, entry_room = step
                    if direction == "下":
                        text = f"{label}从楼下走来。"
                        detail = {"kind": "down_in"}
                    elif direction == "上":
                        text = f"{label}从楼上下来。"
                        detail = {"kind": "up_in"}
                    else:
                        entry_name = engine.ROOMS.get(entry_room, {}).get("name", "")
                        suffix = f"（{entry_name}）" if entry_name else ""
                        text = f"{label}从{direction}边{suffix}走来。"
                        detail = {"kind": "in", "direction": direction, "place": entry_name}
                else:
                    text = f"{label}从远处来到了这里。"
        else:
            return
        if text not in self._pending_npc_movement_messages.values():
            self._pending_npc_movement_messages[npc_name] = text
            detail["text"] = text
            self._pending_npc_movement_details[npc_name] = detail

    def drain_npc_movement_events(self):
        """取出结构化移动事件；文本在 `text`，同类事件可据此合并。"""
        events = []
        for npc_name, text in self._pending_npc_movement_messages.items():
            detail = dict(self._pending_npc_movement_details.get(npc_name, {}))
            detail.setdefault("npc", npc_name)
            detail.setdefault("text", text)
            detail.setdefault("kind", "special")
            events.append(detail)
        self._pending_npc_movement_messages.clear()
        self._pending_npc_movement_details.clear()
        return events

    def drain_npc_movement_messages(self):
        return [event["text"] for event in self.drain_npc_movement_events()]

    def set_npc_location(self, npc_name, location, source="", announce=True):
        if npc_name not in engine.NPCS or location not in engine.ROOMS:
            return False
        locations = self._npc_location_map()
        raw = locations.get(npc_name)
        if isinstance(raw, dict) and raw.get("offstage"):
            old_location = None
        else:
            old_location = raw.get("location") if isinstance(raw, dict) else raw
            if old_location not in engine.ROOMS:
                old_location = self.get_npc_home_location(npc_name)
        record = {"location": location}
        if isinstance(raw, dict) and raw.get("last_schedule_move_clock") is not None:
            # 同一世界时刻内日程已移动过；自主行动再移动时不能丢掉标记，
            # 否则后续 refresh 会把人物按日程拉回，形成一次输入“去/回”两条播报。
            record["last_schedule_move_clock"] = raw.get("last_schedule_move_clock")
        if source:
            record["source"] = str(source)
        locations[npc_name] = record
        if not announce:
            return True
        if old_location is None and self.location == location:
            self._pending_npc_movement_messages[npc_name] = f"{actor_display.prose_name(npc_name, engine.NPCS.get(npc_name))}回到了这里。"
            self._pending_npc_movement_details[npc_name] = {
                "kind": "special", "text": self._pending_npc_movement_messages[npc_name],
            }
        else:
            self._queue_npc_movement_message(npc_name, old_location, location, source)
        return True

    def set_npc_offstage(self, npc_name, source="schedule"):
        """把 NPC 标记为离场；保留状态记录但不占任何场景。"""
        if npc_name not in engine.NPCS:
            return False
        locations = self._npc_location_map()
        raw = locations.get(npc_name)
        if isinstance(raw, dict) and raw.get("offstage"):
            return True
        old_location = raw.get("location") if isinstance(raw, dict) else raw
        locations[npc_name] = {"offstage": True, "source": str(source or "schedule")}
        if old_location in engine.ROOMS and self.location == old_location:
            self._pending_npc_movement_messages[npc_name] = f"{actor_display.prose_name(npc_name, engine.NPCS.get(npc_name))}离开了这里。"
            self._pending_npc_movement_details[npc_name] = {
                "kind": "special", "text": self._pending_npc_movement_messages[npc_name],
            }
        return True

    def get_npcs_in_room(self, room_id=None):
        room_id = room_id or self.location
        if room_id not in engine.ROOMS:
            return []
        result = []
        for npc_name in engine.NPCS:
            if self.get_npc_location(npc_name, refresh=False) == room_id:
                result.append(npc_name)
        # Alpha202：随机路人独立存储，不加入固定 NPC 名册；只对玩家当前场景执行刷新检查。
        if room_id == self.location:
            try:
                import random_npcs
                random_npcs.refresh_current_room(self, room_id)
                result.extend(name for name in random_npcs.get_room_pedestrians(self, room_id) if name not in result)
            except (ImportError, TypeError, ValueError, KeyError):
                # 随机路人配置异常不能阻断旧存档和原有场景人物显示。
                pass
        # 随机路人只属于玩家当前场景。查询地图上的其他房间时，不能把
        # 存档中尚未回收的临时路人显示出来，也不能借查询其他场景触发刷新。
        return result

    # ==================== P2.35 NPC 主动行为与自主行动 ====================
    NPC_AUTONOMY_ALLOWED = {"patrol", "investigate", "meet_npc", "seek_player", "rest"}
    NPC_AUTONOMY_BLOCKED_STATES = {"injured", "fear", "away"}

    def _npc_autonomy_map(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("npc_autonomy", {})
        if not isinstance(state, dict):
            state = {}
            variables["npc_autonomy"] = state
        return state

    def _npc_action_log(self):
        variables = self.world_state.setdefault("variables", {})
        log = variables.setdefault("npc_action_log", [])
        if not isinstance(log, list):
            log = []
            variables["npc_action_log"] = log
        return log

    def _npc_autonomy_profile(self, npc_name):
        info = engine.NPCS.get(npc_name, {})
        profile = info.get("autonomy_profile", {}) or {}
        if not isinstance(profile, dict):
            profile = {}
        return profile

    def get_npc_action_log(self, limit=10):
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 10
        return list(self._npc_action_log()[-limit:])

    def _record_npc_action(self, npc_name, action, reason="", target=None, from_location=None, to_location=None):
        record = {
            "clock": self.get_quest_clock(),
            "npc": str(npc_name),
            "action": str(action),
            "reason": str(reason or "")
        }
        if target:
            record["target"] = str(target)
        if from_location:
            record["from"] = str(from_location)
        if to_location:
            record["to"] = str(to_location)
        log = self._npc_action_log()
        log.append(record)
        del log[:-100]
        return record

    def _npc_autonomy_route(self, npc_name, profile=None):
        profile = profile or self._npc_autonomy_profile(npc_name)
        route = []
        for room_id in profile.get("route", []) or []:
            if room_id in engine.ROOMS and room_id not in route:
                route.append(room_id)
        if not route:
            home = self.get_npc_home_location(npc_name)
            if home:
                route.append(home)
            for entry in engine.NPCS.get(npc_name, {}).get("daily_schedule", []) or []:
                room_id = entry.get("location")
                if room_id in engine.ROOMS and room_id not in route:
                    route.append(room_id)
        return route

    def _npc_autonomy_due(self, npc_name, profile, clock):
        state = self._npc_autonomy_map().get(npc_name, {})
        if not isinstance(state, dict):
            state = {}
        try:
            interval = max(1, int(profile.get("interval", 3)))
            last = int(state.get("last_action_clock", -999999))
        except (TypeError, ValueError):
            interval, last = 3, -999999
        return clock - last >= interval

    def _npc_autonomy_choose_action(self, npc_name, profile, clock):
        allowed = [x for x in (profile.get("allowed_actions", []) or []) if x in self.NPC_AUTONOMY_ALLOWED]
        if not allowed:
            return "rest"
        blocked = set(profile.get("blocked_states", []) or []) | self.NPC_AUTONOMY_BLOCKED_STATES
        if self.get_npc_state(npc_name) in blocked:
            return "rest"

        memory_behavior = self.get_npc_memory_behavior(npc_name).get("action", "neutral")
        min_relation = int(profile.get("seek_player_min_relation", 30) or 30)
        seek_behaviors = set(profile.get("seek_player_memory_behaviors", ["welcome", "cooperate"]) or [])
        if ("seek_player" in allowed and self.location != self.get_npc_location(npc_name)
                and self.get_relation(npc_name) >= min_relation and memory_behavior in seek_behaviors):
            frequency = max(1, int(profile.get("seek_player_frequency", 5) or 5))
            stable = sum(ord(c) for c in npc_name) + clock
            if stable % frequency == 0:
                return "seek_player"

        bonds = engine.NPCS.get(npc_name, {}).get("npc_bonds", {}) or {}
        if "meet_npc" in allowed and bonds:
            if (sum(ord(c) for c in npc_name) + clock) % max(2, int(profile.get("meet_frequency", 4) or 4)) == 0:
                return "meet_npc"
        route = self._npc_autonomy_route(npc_name, profile)
        if "patrol" in allowed and len(route) > 1:
            return "patrol"
        if "investigate" in allowed:
            return "investigate"
        return "rest"

    # ==================== P2.35b NPC 效用行为层 ====================
    def _npc_utility_profile(self, npc_name):
        info = engine.NPCS.get(npc_name, {})
        profile = info.get("utility_profile", {}) if isinstance(info, dict) else {}
        return profile if isinstance(profile, dict) else {}

    def _npc_utility_map(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("npc_utility", {})
        if not isinstance(state, dict):
            state = {}
            variables["npc_utility"] = state
        return state

    def _npc_behavior_map(self):
        variables = self.world_state.setdefault("variables", {})
        records = variables.setdefault("npc_behaviors", {})
        if not isinstance(records, dict):
            records = {}
            variables["npc_behaviors"] = records
        return records

    def get_npc_behavior(self, npc_name):
        """只读返回写 tick 记录的微行为；没有记录时返回 None。"""
        variables = self.world_state.get("variables", {}) if isinstance(self.world_state, dict) else {}
        records = variables.get("npc_behaviors", {}) if isinstance(variables, dict) else {}
        record = records.get(npc_name) if isinstance(records, dict) else None
        return dict(record) if isinstance(record, dict) else None

    def sync_npc_behaviors(self, action_records=None):
        """写 tick 结算：只记录未被日程覆盖的 NPC 微行为。

        daily_schedule 优先；本方法不移动人物、不播报，也不改变只读展示。
        """
        actions = {}
        for record in action_records or []:
            if isinstance(record, dict) and record.get("npc"):
                actions[str(record["npc"])] = record
        clock = self.get_quest_clock()
        behaviors = self._npc_behavior_map()
        for npc_name, info in engine.NPCS.items():
            if not isinstance(info, dict):
                continue
            if npc_utility.active_schedule_entry(info.get("daily_schedule"), clock) is not None:
                continue
            action = actions.get(npc_name, {})
            context = {}
            if action:
                context["action"] = action.get("action", "")
                context["interacting"] = action.get("action") in ("talk", "interact")
            behavior = npc_behavior.choose_behavior(info, clock, context)
            behaviors[npc_name] = {"behavior": behavior, "clock": clock}
        return behaviors

    def _npc_quest_anchor_names(self):
        """任务发布、交付与对话目标人物属于固定锚点，不参与自由游荡。"""
        names = set()
        for info in engine.QUESTS.values():
            if not isinstance(info, dict):
                continue
            for key in ("npc", "turn_in_npc"):
                if info.get(key):
                    names.add(str(info[key]))
            if info.get("target_type") == "talk" and info.get("target_name"):
                names.add(str(info["target_name"]))
            for stage in info.get("stages", []) or []:
                if (isinstance(stage, dict) and stage.get("target_type") == "talk"
                        and stage.get("target_name")):
                    names.add(str(stage["target_name"]))
        return names

    def _npc_utility_work_hours_ok(self, profile, clock):
        hours = profile.get("work_hours")
        if not isinstance(hours, list) or len(hours) != 2:
            return True
        try:
            from economy.manager import _within_work_hours
        except ImportError:
            return True
        return _within_work_hours(hours, clock)

    def _npc_utility_bond_target(self, npc_name):
        bonds = engine.NPCS.get(npc_name, {}).get("npc_bonds", {}) or {}
        best_target, best_strength = None, 0
        for target, strength in bonds.items():
            if target not in engine.NPCS:
                continue
            value = _safe_int_value(strength, 0)
            if value > best_strength:
                best_target, best_strength = str(target), value
        return best_target, best_strength

    def _npc_utility_context(self, npc_name, profile, clock, needs):
        info = engine.NPCS.get(npc_name, {})
        location = self.get_npc_location(npc_name, refresh=False)
        entry = self._npc_schedule_entry(npc_name, clock)
        schedule_room = self._npc_schedule_location(npc_name, entry) if entry else None
        schedule_state = str(entry.get("state", self.NPC_STATE_DEFAULT)) if entry else self.NPC_STATE_DEFAULT
        schedule_reason = str(entry.get("reason", "")) if entry else ""
        home = self.get_npc_home_location(npc_name)

        work_room = profile.get("work_room")
        if work_room not in engine.ROOMS:
            work_room = None
        meal_room = profile.get("meal_room")
        if meal_room not in engine.ROOMS:
            meal_room = None
        social_room = profile.get("social_room")
        if social_room not in engine.ROOMS:
            social_room = None
        meal_hours = profile.get("meal_hours", list(npc_utility.DEFAULT_MEAL_HOURS))
        if not isinstance(meal_hours, list):
            meal_hours = list(npc_utility.DEFAULT_MEAL_HOURS)
        hour = world_hour(clock)
        meal_tokens = ("吃", "饭", "食", "歇息")
        meal_allowed = bool(
            meal_room and hour in {_safe_int_value(value, -1) for value in meal_hours}
            and (not schedule_room or schedule_room == meal_room
                 or any(token in schedule_reason for token in meal_tokens))
        )

        bond_target, bond_strength = self._npc_utility_bond_target(npc_name)
        autonomy = info.get("autonomy_profile", {}) if isinstance(info, dict) else {}
        route = self._npc_autonomy_route(npc_name, autonomy if isinstance(autonomy, dict) else {})
        security = 70
        zone = str((engine.ROOMS.get(location, {}) or {}).get("zone", "main"))
        try:
            ecology = self.get_region_ecology(zone)
            if isinstance(ecology, dict):
                security = _safe_int_value(ecology.get("security", 70), 70)
        except (TypeError, ValueError, AttributeError):
            pass

        blocked_states = profile.get("blocked_states", [])
        if not isinstance(blocked_states, list):
            blocked_states = []
        allowed_actions = profile.get("allowed_actions", list(npc_utility.DEFAULT_ALLOWED_ACTIONS))
        if not isinstance(allowed_actions, list):
            allowed_actions = list(npc_utility.DEFAULT_ALLOWED_ACTIONS)
        return {
            "name": str(npc_name),
            "clock": clock,
            "hour": hour,
            "location": location,
            "home": home,
            "state": self.get_npc_state(npc_name),
            "blocked_states": blocked_states,
            "allowed_actions": allowed_actions,
            "anchor": npc_name in self._npc_quest_anchor_names(),
            "schedule_room": schedule_room,
            "schedule_state": schedule_state,
            "schedule_reason": schedule_reason,
            "work_room": work_room,
            "work_hours_ok": self._npc_utility_work_hours_ok(profile, clock),
            "meal_room": meal_room,
            "meal_allowed": meal_allowed,
            "social_room": social_room,
            "route": route,
            "security": security,
            "relation": self.get_relation(npc_name),
            "memory_behavior": self.get_npc_memory_behavior(npc_name).get("action", "neutral"),
            "seek_player_min_relation": _safe_int_value(
                profile.get("seek_player_min_relation", 30), 30),
            "seek_player_memory_behaviors": profile.get(
                "seek_player_memory_behaviors", ["welcome", "cooperate"]),
            "player_location": self.location,
            "bond_target": bond_target,
            "bond_strength": bond_strength,
            "needs": needs,
        }

    def _npc_utility_due(self, npc_name, profile, clock):
        record = self._npc_utility_map().get(npc_name, {})
        if not isinstance(record, dict):
            record = {}
        interval = max(1, _safe_int_value(profile.get("interval", 2), 2))
        last = _safe_int_value(record.get("last_clock"), -999999)
        return clock - last >= interval

    def _npc_utility_decide(self, npc_name, profile, clock):
        record = self._npc_utility_map().get(npc_name, {})
        if not isinstance(record, dict):
            record = {}
        elapsed = clock - _safe_int_value(record.get("last_clock"), clock)
        needs = npc_utility.advance_needs(
            record.get("needs"), elapsed, record.get("last_action", ""))
        context = self._npc_utility_context(npc_name, profile, clock, needs)
        decision = npc_utility.choose_action(context)
        decision["needs"] = needs
        return decision

    def _npc_utility_record(self, npc_name, decision, clock):
        state = self._npc_utility_map()
        state[npc_name] = {
            "last_clock": clock,
            "last_action": str(decision.get("action", "investigate")),
            "last_score": decision.get("score", 0),
            "target": decision.get("target") or "",
            "reason": str(decision.get("reason", "")),
            "needs": decision.get("needs", {}),
        }

    def _execute_npc_utility_action(self, npc_name, decision):
        action = str(decision.get("action", "investigate"))
        if action in ("patrol", "seek_player", "meet_npc"):
            return self._execute_npc_autonomous_action(npc_name, action)
        reason = str(decision.get("reason", ""))
        current = self.get_npc_location(npc_name, refresh=False)
        target = decision.get("target")
        if target not in engine.ROOMS or target == current:
            return self._record_npc_action(npc_name, action, reason, None, current, current)
        if self._npc_on_scheduled_post(npc_name):
            # 在岗时以作息地点为准，效用行动只在原地留意，避免与日程来回拉扯。
            return self._record_npc_action(
                npc_name, action, "在岗处理营生，暂不离开值守地点", target, current, current)
        step = self._npc_room_path(current, target)
        next_room = step[1] if step else current
        if next_room != current:
            self.set_npc_location(npc_name, next_room, source=f"utility:{action}")
        return self._record_npc_action(npc_name, action, reason, None, current, next_room)

    def _npc_autonomy_meet_target(self, npc_name):
        bonds = engine.NPCS.get(npc_name, {}).get("npc_bonds", {}) or {}
        candidates = []
        for target, strength in bonds.items():
            if target not in engine.NPCS:
                continue
            try:
                strength = int(strength)
            except (TypeError, ValueError):
                strength = 0
            faction_bonus = 0
            source_faction = self.get_npc_faction(npc_name)
            target_faction = self.get_npc_faction(target)
            if source_faction and target_faction:
                faction_bonus = self.get_faction_relation(source_faction, target_faction)
            candidates.append((strength * 2 + faction_bonus, strength, target))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], -x[1], x[2]))
        return candidates[0][2]

    def _execute_npc_autonomous_action(self, npc_name, action):
        profile = self._npc_autonomy_profile(npc_name)
        current = self.get_npc_location(npc_name, refresh=False)
        on_post = self._npc_on_scheduled_post(npc_name)
        if action == "patrol":
            route = self._npc_autonomy_route(npc_name, profile)
            if len(route) < 2:
                action = "investigate"
            else:
                try:
                    index = route.index(current)
                except ValueError:
                    index = -1
                target = route[(index + 1) % len(route)]
                if target != current:
                    step = self._npc_room_path(current, target)
                    target = step[1] if step else current
                if target != current:
                    if on_post:
                        # 在岗人物原地留意四周，不离开作息规定的地点；
                        # 治安贡献仍按冷却记录，避免与日程来回拉扯。
                        try:
                            from region_activity import record_patrol
                            record_patrol(self, npc_name, current)
                        except (ImportError, TypeError, ValueError):
                            pass
                        return self._record_npc_action(
                            npc_name, "patrol", "在岗巡看四周，暂不离开值守地点", None, current, current)
                    self.set_npc_location(npc_name, target, source="autonomy:patrol")
                    # Alpha84：配置表中的官府/守卫角色巡逻时，会为所在地区提供有限治安贡献。
                    try:
                        from region_activity import record_patrol
                        record_patrol(self, npc_name, target)
                    except (ImportError, TypeError, ValueError):
                        pass
                    return self._record_npc_action(npc_name, "patrol", "按巡行路线巡查当地治安", None, current, target)
        if action == "meet_npc":
            target_npc = self._npc_autonomy_meet_target(npc_name)
            if target_npc:
                target_room = self.get_npc_location(target_npc, refresh=False)
                if target_room:
                    step = self._npc_room_path(current, target_room)
                    next_room = step[1] if step else current
                    if next_room != current:
                        if on_post:
                            return self._record_npc_action(
                                npc_name, "meet_npc", f"值守在岗，与{target_npc}的会面暂缓", target_npc, current, current)
                        self.set_npc_location(npc_name, next_room, source="autonomy:meet")
                    return self._record_npc_action(npc_name, "meet_npc", "沿场景出口前往与关系网络中的人物会面", target_npc, current, next_room)
            action = "investigate"
        if action == "seek_player":
            target_room = self.location
            step = self._npc_room_path(current, target_room)
            next_room = step[1] if step else current
            if next_room != current:
                if on_post:
                    return self._record_npc_action(
                        npc_name, "seek_player", "值守在岗，只在原地留意玩家动向", self.name, current, current)
                self.set_npc_location(npc_name, next_room, source="autonomy:seek_player")
            return self._record_npc_action(npc_name, "seek_player", "沿场景出口主动寻找玩家", self.name, current, next_room)
        if action == "investigate":
            return self._record_npc_action(npc_name, "investigate", "观察当前区域并留意异常", None, current, current)
        return self._record_npc_action(npc_name, "rest", "当前状态或行为条件不适合主动行动", None, current, current)

    def _npc_proactive_log(self):
        variables = self.world_state.setdefault("variables", {})
        log = variables.setdefault("npc_proactive_events", [])
        if not isinstance(log, list):
            log = []
            variables["npc_proactive_events"] = log
        return log

    def get_npc_proactive_event_log(self, limit=10):
        try:
            limit = max(1, min(100, int(limit)))
        except (TypeError, ValueError):
            limit = 10
        return list(self._npc_proactive_log()[-limit:])

    def _npc_proactive_profiles(self, npc_name):
        profile = engine.NPCS.get(npc_name, {}).get("proactive_events", []) or []
        return profile if isinstance(profile, list) else []

    def _npc_proactive_event_allowed(self, npc_name, event, action_record):
        if not isinstance(event, dict):
            return False
        trigger = event.get("trigger_action")
        if trigger and trigger != action_record.get("action"):
            return False
        if not engine.check_conditions(event.get("requires"), self.world_state, self.completed_quests, self):
            return False
        min_relation = event.get("min_relation")
        if min_relation is not None and self.get_relation(npc_name) < int(min_relation):
            return False
        behaviors = event.get("memory_behaviors")
        if behaviors:
            behavior = self.get_npc_memory_behavior(npc_name).get("action", "neutral")
            if behavior not in set(behaviors):
                return False
        cooldown = max(0, int(event.get("cooldown", 0) or 0))
        state = self._npc_autonomy_map().get(npc_name, {})
        history = state.get("proactive_events", {}) if isinstance(state, dict) else {}
        if cooldown and isinstance(history, dict):
            last = history.get(str(event.get("id", "")), -999999)
            try:
                if self.get_quest_clock() - int(last) < cooldown:
                    return False
            except (TypeError, ValueError):
                pass
        return True

    def _apply_npc_proactive_event(self, npc_name, event, action_record):
        event_id = str(event.get("id", ""))
        text = str(event.get("text", event.get("title", "人物主动引发了一件事情。")))
        effects = event.get("effects", {}) or {}
        engine.apply_world_effects(self.world_state, effects)
        for entry in effects.get("npc_information", []) or []:
            if not isinstance(entry, dict) or entry.get("npc") not in engine.NPCS or not entry.get("topic"):
                continue
            self.learn_npc_information(
                entry["npc"], entry["topic"], entry.get("text", ""), entry.get("source", npc_name),
                entry.get("confidence", 70), entry.get("ttl", 0), entry.get("sentiment", "neutral"), entry.get("follow_up")
            )
        for entry in effects.get("player_information", []) or []:
            if not isinstance(entry, dict) or not entry.get("topic"):
                continue
            self.learn_player_information(
                entry["topic"], entry.get("text", text), entry.get("source", npc_name),
                entry.get("confidence", 75), entry.get("ttl", 0), entry.get("sentiment", "neutral"), entry.get("follow_up")
            )
        for target, delta in (effects.get("relations", {}) or {}).items():
            self.change_relation(target, delta)
        reactions = effects.get("npc_reactions", []) or []
        if isinstance(reactions, list):
            self._apply_npc_reactions(reactions, f"npc:{npc_name}:{event_id}")
        memory = event.get("remember_player_action")
        if isinstance(memory, dict) and memory.get("npc") in engine.NPCS:
            self.remember_player_action(
                memory["npc"], memory.get("id", f"npc_event:{event_id}"),
                memory.get("text", text), memory.get("sentiment", "neutral"),
                memory.get("strength", 45), memory.get("ttl", 0), event_type="npc_event"
            )
        record = {
            "clock": self.get_quest_clock(),
            "event_id": event_id,
            "npc": str(npc_name),
            "action": str(action_record.get("action", "")),
            "title": str(event.get("title", event_id)),
            "text": text,
        }
        if action_record.get("target"):
            record["target"] = str(action_record["target"])
        log = self._npc_proactive_log()
        log.append(record)
        del log[:-100]
        state = self._npc_autonomy_map().setdefault(npc_name, {})
        history = state.setdefault("proactive_events", {})
        history[event_id] = self.get_quest_clock()
        return record

    def process_npc_proactive_events(self, action_records=None):
        """将 NPC 自主行动进一步转化为数据驱动的主动剧情事件。"""
        action_records = action_records if action_records is not None else []
        results = []
        for action_record in action_records:
            npc_name = action_record.get("npc")
            if npc_name not in engine.NPCS:
                continue
            for event in self._npc_proactive_profiles(npc_name):
                if not self._npc_proactive_event_allowed(npc_name, event, action_record):
                    continue
                results.append(self._apply_npc_proactive_event(npc_name, event, action_record))
                break
        return results

    def process_npc_autonomy(self):
        """按世界时钟推进 NPC 自主行动，并处理由行动触发的主动剧情事件。"""
        clock = self.get_quest_clock()
        self.refresh_npc_schedules()
        results = []
        autonomy = self._npc_autonomy_map()
        for npc_name in engine.NPCS:
            profile = self._npc_autonomy_profile(npc_name)
            utility = self._npc_utility_profile(npc_name)
            if utility.get("enabled") is True:
                if not self._npc_utility_due(npc_name, utility, clock):
                    continue
                decision = self._npc_utility_decide(npc_name, utility, clock)
                result = self._execute_npc_utility_action(npc_name, decision)
                self._npc_utility_record(npc_name, decision, clock)
                action = str(decision.get("action", "investigate"))
            else:
                if profile.get("enabled", False) is not True or not self._npc_autonomy_due(npc_name, profile, clock):
                    continue
                action = self._npc_autonomy_choose_action(npc_name, profile, clock)
                result = self._execute_npc_autonomous_action(npc_name, action)
            autonomy[npc_name] = {
                "last_action_clock": clock,
                "last_action": result.get("action", action),
                "target": result.get("target", ""),
                "location": result.get("to", self.get_npc_location(npc_name, refresh=False)),
                "proactive_events": autonomy.get(npc_name, {}).get("proactive_events", {}),
            }
            results.append(result)
        self.sync_npc_behaviors(results)
        self.process_npc_proactive_events(results)
        self.process_npc_proactive_quests(results)
        self.process_npc_competitions()
        return results

    # ==================== P2.37 NPC 主动任务与动态剧情链 ====================
    def _npc_proactive_quest_profiles(self, npc_name):
        profile = engine.NPCS.get(npc_name, {}).get("proactive_quests", []) or []
        return profile if isinstance(profile, list) else []

    def _npc_proactive_quest_history(self, npc_name):
        state = self._npc_autonomy_map().setdefault(npc_name, {})
        history = state.setdefault("proactive_quests", {})
        if not isinstance(history, dict):
            history = {}
            state["proactive_quests"] = history
        return history

    def _proactive_quest_allowed(self, npc_name, profile, action_record=None):
        if not isinstance(profile, dict):
            return False
        q_name = profile.get("quest")
        if not q_name or q_name not in engine.QUESTS:
            return False
        trigger = profile.get("trigger_action")
        if trigger and action_record and trigger != action_record.get("action"):
            return False
        if not engine.check_conditions(profile.get("requires"), self.world_state, self.completed_quests, self):
            return False
        min_relation = profile.get("min_relation")
        if min_relation is not None and self.get_relation(npc_name) < int(min_relation):
            return False
        behaviors = profile.get("memory_behaviors")
        if behaviors:
            behavior = self.get_npc_memory_behavior(npc_name).get("action", "neutral")
            if behavior not in set(behaviors):
                return False
        if q_name in self.active_quests:
            return False
        if q_name in self.completed_quests and not engine.QUESTS[q_name].get("repeatable", False):
            return False
        if self.get_flag(f"quest_failed:{q_name}") and not engine.QUESTS[q_name].get("retryable", True):
            return False
        cooldown = max(0, int(profile.get("cooldown", 0) or 0))
        history = self._npc_proactive_quest_history(npc_name)
        if cooldown and q_name in history:
            try:
                if self.get_quest_clock() - int(history[q_name]) < cooldown:
                    return False
            except (TypeError, ValueError):
                pass
        return True

    def _offer_npc_proactive_quest(self, npc_name, profile, action_record=None):
        q_name = str(profile.get("quest"))
        q_info = engine.QUESTS.get(q_name, {})
        if not self._proactive_quest_allowed(npc_name, profile, action_record):
            return None
        self.active_quests[q_name] = 0
        self.quest_states[q_name] = {
            "stage": 0,
            "progress": 0,
            "accepted_at": self.get_quest_clock(),
            "accepted_by_npc": npc_name,
            "proactive": True,
        }
        engine.apply_world_effects(self.world_state, q_info.get("on_accept"))
        self.set_flag(f"quest_active:{q_name}", True)
        history = self._npc_proactive_quest_history(npc_name)
        history[q_name] = self.get_quest_clock()
        record = {
            "clock": self.get_quest_clock(),
            "npc": npc_name,
            "quest": q_name,
            "action": str((action_record or {}).get("action", "")),
            "title": str(q_info.get("title", q_name)),
            "text": str(profile.get("text", f"{actor_display.prose_name(npc_name, engine.NPCS.get(npc_name))} 主动找到你，请你协助处理【{engine.quest_display_name(q_name)}】。")),
            "type": "offer",
        }
        log = self._npc_proactive_log()
        log.append(record)
        del log[:-100]
        info = profile.get("player_information")
        if isinstance(info, dict) and info.get("topic"):
            self.learn_player_information(
                info["topic"], info.get("text", record["text"]), info.get("source", npc_name),
                info.get("confidence", 80), info.get("ttl", 0), info.get("sentiment", "neutral"), info.get("follow_up")
            )
        return record

    def _advance_npc_proactive_quest(self, npc_name, profile, q_name):
        if q_name not in self.active_quests:
            return None
        if not profile.get("advance_stage"):
            return None
        state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": 0})
        q_info = engine.QUESTS.get(q_name, {})
        stages = q_info.get("stages") or []
        if not stages or state.get("branch_pending"):
            # NPC 自主推进不得越过必须由玩家决定的剧情路线。
            return None
        current = int(state.get("stage", 0) or 0)
        if current >= len(stages) - 1:
            return None
        state["stage"] = current + 1
        state["progress"] = 0
        self.active_quests[q_name] = 0
        stage = stages[state["stage"]]
        engine.apply_world_effects(self.world_state, stage.get("effects"))
        record = {
            "clock": self.get_quest_clock(),
            "npc": npc_name,
            "quest": q_name,
            "action": "advance_quest",
            "title": str(q_info.get("title", q_name)),
            "text": str(profile.get("advance_text", f"{actor_display.prose_name(npc_name, engine.NPCS.get(npc_name))} 已替你推进【{engine.quest_display_name(q_name)}】的调查。")),
            "type": "advance",
            "stage": state["stage"],
        }
        log = self._npc_proactive_log()
        log.append(record)
        del log[:-100]
        return record

    def _check_npc_proactive_quest_failures(self):
        failed = []
        clock = self.get_quest_clock()
        for npc_name in engine.NPCS:
            for profile in self._npc_proactive_quest_profiles(npc_name):
                q_name = profile.get("quest")
                if q_name not in self.active_quests:
                    continue
                limit = profile.get("fail_after")
                if limit is None:
                    continue
                state = self.quest_states.get(q_name, {})
                try:
                    if clock - int(state.get("accepted_at", clock)) < int(limit):
                        continue
                except (TypeError, ValueError):
                    continue
                if not state.get("proactive"):
                    continue
                if self.fail_quest(q_name, "npc_proactive_timeout"):
                    failed.append(q_name)
                    record = {
                        "clock": clock, "npc": npc_name, "quest": q_name,
                        "action": "fail_quest", "title": str(engine.QUESTS.get(q_name, {}).get("title", q_name)),
                        "text": str(profile.get("fail_text", f"【{engine.quest_display_name(q_name)}】因迟迟无人处理而恶化，任务失败。")),
                        "type": "fail",
                    }
                    log = self._npc_proactive_log(); log.append(record); del log[:-100]
        return failed

    def process_npc_proactive_quests(self, action_records=None):
        """让 NPC 自主行动触发/推进现有任务，形成动态剧情链。"""
        action_records = action_records or []
        results = []
        for action_record in action_records:
            npc_name = action_record.get("npc")
            if npc_name not in engine.NPCS:
                continue
            for profile in self._npc_proactive_quest_profiles(npc_name):
                q_name = profile.get("quest")
                if self._proactive_quest_allowed(npc_name, profile, action_record):
                    offered = self._offer_npc_proactive_quest(npc_name, profile, action_record)
                    if offered:
                        results.append(offered)
                        break
                if q_name in self.active_quests and profile.get("advance_stage"):
                    advanced = self._advance_npc_proactive_quest(npc_name, profile, q_name)
                    if advanced:
                        results.append(advanced)
                        break
        results.extend({"quest": q, "type": "fail"} for q in self._check_npc_proactive_quest_failures())
        return results

    # ==================== P2.40 NPC 多方竞争与任务博弈 ====================
    def _quest_competition_history(self):
        variables = self.world_state.setdefault("variables", {})
        history = variables.setdefault("quest_competitions", {})
        if not isinstance(history, dict):
            history = {}
            variables["quest_competitions"] = history
        return history

    def _npc_competition_score(self, contestant, contestants=None):
        npc = contestant.get("npc")
        score = float(contestant.get("base_score", 0) or 0)
        score += self.get_relation(npc) * float(contestant.get("relation_weight", 0) or 0)
        score += self.get_npc_player_reputation(npc) * float(contestant.get("memory_weight", 0) or 0)
        if contestant.get("requires") and not engine.check_conditions(contestant.get("requires"), self.world_state, self.completed_quests, self):
            return None
        if contestant.get("min_relation") is not None and self.get_relation(npc) < int(contestant["min_relation"]):
            return None
        if contestant.get("priority") is not None:
            score += float(contestant.get("priority", 0) or 0) * 0.01
        faction = self.get_npc_faction(npc)
        if faction and contestants:
            faction_weight = float(contestant.get("faction_weight", 0) or 0)
            for other in contestants:
                other_npc = other.get("npc")
                other_faction = self.get_npc_faction(other_npc)
                if other_faction and other_faction != faction:
                    score += self.get_faction_relation(faction, other_faction) * faction_weight
            score += self.get_faction_influence(faction) * float(contestant.get("influence_weight", 0) or 0)
        return score

    def _apply_npc_competition(self, q_name, profile):
        contestants = profile.get("contestants") or []
        scored=[]
        for contestant in contestants:
            if not isinstance(contestant, dict) or contestant.get("npc") not in engine.NPCS:
                continue
            score=self._npc_competition_score(contestant, contestants)
            if score is not None:
                scored.append((score, int(contestant.get("priority", 0) or 0), str(contestant.get("npc")), contestant))
        if not scored:
            return None
        scored.sort(key=lambda x:(x[0],x[1],x[2]), reverse=True)
        _, _, _, winner=scored[0]
        action=str(winner.get("action","world_intervention")); state=self.quest_states.get(q_name,{})
        if action not in ("advance_stage", "reroute", "world_intervention"):
            return None
        result={"quest":q_name,"type":"competition","competition":str(profile.get("id","")),"npc":str(winner["npc"]),"action":action,"scores":{x[2]:round(x[0],2) for x in scored}}
        # 竞争不能替玩家决定待选路线；无效目标也不能先写入世界效果。
        target = None
        if action in ("advance_stage", "reroute"):
            stages=engine.QUESTS.get(q_name,{}).get("stages") or []
            try:
                target=int(winner.get("next_stage",int(state.get("stage",0))+1))
            except (TypeError, ValueError, OverflowError):
                return None
            if not stages or target<0 or target>=len(stages): return None
            if state.get("branch_pending"): return None
        engine.apply_world_effects(self.world_state, winner.get("effects") or {})
        if action in ("advance_stage","reroute"):
            state["stage"]=target; state["progress"]=0; self.active_quests[q_name]=0; state.pop("branch_pending",None)
            result["stage"]=target
        memory=winner.get("memory")
        if isinstance(memory,dict) and memory.get("npc") in engine.NPCS:
            mn=memory["npc"]
        else: mn=winner.get("npc")
        if isinstance(memory,dict):
            self.remember_player_action(mn,memory.get("id",f"competition:{q_name}:{profile.get('id','')}"),memory.get("text",profile.get("text","竞争结果已改变任务局势。")),memory.get("sentiment","neutral"),memory.get("strength",40),memory.get("ttl",0),event_type="npc_competition")
        key=f"{q_name}:{profile.get('id','')}"; self._quest_competition_history()[key]=self.get_quest_clock()
        result["text"]=str(profile.get("text",f"{winner['npc']} 在竞争中抢得先机。"))
        log=self._npc_proactive_log(); log.append(dict(result,clock=self.get_quest_clock())); del log[:-100]
        return result

    def process_npc_competitions(self):
        results=[]
        history=self._quest_competition_history(); clock=self.get_quest_clock()
        for q_name in list(self.active_quests.keys()):
            q_info=engine.QUESTS.get(q_name,{})
            for profile in q_info.get("npc_competitions",[]) or []:
                if not isinstance(profile,dict): continue
                state=self.quest_states.get(q_name,{})
                if profile.get("stage") is not None and int(state.get("stage",0))!=int(profile["stage"]): continue
                if profile.get("branch") and state.get("branch")!=profile.get("branch"): continue
                if not engine.check_conditions(profile.get("requires"),self.world_state,self.completed_quests,self): continue
                accepted=int(state.get("accepted_at",clock) or 0)
                if clock-accepted<max(0,int(profile.get("delay",0) or 0)): continue
                key=f"{q_name}:{profile.get('id','')}"; last=history.get(key)
                if profile.get("once",True) and last is not None: continue
                result=self._apply_npc_competition(q_name,profile)
                if result: results.append(result)
        return results

    # ==================== P2.39 NPC/世界主动干预任务链 ====================
    def _quest_intervention_history(self):
        variables = self.world_state.setdefault("variables", {})
        history = variables.setdefault("quest_interventions", {})
        if not isinstance(history, dict):
            history = {}
            variables["quest_interventions"] = history
        return history

    def _quest_intervention_allowed(self, q_name, profile):
        if not isinstance(profile, dict) or q_name not in self.active_quests:
            return False
        state = self.quest_states.get(q_name, {})
        if state.get("branch_pending") and not profile.get("allow_branch_pending", False):
            return False
        stage = profile.get("stage")
        if stage is not None and int(state.get("stage", 0) or 0) != int(stage):
            return False
        branch = profile.get("branch")
        if branch and state.get("branch") != branch:
            return False
        if not engine.check_conditions(profile.get("requires"), self.world_state, self.completed_quests, self):
            return False
        actor = profile.get("npc")
        if actor and actor in engine.NPCS:
            min_relation = profile.get("min_relation")
            if min_relation is not None and self.get_relation(actor) < int(min_relation):
                return False
        accepted_at = int(state.get("accepted_at", self.get_quest_clock()) or 0)
        if self.get_quest_clock() - accepted_at < max(0, int(profile.get("delay", 0) or 0)):
            return False
        key = f"{q_name}:{profile.get('id', '')}"
        history = self._quest_intervention_history()
        last = history.get(key)
        if profile.get("once", True) and last is not None:
            return False
        cooldown = max(0, int(profile.get("cooldown", 0) or 0))
        if cooldown and last is not None:
            try:
                if self.get_quest_clock() - int(last) < cooldown:
                    return False
            except (TypeError, ValueError):
                pass
        return True

    def _apply_quest_intervention(self, q_name, profile):
        state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": self.active_quests.get(q_name, 0)})
        q_info = engine.QUESTS.get(q_name, {})
        action = str(profile.get("action", "world_intervention"))
        actor = str(profile.get("npc", "世界"))
        # 先验证动作与目标阶段，再执行任何世界效果，避免无效配置留下半套状态变化。
        if action not in ("advance_stage", "reroute", "fail_quest", "complete_stage", "world_intervention"):
            return None
        target_stage = None
        if action in ("advance_stage", "reroute"):
            stages = q_info.get("stages") or []
            try:
                target_stage = int(profile.get("next_stage", int(state.get("stage", 0) or 0) + 1))
            except (TypeError, ValueError, OverflowError):
                return None
            if not stages or target_stage < 0 or target_stage >= len(stages):
                return None
            if state.get("branch_pending"):
                return None
        if action == "complete_stage":
            stages = q_info.get("stages") or []
            try:
                current_stage = int(state.get("stage", 0) or 0)
            except (TypeError, ValueError, OverflowError):
                return None
            if not stages or current_stage < 0 or current_stage >= len(stages):
                return None
            if state.get("branch_pending"):
                return None
        effects = profile.get("effects") or {}
        result = {"quest": q_name, "npc": actor, "action": action, "type": "intervention"}
        engine.apply_world_effects(self.world_state, effects)
        if action in ("advance_stage", "reroute"):
            stages = q_info.get("stages") or []
            state["stage"] = target_stage
            state["progress"] = 0
            self.active_quests[q_name] = 0
            state.pop("branch_pending", None)
            if profile.get("branch"):
                state["branch"] = str(profile["branch"])
            result["stage"] = target_stage
        elif action == "fail_quest":
            if not self.fail_quest(q_name, str(profile.get("reason", "npc_intervention"))):
                return None
            result["failed"] = True
        elif action == "complete_stage":
            result["stage"] = int(state.get("stage", 0) or 0)
            state["progress"] = int((q_info.get("stages") or [])[result["stage"]].get("required_cnt", 1))
            self.active_quests[q_name] = state["progress"]
        key = f"{q_name}:{profile.get('id', '')}"
        self._quest_intervention_history()[key] = self.get_quest_clock()
        text = str(profile.get("text", f"{actor_display.prose_name(actor, engine.NPCS.get(actor))} 的行动改变了【{engine.quest_display_name(q_name)}】的局势。"))
        record = {
            "clock": self.get_quest_clock(), "quest": q_name, "npc": actor,
            "action": action, "type": "intervention", "text": text,
        }
        record.update({k: v for k, v in result.items() if k in ("stage", "failed")})
        log = self._npc_proactive_log()
        log.append(record)
        del log[:-100]
        memory = profile.get("remember_player_action")
        if isinstance(memory, dict) and memory.get("npc") in engine.NPCS:
            self.remember_player_action(
                memory["npc"], memory.get("id", f"quest_intervention:{q_name}:{profile.get('id', '')}"),
                memory.get("text", text), memory.get("sentiment", "neutral"),
                memory.get("strength", 40), memory.get("ttl", 0), event_type="quest_intervention"
            )
        return record

    def process_quest_interventions(self):
        """处理 NPC/世界对进行中任务的主动干预；不新增任务存档字段。"""
        results = []
        for q_name in list(self.active_quests.keys()):
            q_info = engine.QUESTS.get(q_name, {})
            profiles = q_info.get("npc_interventions", []) or []
            if not isinstance(profiles, list):
                continue
            for profile in profiles:
                if self._quest_intervention_allowed(q_name, profile):
                    result = self._apply_quest_intervention(q_name, profile)
                    if result:
                        results.append(result)
        return results

    # ==================== P2.32 NPC 信息与舆情系统 ====================
    def _npc_information_map(self):
        variables = self.world_state.setdefault("variables", {})
        info = variables.setdefault("npc_information", {})
        if not isinstance(info, dict):
            info = {}
            variables["npc_information"] = info
        return info

    def _player_information_map(self):
        variables = self.world_state.setdefault("variables", {})
        info = variables.setdefault("player_information", {})
        if not isinstance(info, dict):
            info = {}
            variables["player_information"] = info
        return info

    def _information_record(self, topic, text, source="", confidence=50, ttl=0, sentiment="neutral", follow_up=None):
        record = {
            "topic": str(topic), "text": str(text), "source": str(source or ""),
            "confidence": max(0, min(100, _safe_int_value(confidence, 50))), "learned_at": self.get_quest_clock(),
            "sentiment": str(sentiment or "neutral")
        }
        follow_up = normalize_follow_up(follow_up)
        if follow_up:
            record["follow_up"] = follow_up
        ttl = _safe_int_value(ttl, 0)
        if ttl > 0:
            record["expires_at"] = self.get_quest_clock() + ttl
        return record

    def learn_npc_information(self, npc_name, topic, text, source="", confidence=50, ttl=0, sentiment="neutral", follow_up=None):
        if npc_name not in engine.NPCS or not topic:
            return False
        bucket = self._npc_information_map().setdefault(npc_name, {})
        if not isinstance(bucket, dict):
            bucket = {}
            self._npc_information_map()[npc_name] = bucket
        record = self._information_record(topic, text, source, confidence, ttl, sentiment, follow_up)
        old = bucket.get(str(topic))
        if isinstance(old, dict):
            record["confidence"] = max(record["confidence"], max(0, min(100, _safe_int_value(old.get("confidence", 0), 0))))
            if "follow_up" not in record:
                old_follow_up = normalize_follow_up(old.get("follow_up"))
                if old_follow_up:
                    record["follow_up"] = old_follow_up
        bucket[str(topic)] = record
        return True

    def learn_player_information(self, topic, text, source="", confidence=50, ttl=0, sentiment="neutral", follow_up=None):
        if not topic:
            return False
        bucket = self._player_information_map()
        record = self._information_record(topic, text, source, confidence, ttl, sentiment, follow_up)
        old = bucket.get(str(topic))
        if isinstance(old, dict):
            record["confidence"] = max(record["confidence"], max(0, min(100, _safe_int_value(old.get("confidence", 0), 0))))
            if "follow_up" not in record:
                old_follow_up = normalize_follow_up(old.get("follow_up"))
                if old_follow_up:
                    record["follow_up"] = old_follow_up
        bucket[str(topic)] = record
        return True

    def _information_valid(self, record):
        if not isinstance(record, dict):
            return False
        expires = record.get("expires_at")
        if expires is not None:
            try:
                return self.get_quest_clock() < int(expires)
            except (TypeError, ValueError):
                return False
        return True

    def get_npc_information(self, npc_name=None, topic=None):
        info = self._npc_information_map()
        if npc_name is None:
            result = {}
            for name, bucket in info.items():
                if not isinstance(bucket, dict):
                    continue
                result[name] = {k: v for k, v in bucket.items() if self._information_valid(v)}
            return result
        bucket = info.get(npc_name, {})
        if not isinstance(bucket, dict):
            return None if topic else {}
        if topic is not None:
            record = bucket.get(str(topic))
            return record if self._information_valid(record) else None
        return {k: v for k, v in bucket.items() if self._information_valid(v)}

    def get_player_information(self, topic=None):
        bucket = self._player_information_map()
        if topic is not None:
            record = bucket.get(str(topic))
            return record if self._information_valid(record) else None
        return {k: v for k, v in bucket.items() if self._information_valid(v)}

    def cleanup_information(self):
        """清理过期情报，同时区分 NPC 的二级信息表与玩家的主题信息表。

        P2.51 修复：旧逻辑把玩家信息记录本身误当成“主题 -> 记录”的二级桶，
        会把 topic/text/source/confidence 等字段全部清掉，最终导致“信息”只剩内部主题 ID。
        """
        npc_info = self._npc_information_map()
        for npc_name in list(npc_info.keys()):
            bucket = npc_info.get(npc_name)
            if not isinstance(bucket, dict):
                npc_info.pop(npc_name, None)
                continue
            npc_info[npc_name] = {k: v for k, v in bucket.items() if self._information_valid(v)}

        player_info = self._player_information_map()
        for topic in list(player_info.keys()):
            record = player_info.get(topic)
            if not self._information_valid(record):
                player_info.pop(topic, None)

    def _npc_information_profile(self, npc_name):
        profile = engine.NPCS.get(npc_name, {}).get("information_profile", {}) or {}
        return profile if isinstance(profile, dict) else {}

    def seed_npc_information(self, npc_name):
        data = engine.NPCS.get(npc_name, {})
        entries = data.get("information", []) or []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("topic") or not entry.get("text"):
                continue
            self.learn_npc_information(
                npc_name, entry["topic"], entry["text"], entry.get("source", npc_name),
                entry.get("confidence", 70), entry.get("ttl", 0), entry.get("sentiment", "neutral"),
                entry.get("follow_up")
            )

    def learn_information_from_npc(self, npc_name, topic=None):
        self.seed_npc_information(npc_name)
        profile = self._npc_information_profile(npc_name)
        minimum = int(profile.get("share_to_player_min_relation", 0))
        if self.get_relation(npc_name) < minimum:
            return []
        records = self.get_npc_information(npc_name)
        learned = []
        for key, record in records.items():
            if topic and key != topic:
                continue
            if not record.get("player_shareable", True):
                continue
            self.learn_player_information(key, record.get("text", ""), record.get("source", npc_name), record.get("confidence", 50),
                                          max(0, _safe_int_value(record.get("expires_at", self.get_quest_clock())) - self.get_quest_clock()) if record.get("expires_at") is not None else 0,
                                          record.get("sentiment", "neutral"), record.get("follow_up"))
            learned.append(key)
        return learned

    def propagate_npc_information(self, room_id=None):
        self.cleanup_information()
        room_id = room_id or self.location
        npcs = self.get_npcs_in_room(room_id)
        learned = []
        for source in npcs:
            self.seed_npc_information(source)
        for source in npcs:
            source_records = self.get_npc_information(source)
            for target in npcs:
                if source == target:
                    continue
                bond = self.get_npc_bond(source, target)
                profile = self._npc_information_profile(source)
                min_bond = int(profile.get("share_min_bond", 0))
                for topic, record in source_records.items():
                    if not record.get("npc_shareable", True) or bond < min_bond:
                        continue
                    target_profile = self._npc_information_profile(target)
                    if target_profile.get("receive_information", True) is False:
                        continue
                    if self.learn_npc_information(target, topic, record.get("text", ""), source,
                                                  max(0, _safe_int_value(record.get("confidence", 50), 50) - 5),
                                                  max(0, _safe_int_value(record.get("expires_at", self.get_quest_clock())) - self.get_quest_clock()) if record.get("expires_at") is not None else 0,
                                                  record.get("sentiment", "neutral"), record.get("follow_up")):
                        learned.append((source, target, topic))
        return learned

    # ==================== P2.33 NPC 情报网络与记忆系统 ====================
    def _npc_memory_map(self):
        variables = self.world_state.setdefault("variables", {})
        memories = variables.setdefault("npc_memories", {})
        if not isinstance(memories, dict):
            memories = {}
            variables["npc_memories"] = memories
        return memories

    def _npc_memory_profile(self, npc_name):
        profile = engine.NPCS.get(npc_name, {}).get("memory_profile", {}) or {}
        return profile if isinstance(profile, dict) else {}

    def _memory_valid(self, record):
        if not isinstance(record, dict):
            return False
        expires = record.get("expires_at")
        if expires is None:
            return True
        try:
            return self.get_quest_clock() < int(expires)
        except (TypeError, ValueError):
            return False

    def remember_npc_about_player(self, npc_name, memory_id, text, sentiment="neutral", strength=50,
                                  source="player", ttl=0, shareable=True, event_type=""):
        if npc_name not in engine.NPCS or not memory_id or not text:
            return False
        memories = self._npc_memory_map().setdefault(npc_name, {})
        if not isinstance(memories, dict):
            memories = {}
            self._npc_memory_map()[npc_name] = memories
        now = self.get_quest_clock()
        record = {
            "id": str(memory_id), "text": str(text), "sentiment": str(sentiment or "neutral"),
            "strength": max(0, min(100, int(strength))), "source": str(source or "player"),
            "remembered_at": now, "shareable": bool(shareable)
        }
        if event_type:
            record["event_type"] = str(event_type)
        if int(ttl or 0) > 0:
            record["expires_at"] = now + int(ttl)
        old = memories.get(str(memory_id))
        if isinstance(old, dict) and self._memory_valid(old):
            record["strength"] = max(record["strength"], int(old.get("strength", 0)))
            if old.get("remembered_at") is not None:
                record["remembered_at"] = min(now, int(old.get("remembered_at", now)))
        memories[str(memory_id)] = record
        return True

    def get_npc_memories(self, npc_name=None):
        memories = self._npc_memory_map()
        if npc_name is None:
            return {n: {k: v for k, v in (bucket or {}).items() if self._memory_valid(v)}
                    for n, bucket in memories.items() if isinstance(bucket, dict)}
        bucket = memories.get(npc_name, {})
        if not isinstance(bucket, dict):
            return {}
        return {k: v for k, v in bucket.items() if self._memory_valid(v)}

    def get_npc_memory(self, npc_name, memory_id):
        return self.get_npc_memories(npc_name).get(str(memory_id))

    def cleanup_npc_memories(self):
        memories = self._npc_memory_map()
        for npc_name in list(memories.keys()):
            bucket = memories.get(npc_name)
            if not isinstance(bucket, dict):
                memories.pop(npc_name, None)
                continue
            memories[npc_name] = {k: v for k, v in bucket.items() if self._memory_valid(v)}

    def remember_player_action(self, npc_name, memory_id, text, sentiment="neutral", strength=50,
                               ttl=0, event_type="action"):
        profile = self._npc_memory_profile(npc_name)
        if not profile.get("remember_player_actions", True):
            return False
        return self.remember_npc_about_player(
            npc_name, memory_id, text, sentiment, strength,
            source="player_action", ttl=ttl,
            shareable=profile.get("share_player_memories", True), event_type=event_type
        )

    def get_npc_player_reputation(self, npc_name):
        records = self.get_npc_memories(npc_name).values()
        score = 0
        weight = 0
        for record in records:
            strength = max(0, min(100, int(record.get("strength", 0))))
            sentiment = str(record.get("sentiment", "neutral"))
            if sentiment in {"positive", "trust", "helpful"}:
                score += strength
                weight += strength
            elif sentiment in {"negative", "hostile", "betrayal"}:
                score -= strength
                weight += strength
        if weight == 0:
            return 0
        return max(-100, min(100, int(round(score * 100 / weight))))

    def get_npc_memory_attitude(self, npc_name):
        reputation = self.get_npc_player_reputation(npc_name)
        if reputation >= 50:
            return "friendly"
        if reputation <= -50:
            return "hostile"
        if reputation >= 15:
            return "favorable"
        if reputation <= -15:
            return "wary"
        return "neutral"

    def get_npc_memory_behavior(self, npc_name):
        """P2.34：把长期记忆转化为可执行的 NPC 行为，不直接覆盖旧关系规则。"""
        profile = self._npc_memory_profile(npc_name)
        rules = profile.get("behavior", {}) or {}
        if not isinstance(rules, dict):
            rules = {}
        reputation = self.get_npc_player_reputation(npc_name)
        thresholds = {
            "friendly": int(rules.get("friendly_gte", 70)),
            "favorable": int(rules.get("favorable_gte", 30)),
            "wary": int(rules.get("wary_lte", -30)),
            "hostile": int(rules.get("hostile_lte", -75)),
        }
        if reputation >= thresholds["friendly"]:
            action = "welcome"
        elif reputation >= thresholds["favorable"]:
            action = "cooperate"
        elif reputation <= thresholds["hostile"]:
            action = "refuse"
        elif reputation <= thresholds["wary"]:
            action = "caution"
        else:
            action = "neutral"
        return {"reputation": reputation, "action": action, "thresholds": thresholds}

    def propagate_npc_player_memories(self, room_id=None):
        self.cleanup_npc_memories()
        room_id = room_id or self.location
        npcs = self.get_npcs_in_room(room_id)
        propagated = []
        for source in npcs:
            source_records = self.get_npc_memories(source)
            source_profile = self._npc_memory_profile(source)
            min_bond = int(source_profile.get("memory_share_min_bond", 5))
            for target in npcs:
                if source == target:
                    continue
                if self.get_npc_bond(source, target) < min_bond:
                    continue
                target_profile = self._npc_memory_profile(target)
                if target_profile.get("receive_player_memories", True) is False:
                    continue
                for memory_id, record in source_records.items():
                    if not record.get("shareable", True):
                        continue
                    strength = max(1, int(record.get("strength", 0)) - int(source_profile.get("memory_propagation_loss", 10)))
                    if strength <= 0:
                        continue
                    ttl = 0
                    if record.get("expires_at") is not None:
                        ttl = max(0, int(record["expires_at"]) - self.get_quest_clock())
                    copied_id = f"heard:{source}:{memory_id}"
                    if self.remember_npc_about_player(
                        target, copied_id,
                        f"从{source}处听说：{record.get('text', '')}",
                        record.get("sentiment", "neutral"), strength,
                        source=f"npc:{source}", ttl=ttl, shareable=target_profile.get("share_player_memories", True),
                        event_type="propagated"
                    ):
                        propagated.append((source, target, memory_id))
        return propagated

    def list_npc_memory_summary(self, npc_name=None):
        self.cleanup_npc_memories()
        result = []
        source = self.get_npc_memories(npc_name) if npc_name else self.get_npc_memories()
        if npc_name:
            for memory_id, record in sorted(source.items()):
                result.append({"npc": npc_name, "id": memory_id, **record})
        else:
            for name, bucket in sorted(source.items()):
                for memory_id, record in sorted(bucket.items()):
                    result.append({"npc": name, "id": memory_id, **record})
        return result

    def list_information_summary(self):
        self.cleanup_information()
        result = []
        for topic, record in sorted(self.get_player_information().items()):
            result.append({"topic": topic, **record})
        return result

    def get_npc_quest_givers_here(self, room_id=None):
        """返回当前实际地点的任务发布/交付 NPC；使用动态位置而非静态房间 NPC 列表。"""
        room_id = room_id or self.location
        here = set(self.get_npcs_in_room(room_id))
        result = []
        for npc_name in here:
            if engine.NPCS.get(npc_name, {}).get("quests"):
                result.append(npc_name)
        return result

    def _npc_bond_map(self):
        variables = self.world_state.setdefault("variables", {})
        bonds = variables.setdefault("npc_bonds", {})
        if not isinstance(bonds, dict):
            bonds = {}
            variables["npc_bonds"] = bonds
        return bonds

    def get_npc_bond(self, npc_a, npc_b):
        if npc_a not in engine.NPCS or npc_b not in engine.NPCS or npc_a == npc_b:
            return 0
        stored = self._npc_bond_map().get(npc_a, {})
        if isinstance(stored, dict) and npc_b in stored:
            try:
                return int(stored[npc_b])
            except (TypeError, ValueError):
                return 0
        profile = engine.NPCS.get(npc_a, {}).get("npc_bonds", {}) or {}
        try:
            return int(profile.get(npc_b, 0))
        except (TypeError, ValueError):
            return 0

    def change_npc_bond(self, npc_a, npc_b, delta):
        if npc_a not in engine.NPCS or npc_b not in engine.NPCS or npc_a == npc_b:
            return 0
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return self.get_npc_bond(npc_a, npc_b)
        bonds = self._npc_bond_map()
        row = bonds.setdefault(npc_a, {})
        new_value = max(-100, min(100, self.get_npc_bond(npc_a, npc_b) + delta))
        row[npc_b] = new_value
        return new_value

    def get_npc_encounters(self, room_id=None):
        """返回当前房间实际同时出现的 NPC 对话/协作组合。"""
        names = self.get_npcs_in_room(room_id or self.location)
        encounters = []
        for idx, a in enumerate(names):
            for b in names[idx + 1:]:
                bond = self.get_npc_bond(a, b) or self.get_npc_bond(b, a)
                if bond == 0:
                    continue
                encounters.append({
                    "npc_a": a, "npc_b": b,
                    "bond": bond,
                    "tone": "协作" if bond >= 5 else ("对立" if bond <= -5 else "往来"),
                })
        return encounters

    def get_npc_sect_stance(self, npc_name):
        """根据玩家当前门派计算 NPC 对玩家的立场；不单独写入存档。"""
        info = engine.NPCS.get(npc_name, {})
        profile = info.get("sect_profile", {}) or {}
        current = self.get_sect()
        if not isinstance(profile, dict) or current == "散人" and not profile.get("wary"):
            return "neutral"
        for stance in ("preferred", "friendly", "wary", "opposed"):
            values = profile.get(stance, []) or []
            if current in values:
                return stance
        return "neutral"

    def _schedule_state_record(self, npc_name):
        entry = self._npc_schedule_entry(npc_name)
        if not entry:
            return None
        state = str(entry.get("state", self.NPC_STATE_DEFAULT))
        if state not in self.NPC_STATE_ALLOWED:
            return None
        return {
            "state": state,
            "reason": str(entry.get("reason", "")),
            "source": "schedule",
            "schedule_start": int(entry.get("start", 0)),
            "schedule_end": int(entry.get("end", 0)),
        }

    def refresh_npc_schedules(self):
        """刷新日常状态；临时事件/任务状态在有效期内优先于日常时刻表。"""
        state_map = self._npc_state_map()
        schedule_clock = self.get_quest_clock()

        def advance_schedule_location(npc_name, current, target, source):
            raw = locations.get(npc_name)
            if isinstance(raw, dict) and raw.get("last_schedule_move_clock") == schedule_clock:
                return
            step = self._npc_room_path(current, target)
            # 日程移动只能沿真实出口推进；不可达目标不允许瞬移伪装成普通移动。
            if not step:
                return
            next_location = step[1]
            if next_location == current:
                return
            self.set_npc_location(npc_name, next_location, source=source)
            updated = locations.get(npc_name)
            if isinstance(updated, dict):
                updated["last_schedule_move_clock"] = schedule_clock
        for npc_name in engine.NPCS:
            raw = state_map.get(npc_name)
            if isinstance(raw, dict) and raw.get("source") != "schedule":
                try:
                    until = raw.get("until_clock")
                    if until is not None and self.get_quest_clock() >= int(until):
                        state_map.pop(npc_name, None)
                        # 保留事件/任务期间的实际位置，下面统一沿真实出口返回日程地点；
                        # 不能先删除位置再让 get_npc_location() 静默把 NPC 瞬移回家。
                        raw = None
                except (TypeError, ValueError):
                    pass
                if raw is not None:
                    continue
            entry = self._schedule_state_record(npc_name)
            if entry:
                state_map[npc_name] = entry
            elif isinstance(raw, dict) and raw.get("source") == "schedule":
                state_map.pop(npc_name, None)

        locations = self._npc_location_map()

        def sync_schedule_location(npc_name, current, target, source, instant, was_offstage):
            raw = locations.get(npc_name)
            if isinstance(raw, dict) and raw.get("last_schedule_move_clock") == schedule_clock:
                return
            if not target:
                return
            if current == target and not was_offstage:
                if isinstance(raw, dict):
                    raw["last_schedule_move_clock"] = schedule_clock
                return
            if was_offstage:
                self.set_npc_location(npc_name, target, source=source)
            elif current not in engine.ROOMS:
                # 首次定位：instant 日程直接落位且不播报；普通日程从住址走第一步。
                if instant:
                    locations[npc_name] = {"location": target, "source": source}
                else:
                    home = self.get_npc_home_location(npc_name)
                    step = self._npc_room_path(home, target) if home else None
                    if step:
                        self.set_npc_location(npc_name, step[1], source=source)
                    else:
                        locations[npc_name] = {"location": home or target, "source": source}
            elif instant:
                self.set_npc_location(npc_name, target, source=source)
            else:
                step = self._npc_room_path(current, target)
                # 日程移动只能沿真实出口推进；不可达目标不允许瞬移伪装成普通移动。
                if not step:
                    return
                next_location = step[1]
                if next_location == current:
                    return
                self.set_npc_location(npc_name, next_location, source=source)
            updated = locations.get(npc_name)
            if isinstance(updated, dict):
                updated["last_schedule_move_clock"] = schedule_clock

        for npc_name in engine.NPCS:
            raw_location = locations.get(npc_name)
            was_offstage = isinstance(raw_location, dict) and raw_location.get("offstage") is True
            if was_offstage:
                current_location = None
            elif isinstance(raw_location, dict):
                current_location = raw_location.get("location")
            else:
                current_location = raw_location
            if current_location not in engine.ROOMS:
                current_location = None
            state_record = state_map.get(npc_name)
            schedule_entry = self._npc_schedule_entry(npc_name)
            explicit_state = isinstance(state_record, dict) and state_record.get("source") != "schedule"
            if explicit_state:
                # 事件/任务状态只覆盖状态文案，不改动人物实际位置。
                continue
            if schedule_entry is not None:
                target = self._npc_schedule_location(npc_name, schedule_entry)
                if target is None:
                    self.set_npc_offstage(npc_name, source="schedule")
                else:
                    sync_schedule_location(
                        npc_name,
                        current_location,
                        target,
                        "schedule",
                        schedule_entry.get("instant") is True,
                        was_offstage,
                    )
            elif was_offstage or current_location is None:
                home = self.get_npc_home_location(npc_name)
                if home:
                    locations[npc_name] = {"location": home, "source": "home"}
        return state_map

    def get_npc_state_record(self, npc_name):
        raw = self._npc_state_map().get(npc_name, {})
        if not isinstance(raw, dict):
            raw = {}
        try:
            until = raw.get("until_clock")
            if until is not None and self.get_quest_clock() >= int(until):
                self._npc_state_map().pop(npc_name, None)
                raw = {}
        except (TypeError, ValueError):
            pass
        if not raw:
            scheduled = self._schedule_state_record(npc_name)
            if scheduled:
                self._npc_state_map()[npc_name] = scheduled
                raw = scheduled
        return dict(raw) if raw else {"state": self.NPC_STATE_DEFAULT}

    def get_npc_state(self, npc_name):
        return str(self.get_npc_state_record(npc_name).get("state", self.NPC_STATE_DEFAULT))

    def set_npc_state(self, npc_name, state, duration=0, reason="", source="", injury_level=""):
        if npc_name not in engine.NPCS:
            return False
        state = str(state)
        if state not in self.NPC_STATE_ALLOWED:
            return False
        profile = engine.NPCS.get(npc_name, {}).get("state_profile", {}) or {}
        allowed = profile.get("allowed", []) or []
        if allowed and state not in allowed:
            return False
        record = {"state": state}
        try:
            duration = max(0, int(duration))
        except (TypeError, ValueError):
            duration = 0
        if duration:
            record["until_clock"] = self.get_quest_clock() + duration
        if reason:
            record["reason"] = str(reason)
        if source:
            record["source"] = str(source)
        injury_level = str(injury_level).strip().lower()
        if injury_level in self.NPC_INJURY_LEVELS:
            record["injury_level"] = injury_level
        self._npc_state_map()[npc_name] = record
        return True

    def clear_npc_state(self, npc_name):
        self._npc_state_map().pop(npc_name, None)
        return True

    def _apply_npc_reactions(self, reactions, source):
        applied = []
        if not isinstance(reactions, list):
            return applied
        for reaction in reactions:
            if not isinstance(reaction, dict):
                continue
            npc = reaction.get("npc")
            state = reaction.get("state")
            if not npc or not state:
                continue
            if self.set_npc_state(npc, state, reaction.get("duration", 0), reaction.get("reason", ""), source):
                location = reaction.get("location")
                if location in engine.ROOMS:
                    self.set_npc_location(npc, location, source)
                applied.append((npc, state))
        return applied

    def react_npcs_to_event(self, event_id, event_info=None):
        event_info = event_info or {}
        reactions = []
        for npc_name, info in engine.NPCS.items():
            for reaction in info.get("event_reactions", []) or []:
                if isinstance(reaction, dict) and str(reaction.get("event")) == str(event_id):
                    entry = dict(reaction)
                    entry["npc"] = npc_name
                    reactions.append(entry)
        return self._apply_npc_reactions(reactions, f"event:{event_id}")

    def react_npcs_to_quest(self, q_name, outcome):
        reactions = []
        for npc_name, info in engine.NPCS.items():
            qmap = info.get("quest_reactions", {}) or {}
            if not isinstance(qmap, dict):
                continue
            outcome_info = qmap.get(q_name, {})
            if not isinstance(outcome_info, dict):
                continue
            reaction = outcome_info.get(str(outcome))
            if isinstance(reaction, dict):
                entry = dict(reaction)
                entry["npc"] = npc_name
                reactions.append(entry)
        applied = self._apply_npc_reactions(reactions, f"quest:{q_name}:{outcome}")
        # P2.34：任务结果会成为 NPC 对玩家的长期社会记忆。
        sentiment = "positive" if str(outcome) == "complete" else "negative" if str(outcome) in {"fail", "abandon"} else "neutral"
        strength = 65 if sentiment == "positive" else 60 if sentiment == "negative" else 40
        for entry in reactions:
            npc_name = entry.get("npc")
            if npc_name in engine.NPCS:
                profile = self._npc_memory_profile(npc_name)
                memory_cfg = profile.get("quest_memory", {}) or {}
                if isinstance(memory_cfg, dict):
                    strength = int(memory_cfg.get(str(outcome), strength))
                self.remember_player_action(
                    npc_name, f"quest:{q_name}:{outcome}",
                    f"你曾经参与任务《{engine.quest_display_name(q_name)}》，结果是：{outcome}。",
                    sentiment, strength, ttl=int(memory_cfg.get("ttl", 0)) if isinstance(memory_cfg, dict) else 0,
                    event_type="quest"
                )
        return applied

    def get_npc_ecology(self, npc_name):
        """返回 NPC 的稳定生态摘要，不直接暴露内部 world_state。"""
        info = engine.NPCS.get(npc_name, {})
        return {
            "name": npc_name,
            "title": info.get("title", npc_name),
            "type": info.get("type", "unknown"),
            "faction": info.get("faction", "未知势力"),
            "relation": self.get_relation(npc_name),
            "relation_status": self.get_relation_status(npc_name),
            "quests": list(info.get("quests", []) or []),
            "has_shop": bool(info.get("shop")),
            "dialogue_choices": len(info.get("dialogue_choices", []) or []),
            "relation_dialogue": len(info.get("relation_dialogue", []) or []),
            "behavior": engine.relation_behavior(self.get_relation(npc_name)),
            "state": self.get_npc_state(npc_name),
            "state_record": self.get_npc_state_record(npc_name),
            "sect_stance": self.get_npc_sect_stance(npc_name),
        }

    def _relation_progress_var(self, npc_name):
        return f"relation_talk_gain:{npc_name}"

    def get_talk_relation_gain(self, npc_name):
        """读取普通交谈关系收益计数；损坏的旧存档值按 0 处理。"""
        raw = self.get_var(self._relation_progress_var(npc_name), 0)
        if isinstance(raw, bool):
            return 0
        try:
            return max(0, int(raw))
        except (TypeError, ValueError, OverflowError):
            return 0

    def change_talk_relation(self, npc_name, delta, cap=10):
        """限制普通交谈累计正向刷关系；负向和剧情关系效果不受此限制。"""
        if isinstance(delta, bool) or isinstance(cap, bool):
            return self.get_relation(npc_name)
        try:
            delta = int(delta)
            cap = max(0, int(cap))
        except (TypeError, ValueError):
            return self.get_relation(npc_name)
        if delta > 0:
            used = self.get_talk_relation_gain(npc_name)
            allowed = max(0, cap - used)
            applied = min(delta, allowed)
            if applied:
                self.set_var(self._relation_progress_var(npc_name), used + applied)
            return self.change_relation(npc_name, applied)
        return self.change_relation(npc_name, delta)

    def mark_dialogue_choice_used(self, npc_name, choice_id):
        return self.set_flag(f"npc_dialogue_once:{npc_name}:{choice_id}", True)

    def is_dialogue_choice_used(self, npc_name, choice_id):
        return bool(self.get_flag(f"npc_dialogue_once:{npc_name}:{choice_id}", False))

    def change_relation(self, npc_name, delta):
        if isinstance(delta, bool):
            return self.get_relation(npc_name)
        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return self.get_relation(npc_name)
        relations = self._relation_map()
        old = self.get_relation(npc_name)
        new = max(-100, min(100, old + delta))
        relations[npc_name] = new
        if delta >= 3:
            self.remember_player_action(npc_name, f"relation_positive:{self.get_quest_clock()}:{new}", "你近期对我表现出明显善意，我愿意记住这份情义。", "positive", min(100, 35 + abs(int(delta)) * 5), ttl=0, event_type="relationship")
        elif delta <= -3:
            self.remember_player_action(npc_name, f"relation_negative:{self.get_quest_clock()}:{new}", "你近期的言行令我不快，我会记住这次冲突。", "negative", min(100, 35 + abs(int(delta)) * 5), ttl=0, event_type="relationship")
        return new

    def get_all_relations(self):
        return {name: self.get_relation(name) for name in engine.NPCS if self.get_relation(name) != 0}

    def get_build_summary(self):
        """返回角色 Build 的稳定摘要，供终端 UI 和未来数据系统使用。"""
        labels = {
            "strength": "力量", "constitution": "体魄",
            "internal": "内息", "agility": "身法", "insight": "洞察"
        }
        return {labels[k]: self.get_attribute(k) for k in labels}

    def allocate_attribute(self, name, points=1):
        """投入属性点；失败时不修改任何状态。"""
        aliases = {
            "力量": "strength", "力": "strength", "str": "strength",
            "体魄": "constitution", "体": "constitution", "con": "constitution",
            "内息": "internal", "内": "internal", "int": "internal",
            "身法": "agility", "敏捷": "agility", "agi": "agility",
            "洞察": "insight", "感知": "insight", "wis": "insight"
        }
        key = aliases.get(str(name).lower(), str(name).lower())
        if key not in self.attributes:
            return False, "未知属性。可用：力量、体魄、内息、身法、洞察。"
        try:
            points = int(points)
        except (TypeError, ValueError):
            return False, "属性点数量必须是正整数。"
        if points < 1:
            return False, "属性点数量必须是正整数。"
        if points > self.attribute_points:
            return False, f"可用属性点不足：当前只有 {self.attribute_points} 点。"
        # 先完成所有校验，再修改状态。
        self.attributes[key] += points
        self.attribute_points -= points
        if key == "constitution":
            self.max_hp += points * 8
            self.hp += points * 8
        elif key == "internal":
            self.max_mp += points * 6
            self.mp += points * 6
        return True, f"{key} +{points}。"

    def get_hit_chance(self):
        """基础命中率 + 身法修正，限制在战斗规则允许范围内。"""
        affixes = self.get_equipment_affixes()
        return max(engine.COMBAT_DEFAULTS["min_hit"], min(engine.COMBAT_DEFAULTS["max_hit"], engine.COMBAT_DEFAULTS["hit"] + self.get_effective_attribute("agility") * 0.01 + affixes["accuracy_bonus"] + self.get_build_bonuses()["hit_bonus"]))

    def get_crit_chance(self):
        """基础暴击率 + 洞察修正。"""
        affixes = self.get_equipment_affixes()
        return min(0.50, engine.COMBAT_DEFAULTS["crit"] + self.get_effective_attribute("insight") * 0.01 + affixes["crit_bonus"] + self.get_build_bonuses()["crit_bonus"])

    def get_dodge_chance(self):
        """基础闪避率 + 身法修正。"""
        affixes = self.get_equipment_affixes()
        return min(0.50, engine.COMBAT_DEFAULTS["dodge"] + self.get_effective_attribute("agility") * 0.01 + affixes["dodge_bonus"] + self.get_build_bonuses()["dodge_bonus"])

    def _apply_level_up(self):
        """结算一级成长；调用方负责先扣除升级所需经验。"""
        self.level += 1
        self.max_hp += 15; self.hp = self.max_hp
        self.max_mp += 10; self.mp = self.max_mp
        self.atk += 3; self.defense += 2
        self.attribute_points += 3
        self.exp_to_level = exp_needed_for_level(self.level)

    def normalize_exp_progress(self):
        """按当前等级重算升级所需经验，让旧曲线存档平滑过渡到新曲线。

        只重算 exp_to_level，并处理因曲线下调而多出的经验；不改变 V12 存档字段结构。
        """
        self.exp_to_level = exp_needed_for_level(self.level)
        guard = 0
        while self.exp >= self.exp_to_level and guard < 1000:
            self.exp -= self.exp_to_level
            self._apply_level_up()
            guard += 1

    def gain_exp(self, amount):
        self.exp += amount
        print(f"{engine.Color.GREEN}获得了 {amount} 点经验。{engine.Color.RESET}")
        while self.exp >= self.exp_to_level:
            self.exp -= self.exp_to_level
            self._apply_level_up()
            print(f"\n{engine.Color.BRIGHT_YELLOW}【功力大进！】等级提升到了 {self.level} 级！{engine.Color.RESET}")

    def _quest_stage_info(self, q_name):
        q_info = engine.QUESTS.get(q_name, {})
        stages = q_info.get("stages")
        if not stages:
            return None, q_info
        state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": 0})
        stage_idx = max(0, min(state.get("stage", 0), len(stages)-1))
        return stages[stage_idx], q_info

    def get_quest_collect_requirements(self, q_name):
        """返回纯收集任务需要交付的 (物品, 数量)；混合任务的收集阶段不在此列。"""
        info = engine.QUESTS.get(q_name, {})
        stages = info.get("stages") or []
        if stages:
            if not all(isinstance(stage, dict) and stage.get("target_type") == "collect" for stage in stages):
                return []
            raw = [(stage.get("target_name"), stage.get("required_cnt", 1)) for stage in stages]
        elif info.get("target_type") == "collect":
            raw = [(info.get("target_name"), info.get("required_cnt", 1))]
        else:
            return []
        requirements = []
        for name, count in raw:
            item_name = str(name or "").strip()
            if not item_name:
                continue
            try:
                quantity = max(1, int(count or 1))
            except (TypeError, ValueError, OverflowError):
                quantity = 1
            requirements.append((item_name, quantity))
        return requirements

    def get_quest_collect_progress(self, q_name):
        """按行囊实物返回 (物品, 现有数量, 需要数量)；非收集任务返回空列表。"""
        requirements = self.get_quest_collect_requirements(q_name)
        if not requirements:
            return []
        inventory = getattr(self, "inventory", None)
        if not isinstance(inventory, list):
            return [(item_name, 0, required) for item_name, required in requirements]
        return [(item_name, inventory.count(item_name), required) for item_name, required in requirements]

    def sync_collect_quest_from_inventory(self, q_name):
        """接取收集任务时按现有材料登记阶段进度，避免“先备料后接取”无法交付。"""
        progress = self.get_quest_collect_progress(q_name)
        if not progress:
            return []
        stages = engine.QUESTS.get(q_name, {}).get("stages") or []
        state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": 0})
        if not stages:
            item_name, held, required = progress[0]
            registered = min(held, required)
            self.active_quests[q_name] = registered
            state["progress"] = registered
            return progress
        for index, (item_name, held, required) in enumerate(progress):
            registered = min(held, required)
            state["stage"] = index
            state["progress"] = registered
            self.active_quests[q_name] = registered
            if held < required:
                break
        return progress

    def is_quest_goal_complete(self, q_name):
        """目标是否已完成但尚未交付；已交付状态只由完成列表与完成旗标表示。"""
        if q_name not in self.active_quests:
            return False
        info = engine.QUESTS.get(q_name, {})
        state = self.quest_states.get(q_name, {})
        if state.get("branch_pending"):
            return False
        collect_progress = self.get_quest_collect_progress(q_name)
        if collect_progress:
            return all(held >= required for _, held, required in collect_progress)
        stages = info.get("stages") or []
        if stages:
            try:
                stage_index = int(state.get("stage", 0) or 0)
                required = max(1, int(stages[-1].get("required_cnt", 1) or 1))
                progress = int(state.get("progress", self.active_quests.get(q_name, 0)) or 0)
            except (TypeError, ValueError, OverflowError):
                return False
            return stage_index >= len(stages) - 1 and progress >= required
        try:
            required = max(1, int(info.get("required_cnt", 1) or 1))
            progress = int(self.active_quests.get(q_name, 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return False
        return progress >= required

    def get_quest_delivery_guide(self, q_name):
        """返回交付该任务所需的委托人、地点与完整指令。"""
        info = engine.QUESTS.get(q_name, {})
        npc_name = info.get("turn_in_npc") or info.get("npc")
        if not npc_name:
            return None
        room_id = self.get_npc_location(npc_name, refresh=False)
        if room_id not in engine.ROOMS:
            room_id = self.get_npc_home_location(npc_name)
        room_name = str(engine.ROOMS.get(room_id, {}).get("name", "")).strip() if room_id else ""
        npc_label = actor_display.prose_name(npc_name, engine.NPCS.get(npc_name))
        return {
            "npc": npc_label,
            "location": room_name,
            "command": f"交谈 {npc_label} 交付委托 {engine.quest_display_name(q_name)}",
        }

    def _print_quest_delivery_guidance(self, q_name):
        guide = self.get_quest_delivery_guide(q_name)
        if not guide:
            print(f"{engine.Color.YELLOW}请回到原委托人处主动交付，交付后才能领取奖励。{engine.Color.RESET}")
            return
        place = f"【{guide['location']}】" if guide.get("location") else "委托人所在处"
        print(f"{engine.Color.CYAN}交付指引：请前往{place}找【{guide['npc']}】主动交付；输入“{guide['command']}”。{engine.Color.RESET}")

    def update_quest_progress(self, target_name, event_type="kill"):
        for q_name in list(self.active_quests.keys()):
            q_info = engine.QUESTS.get(q_name, {})
            public_title = engine.quest_display_name(q_name)
            stage, full_info = self._quest_stage_info(q_name)
            if stage is not None:
                expected_type = stage.get("target_type", "talk")
                if expected_type != event_type or stage.get("target_name") != target_name:
                    continue
                state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": 0})
                req = _safe_int_value(stage.get("required_cnt"), 1, 1)
                progress_before = _safe_int_value(state.get("progress"), 0, 0)
                # 已达标或等待分支选择时，重复触发同一目标不得再次结算阶段效果。
                if progress_before >= req or state.get("branch_pending"):
                    continue
                state["progress"] = min(req, progress_before + 1)
                self.active_quests[q_name] = state["progress"]
                print(f"{engine.Color.BRIGHT_YELLOW}[任务更新] 【{public_title}】阶段 {state['stage']+1}/{len(full_info['stages'])}：({state['progress']}/{req}){engine.Color.RESET}")
                if state["progress"] >= req:
                    engine.apply_world_effects(self.world_state, stage.get("effects"))
                    branch_choices = stage.get("branch_choices") or []
                    if branch_choices:
                        available = self.get_quest_branch_options(q_name)
                        state["branch_pending"] = True
                        self.active_quests[q_name] = 0
                        labels = " / ".join(f"{i + 1}. {c.get('title', '路线选项')}" for i, c in enumerate(available)) or "无可用路线"
                        print(f"{engine.Color.BRIGHT_CYAN}[剧情分支] 【{public_title}】出现新的路线选择：{labels}。输入“选择 {public_title}|序号”继续。{engine.Color.RESET}")
                    elif stage.get("next_stage") is not None:
                        # Alpha149：允许分支路线在完成各自目标后汇合到共同收尾阶段。
                        # 目标索引无效时不跳转，避免数据错误把任务状态写坏。
                        try:
                            target_stage = int(stage.get("next_stage"))
                        except (TypeError, ValueError):
                            target_stage = -1
                        if 0 <= target_stage < len(full_info["stages"]) and target_stage != state["stage"]:
                            state["stage"] = target_stage
                            state["progress"] = 0
                            self.active_quests[q_name] = 0
                            next_stage = full_info["stages"][target_stage]
                            print(f"{engine.Color.BRIGHT_CYAN}[剧情推进] 【{public_title}】进入下一阶段：{next_stage.get('desc', '')}{engine.Color.RESET}")
                        elif state["stage"] + 1 < len(full_info["stages"]):
                            state["stage"] += 1
                            state["progress"] = 0
                            self.active_quests[q_name] = 0
                            next_stage = full_info["stages"][state["stage"]]
                            print(f"{engine.Color.BRIGHT_CYAN}[剧情推进] 【{public_title}】进入下一阶段：{next_stage.get('desc', '')}{engine.Color.RESET}")
                        else:
                            print(f"{engine.Color.BRIGHT_GREEN}[任务目标达成] 【{public_title}】全部目标已完成，可以交付。{engine.Color.RESET}")
                            self._print_quest_delivery_guidance(q_name)
                    elif state["stage"] + 1 < len(full_info["stages"]):
                        state["stage"] += 1
                        state["progress"] = 0
                        self.active_quests[q_name] = 0
                        next_stage = full_info["stages"][state["stage"]]
                        print(f"{engine.Color.BRIGHT_CYAN}[剧情推进] 【{public_title}】进入下一阶段：{next_stage.get('desc', '')}{engine.Color.RESET}")
                    else:
                        print(f"{engine.Color.BRIGHT_GREEN}[任务目标达成] 【{public_title}】全部目标已完成，可以交付。{engine.Color.RESET}")
                        self._print_quest_delivery_guidance(q_name)
                continue

            expected_type = q_info.get("target_type", "kill")
            if expected_type != event_type or q_info.get("target_name") != target_name:
                continue
            req = q_info.get("required_cnt", 1)
            curr = min(req, self.active_quests[q_name] + 1)
            self.active_quests[q_name] = curr
            print(f"{engine.Color.BRIGHT_YELLOW}[任务更新] 【{public_title}】进度：({curr}/{req}){engine.Color.RESET}")

    # ==================== P2.38 动态任务链与中途分支 ====================
    def get_quest_branch_options(self, q_name):
        """返回当前阶段可选分支；分支状态只写入既有 quest_states。"""
        if q_name not in self.active_quests:
            return []
        q_info = engine.QUESTS.get(q_name, {})
        stages = q_info.get("stages") or []
        state = self.quest_states.get(q_name, {})
        if not stages:
            return []
        idx = int(state.get("stage", 0) or 0)
        if idx < 0 or idx >= len(stages):
            return []
        choices = stages[idx].get("branch_choices") or []
        if not isinstance(choices, list):
            return []
        return [c for c in choices if isinstance(c, dict) and engine.check_conditions(c.get("requires"), self.world_state, self.completed_quests, self)]

    def choose_quest_branch(self, q_name, choice_id):
        """选择当前任务阶段的动态分支，并跳转到指定后续阶段。"""
        if q_name not in self.active_quests:
            return False, "你没有接取这个任务。"
        q_info = engine.QUESTS.get(q_name, {})
        stages = q_info.get("stages") or []
        state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": self.active_quests[q_name]})
        idx = int(state.get("stage", 0) or 0)
        if idx < 0 or idx >= len(stages):
            return False, "当前任务阶段无效。"
        current_stage = stages[idx]
        stage_choices = current_stage.get("branch_choices") or []
        choices = self.get_quest_branch_options(q_name)
        try:
            current_progress = int(state.get("progress", 0) or 0)
            required_progress = int(current_stage.get("required_cnt", 1) or 1)
        except (TypeError, ValueError):
            current_progress, required_progress = 0, 1
        if stage_choices and not state.get("branch_pending") and current_progress < required_progress:
            return False, "当前阶段目标尚未达成，暂时不能选择路线。"
        requested = str(choice_id).strip()
        choice = next((c for c in choices if str(c.get("id")) == requested or str(c.get("title", "")).strip() == requested), None)
        if choice is None and requested.isdigit():
            option_index = int(requested) - 1
            if 0 <= option_index < len(choices):
                choice = choices[option_index]
        if choice is None:
            stage_choices = stages[idx].get("branch_choices") or []
            locked = next((c for c in stage_choices if isinstance(c, dict) and (str(c.get("id")) == requested or str(c.get("title", "")).strip() == requested)), None)
            available = " / ".join(f"{i + 1}. {c.get('title', '分支选项')}" for i, c in enumerate(choices)) or "无"
            if locked is not None:
                reasons = engine.explain_condition_failures(locked.get("requires"), self.world_state, self.completed_quests, self)
                detail = "；".join(reasons) if reasons else "分支条件不满足或配置无效"
                # 对玩家隐藏内部世界变量/标记名，避免输出调试字段。
                return False, f"没有可用分支【{locked.get('title', '该路线')}】：相关剧情条件尚未满足。当前可选：{available}"
            return False, f"没有找到对应分支。当前可选：{available}"
        try:
            next_stage = int(choice.get("next_stage", idx + 1))
        except (TypeError, ValueError):
            return False, "分支 next_stage 配置无效。"
        if next_stage < 0 or next_stage >= len(stages):
            return False, "分支目标阶段超出任务范围。"
        engine.apply_world_effects(self.world_state, choice.get("effects"))
        # 《青锋疑云》的调查态度会影响师父对弟子的信任，结果记录在既有师承状态中。
        if q_name == "青锋疑云" and self.get_sect() == "华山":
            mentorship = self.get_sect_mentorship("华山")
            if mentorship.get("mentor"):
                route_bond = {"public_report": 3, "private_trace": 5, "hold_report": -2}.get(str(choice.get("id")), 0)
                if route_bond:
                    old_bond = max(0, min(100, int(mentorship.get("bond", 0) or 0)))
                    mentorship["bond"] = max(0, min(100, old_bond + route_bond))
                    mentorship["investigation_route"] = str(choice.get("id"))
        # 分支本身的江湖成长只在成功选中时结算一次；重复调用会因阶段已改变而被拒绝。
        action = choice.get("jianghu_action")
        if action:
            self.record_jianghu_action(action, choice.get("jianghu_amount", 1))
        honor_delta = int(choice.get("honor_delta", 0) or 0)
        infamy_delta = int(choice.get("infamy_delta", 0) or 0)
        if honor_delta or infamy_delta:
            self.add_jianghu_reputation(honor=honor_delta, infamy=infamy_delta)
        state["stage"] = next_stage
        state["progress"] = 0
        state["branch"] = str(choice.get("id"))
        state.pop("branch_pending", None)
        self.active_quests[q_name] = 0
        log = self._npc_proactive_log()
        log.append({
            "clock": self.get_quest_clock(),
            "quest": q_name,
            "action": "choose_branch",
            "type": "branch",
            "branch": str(choice.get("id")),
            "stage": next_stage,
            "text": str(choice.get("text", choice.get("title", "已选择剧情分支。"))),
        })
        del log[:-100]
        return True, f"已选择分支【{choice.get('title', choice.get('id'))}】，任务进入第 {next_stage + 1} 阶段。"

    # ==================== P2.25 任务生命周期 API ====================
    def get_quest_clock(self):
        # 世界时钟被任务、经济、治安、危机和 NPC 自主行动共同读取；
        # 单个异常存档值不应让所有系统在同一个 Tick 连锁失败。
        return _safe_int_value(self.get_var("quest_clock", 0), 0, 0, 2_000_000_000)

    def tick_quest_clock(self, steps=1):
        """推进世界时钟；批量步数必须与逐步推进执行相同次数的世界结算。"""
        steps = max(0, int(steps))
        if steps == 0:
            # 保留旧行为：零步仍触发一次既有刷新入口，但不推进时钟与经济 Tick。
            return self._process_world_tick_once(0)
        clock = self.get_quest_clock()
        for _ in range(steps):
            clock = self._process_world_tick_once(1)
        return clock

    def _process_world_tick_once(self, steps=1):
        steps = max(0, int(steps))
        clock = self.increment_var("quest_clock", steps) if steps else self.get_quest_clock()
        # NPC 日程刷新与竞争评估统一由 process_npc_autonomy() 执行一次。
        # NPC 竞争已由 process_npc_autonomy() 统一处理。这里不能再次调用，
        # 否则同一个世界 Tick 会重复评估竞争条件，导致冷却、势力压力等状态
        # 在单次时间推进中被多次推进。
        self.process_npc_autonomy()
        self.process_quest_interventions()
        self.process_faction_actions()
        self.process_faction_conflicts()
        self.process_region_ecology()
        self.process_dynamic_world_stability()
        # P3.2：经济系统跟随既有世界时钟推进，状态仍写入 V12 已有的 economy_state 扩展字段。
        try:
            from economy import EconomyManager
            manager = EconomyManager(getattr(self, "economy_state", {}))
            manager.real_time_regen = True
            manager.apply_world_progress(getattr(self, "world_state", {}))
            # 将已有区域生态数值传入经济模拟，让商路值实际影响商队到场频率。
            manager.state.events["region_ecology"] = {
                zone: self.get_region_ecology(zone) for zone in engine.WORLD_REGIONS
            }
            # Alpha92：把仍在生效的世界危机快照传入经济模拟；只传活动状态，
            # 不改变 V12 存档结构，也不让已结束的危机继续阻滞商队。
            active_crises = {}
            crisis_rows = self.world_state.get("variables", {}).get("world_crises", {})
            if isinstance(crisis_rows, dict):
                current_clock = self.get_quest_clock()
                for crisis_id, crisis in crisis_rows.items():
                    if not isinstance(crisis, dict) or crisis.get("status") != "active":
                        continue
                    try:
                        if current_clock >= int(crisis.get("expires_clock", current_clock + 1)):
                            continue
                    except (TypeError, ValueError, OverflowError):
                        continue
                    effects = crisis.get("effects", {})
                    if not isinstance(effects, dict):
                        continue
                    for zone, effect in effects.items():
                        if not isinstance(effect, dict):
                            continue
                        try:
                            travel_penalty = max(0, min(100, -int(effect.get("travel", 0))))
                            # Alpha93：玩家与 NPC 已取得的危机缓解进度，实际降低商队所受的通行惩罚。
                            # 缓解比例有上限；仍保留至少按原始效果计算的可解释关系，不改存档版本。
                            npc_relief = max(0.0, min(0.70, float(crisis.get("npc_relief", 0.0))))
                            player_relief = max(0.0, min(0.70, float(crisis.get("player_relief", 0.0))))
                            combined_relief = max(0.0, min(0.70, npc_relief + player_relief))
                            travel_penalty = max(0, min(100, int(round(travel_penalty * (1.0 - combined_relief)))))
                        except (TypeError, ValueError, OverflowError):
                            travel_penalty = 0
                        if travel_penalty <= 0:
                            continue
                        prior = active_crises.get(str(zone), {})
                        if travel_penalty > int(prior.get("travel_penalty", 0)):
                            active_crises[str(zone)] = {
                                "id": str(crisis_id),
                                "title": str(crisis.get("title", "局势动荡")),
                                "travel_penalty": travel_penalty,
                                "relief_applied": round(combined_relief, 3),
                            }
            manager.state.events["world_crises"] = active_crises
            manager.update(steps, player_location=getattr(self, "location", None))
            self.economy_state = manager.export_state()
        except (ImportError, TypeError, ValueError, OSError):
            # 经济模块异常不得阻断原有任务/NPC世界时钟。
            pass
        self.check_quest_failures()
        return clock

    def check_quest_failures(self):
        """检查数据驱动的超时/失败条件；失败状态只写入既有 world_state。"""
        failed = []
        for q_name in list(self.active_quests.keys()):
            q_info = engine.QUESTS.get(q_name, {})
            state = self.quest_states.setdefault(q_name, {"stage": 0, "progress": self.active_quests[q_name]})
            limit = q_info.get("time_limit")
            if limit is not None:
                try:
                    if self.get_quest_clock() - int(state.get("accepted_at", self.get_quest_clock())) >= int(limit):
                        failed.append((q_name, "time_limit"))
                        continue
                except (TypeError, ValueError):
                    pass
            fail_if = q_info.get("fail_if")
            if fail_if and engine.check_conditions(fail_if, self.world_state, self.completed_quests, self):
                failed.append((q_name, "condition"))
        for q_name, reason in failed:
            self.fail_quest(q_name, reason)
        return failed

    def fail_quest(self, q_name, reason="condition"):
        if q_name not in self.active_quests:
            return False
        q_info = engine.QUESTS.get(q_name, {})
        self.active_quests.pop(q_name, None)
        self.quest_states.pop(q_name, None)
        self.set_flag(f"quest_active:{q_name}", False)
        self.set_flag(f"quest_failed:{q_name}", True)
        failed_map = self.world_state.setdefault("variables", {}).setdefault("quest_failures", {})
        failed_map[q_name] = {"reason": reason, "clock": self.get_quest_clock()}
        engine.apply_world_effects(self.world_state, q_info.get("on_fail"))
        self.react_npcs_to_quest(q_name, "fail")
        reason_labels = {"time_limit": "超时未完成", "condition": "未满足任务条件", "npc_proactive_timeout": "久未处理，事态恶化", "npc_intervention_stagnation": "局势恶化"}
        print(f"{engine.Color.RED}[任务失败] 【{engine.quest_display_name(q_name)}】已失败：{reason_labels.get(reason, '任务条件发生变化')}。{engine.Color.RESET}")
        return True

    def abandon_quest(self, q_name):
        if q_name not in self.active_quests:
            return False, "你没有接取这个任务。"
        q_info = engine.QUESTS.get(q_name, {})
        self.active_quests.pop(q_name, None)
        self.quest_states.pop(q_name, None)
        self.set_flag(f"quest_active:{q_name}", False)
        self.set_flag(f"quest_abandoned:{q_name}", True)
        engine.apply_world_effects(self.world_state, q_info.get("on_abandon"))
        self.react_npcs_to_quest(q_name, "abandon")
        return True, f"已放弃任务【{engine.quest_display_name(q_name)}】。"

    # ==================== 世界状态 API ====================
    def get_flag(self, key, default=False):
        return engine.get_world_flag(self.world_state, key, default)

    def set_flag(self, key, value=True):
        return engine.set_world_flag(self.world_state, key, value)

    def get_var(self, key, default=0):
        return engine.get_world_var(self.world_state, key, default)

    def set_var(self, key, value):
        return engine.set_world_var(self.world_state, key, value)

    def increment_var(self, key, amount=1):
        value = self.get_var(key, 0) + amount
        return self.set_var(key, value)

    def mark_visited(self, room_id):
        if room_id:
            self.set_flag(f"visited:{room_id}", True)
            room = engine.ROOMS.get(room_id, {})
            zone = room.get("zone")
            if zone:
                self.set_flag(f"visited_zone:{zone}", True)

    # ==================== P2.26 动态世界事件 ====================
    def _world_event_state(self):
        variables = self.world_state.setdefault("variables", {})
        state = variables.setdefault("world_events", {})
        if not isinstance(state, dict):
            state = {}
            variables["world_events"] = state
        return state

    def get_world_event_state(self, event_id):
        state = self._world_event_state()
        raw = state.get(event_id, {})
        return raw if isinstance(raw, dict) else {}

    def list_world_events(self, zone=None, available_only=False):
        zone = zone or engine.ROOMS.get(self.location, {}).get("zone", "main")
        result = []
        for event_id, info in getattr(engine, "WORLD_EVENTS", {}).items():
            if not isinstance(info, dict) or info.get("region") != zone:
                continue
            available = self.can_trigger_world_event(event_id)
            if available_only and not available:
                continue
            result.append({"id": event_id, "title": info.get("title", event_id), "available": available,
                           "description": info.get("description", ""), "region": zone})
        return result

    def can_trigger_world_event(self, event_id):
        info = getattr(engine, "WORLD_EVENTS", {}).get(event_id)
        if not isinstance(info, dict):
            return False
        zone = engine.ROOMS.get(self.location, {}).get("zone", "main")
        if info.get("region") != zone:
            return False
        if not engine.check_conditions(info.get("requires"), self.world_state, self.completed_quests, self):
            return False
        state = self.get_world_event_state(event_id)
        try:
            event_count = max(0, int(state.get("count", 0)))
        except (TypeError, ValueError, OverflowError):
            event_count = 0
        if info.get("once") and event_count > 0:
            return False
        try:
            cooldown = max(0, int(info.get("cooldown", 0) or 0))
        except (TypeError, ValueError, OverflowError):
            cooldown = 0
        try:
            current_clock = int(self.get_quest_clock())
        except (TypeError, ValueError, OverflowError):
            current_clock = 0
        try:
            last_clock = int(state.get("last_clock", -10**9))
        except (TypeError, ValueError, OverflowError):
            last_clock = -10**9
        if cooldown > 0 and current_clock - last_clock < cooldown:
            return False
        return True

    def trigger_world_event(self, event_id=None):
        events = getattr(engine, "WORLD_EVENTS", {})
        if event_id:
            event_id = next((key for key, value in events.items()
                             if key == event_id or (isinstance(value, dict) and value.get("title") == event_id)), event_id)
            candidates = [event_id] if self.can_trigger_world_event(event_id) else []
        else:
            candidates = [x["id"] for x in self.list_world_events(available_only=True)]
        if not candidates:
            return False, "当前区域没有符合条件的动态事件。", None
        # 数据文件顺序即事件优先级，保证测试/存档行为确定性。
        chosen = candidates[0]
        info = events[chosen]
        effects = info.get("effects") or {}
        if not isinstance(effects, dict):
            return False, f"世界事件【{info.get('title', '未知事件')}】的效果数据无效，事件未执行。", None

        # Validate the complete reward payload before consuming the event or
        # changing world state. This prevents a typo/invalid item from silently
        # consuming a once-only event, and prevents malformed numeric values
        # from crashing after the event has already partially applied.
        rewards = info.get("rewards", {}) or {}
        if not isinstance(rewards, dict):
            return False, f"世界事件【{info.get('title', '未知事件')}】的奖励数据无效，事件未执行。", None
        relations = rewards.get("relations", {}) or {}
        if not isinstance(relations, dict):
            return False, f"世界事件【{info.get('title', '未知事件')}】的人物关系奖励数据无效，事件未执行。", None
        for npc_name, delta in relations.items():
            if npc_name not in engine.NPCS or not isinstance(delta, int) or isinstance(delta, bool):
                return False, f"世界事件【{info.get('title', '未知事件')}】的人物关系奖励无效，事件未执行。", None

        reward_bundle = {
            "gold": rewards.get("gold", 0),
            "sect_reputation": rewards.get("sect_reputation", {}) or {},
        }
        if rewards.get("item"):
            reward_bundle["items"] = [{
                "item": rewards.get("item"),
                "quantity": rewards.get("item_quantity", 1),
            }]
        from rewards import validate_reward_bundle, apply_reward_bundle
        reward_ok, reward_error = validate_reward_bundle(reward_bundle)
        if not reward_ok:
            return False, f"世界事件【{info.get('title', '未知事件')}】奖励无效：{reward_error}事件未执行。", None

        # 奖励发放可能因背包容量等运行时条件失败；必须先确认实际结算成功，
        # 再消耗一次性事件、修改世界标记或解锁后续事件，避免“事件已完成但奖励未发”。
        reward_result = apply_reward_bundle(self, reward_bundle, source="世界事件奖励", announce=False)
        if not isinstance(reward_result, dict) or not reward_result.get("ok"):
            detail = reward_result.get("message", "奖励结算未成功。") if isinstance(reward_result, dict) else "奖励结算未成功。"
            return False, f"世界事件【{info.get('title', '未知事件')}】暂未完成：{detail}", None

        state = self._world_event_state()
        old = self.get_world_event_state(chosen)
        try:
            count = max(0, int(old.get("count", 0))) + 1
        except (TypeError, ValueError, OverflowError):
            count = 1
        state[chosen] = {"count": count, "last_clock": self.get_quest_clock()}
        engine.apply_world_effects(self.world_state, effects)
        for entry in effects.get("npc_information", []) or []:
            if not isinstance(entry, dict) or entry.get("npc") not in engine.NPCS or not entry.get("topic"):
                continue
            self.learn_npc_information(
                entry["npc"], entry["topic"], entry.get("text", ""), chosen,
                entry.get("confidence", 70), entry.get("ttl", 0), entry.get("sentiment", "neutral"), entry.get("follow_up")
            )
        self.react_npcs_to_event(chosen, info)
        for npc_name, delta in relations.items():
            self.change_relation(npc_name, delta)
        next_events = info.get("unlock_events", []) or []
        if next_events:
            for next_id in next_events:
                self.set_flag(f"world_event:unlocked:{next_id}", True)
        self.increment_var(f"world_event_region:{info.get('region', 'main')}", 1)
        return True, info.get("text", info.get("description", "世界中发生了一件意外之事。")), info

    def save_to_file(self, filename=SAVE_PATH, verbose=True, auto=False):
        if filename == SAVE_PATH and getattr(self, "_save_deferred", False):
            self._save_pending = True
            self._save_pending_filename = filename
            return True
        self._ensure_sect_state()
        self.sect = self.get_sect()
        save_data = {
            "version": engine.SAVE_VERSION,
            "name": self.name,
            "sect": self.sect,
            "level": self.level,
            "exp": self.exp,
            "exp_to_level": self.exp_to_level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "atk": self.atk,
            "defense": self.defense,
            "gold": self.gold,
            "inventory": self.inventory,
            "equipment": self.equipment,
            "equip_enhance": self.equip_enhance,
            "location": self.location,
            "active_quests": self.active_quests,
            "quest_states": self.quest_states,
            "completed_quests": self.completed_quests,
            "world_state": self.world_state,
            "economy_state": getattr(self, "economy_state", {}),
            "attributes": self.attributes,
            "attribute_points": self.attribute_points
        }
        try:
            abs_filename = os.path.abspath(filename)
            parent_dir = os.path.dirname(abs_filename) or os.getcwd()
            os.makedirs(parent_dir, exist_ok=True)

            # 先写入同目录临时文件，再用 os.replace 原子替换正式存档，
            # 避免程序在 JSON 尚未写完时被中断而留下半截 save.json。
            fd, tmp_path = tempfile.mkstemp(prefix=".save_", suffix=".tmp", dir=parent_dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(save_data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                # 保留最近一份可解析的旧存档作为恢复点；不改变 V12 存档结构。
                # 只有旧文件是完整 JSON 对象时才覆盖备份，避免把损坏文件复制成“有效备份”。
                if os.path.isfile(abs_filename):
                    try:
                        with open(abs_filename, "r", encoding="utf-8") as existing_file:
                            existing_payload = json.load(existing_file)
                        if isinstance(existing_payload, dict):
                            backup_path = abs_filename + ".bak"
                            backup_fd, backup_tmp = tempfile.mkstemp(prefix=".save_backup_", suffix=".tmp", dir=parent_dir)
                            try:
                                with os.fdopen(backup_fd, "w", encoding="utf-8") as backup_file:
                                    json.dump(existing_payload, backup_file, ensure_ascii=False, indent=2)
                                    backup_file.flush()
                                    os.fsync(backup_file.fileno())
                                os.replace(backup_tmp, backup_path)
                            finally:
                                if os.path.exists(backup_tmp):
                                    os.remove(backup_tmp)
                    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                        # 旧存档无法验证时保留已有备份，不阻止玩家保存当前进度。
                        pass
                os.replace(tmp_path, abs_filename)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            if verbose:
                if auto:
                    print(f"{engine.Color.BRIGHT_GREEN}游戏已自动保存{engine.Color.RESET}")
                else:
                    print(f"{engine.Color.BRIGHT_GREEN}[存档成功] 游戏进度已保存。{engine.Color.RESET}")
            self._autosave_tick = self._autosave_clock()
            self._clear_autosave_pending()
            return True
        except Exception as e:
            print(f"{engine.Color.RED}[存档失败] 无法保存当前进度，请检查存储空间和游戏目录权限。{engine.Color.RESET}")
            return False

    def _autosave_clock(self):
        try:
            return int(self.get_quest_clock())
        except (AttributeError, TypeError, ValueError, OverflowError):
            return 0

    def _autosave_due(self):
        last = getattr(self, "_autosave_tick", None)
        return last is None or self._autosave_clock() - last >= AUTO_SAVE_INTERVAL_TICKS

    def _autosave_allowed(self):
        """只有安全、无存活敌人且不在战斗中时才允许自动落盘。"""
        try:
            room = engine.ROOMS.get(getattr(self, "location", None), {}) or {}
            if room.get("safe") is not True:
                return False
            if room.get("secret_realm") is True or room.get("is_secret_realm") is True:
                return False
            if getattr(self, "_in_combat", False):
                return False
            from world_lifecycle import visible_enemies
            enemies, _ = visible_enemies(self, self.location, room.get("enemies", []))
            return not enemies
        except (ImportError, KeyError, TypeError, ValueError, AttributeError, OSError):
            return False

    def _clear_autosave_pending(self):
        self._autosave_pending = False
        self._autosave_pending_filename = None
        self._autosave_pending_verbose = True

    def _write_save(self, filename, verbose):
        saver = self.save_to_file
        try:
            parameters = inspect.signature(saver).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_verbose = "verbose" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        accepts_auto = "auto" in parameters or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        if accepts_auto:
            saved = saver(filename, verbose, auto=True)
        elif accepts_verbose:
            saved = saver(filename, verbose)
        else:
            saved = saver(filename)
        if saved:
            self._autosave_tick = self._autosave_clock()
            self._clear_autosave_pending()
        return saved

    def autosave(self, filename=SAVE_PATH, verbose=True, force=False):
        """自动存档：安全场景外只挂起；距上次落盘不足 10 个世界时刻时也先挂起。"""
        if not self._autosave_allowed():
            self._autosave_pending = True
            self._autosave_pending_filename = filename
            self._autosave_pending_verbose = verbose
            return True
        if not force and not self._autosave_due():
            self._autosave_pending = True
            self._autosave_pending_filename = filename
            self._autosave_pending_verbose = verbose
            return True
        return self._write_save(filename, verbose)

    def flush_autosave(self):
        """只在安全场景补写挂起的自动存档，危险场景继续保留请求。"""
        if not self._autosave_allowed():
            return False
        if not getattr(self, "_autosave_pending", False):
            return False
        if not self._autosave_due():
            return False
        filename = getattr(self, "_autosave_pending_filename", SAVE_PATH) or SAVE_PATH
        verbose = getattr(self, "_autosave_pending_verbose", True)
        return self._write_save(filename, verbose)

    def begin_deferred_save(self):
        """延迟动作内触发的自动存档，等世界时钟推进后再落盘。"""
        self._save_deferred = True
        self._save_pending = False
        self._save_pending_filename = None

    def flush_deferred_save(self):
        """结束延迟存档；只有在期间请求过存档时才真正写入。"""
        self._save_deferred = False
        pending = getattr(self, "_save_pending", False)
        filename = getattr(self, "_save_pending_filename", SAVE_PATH) or SAVE_PATH
        self._save_pending = False
        self._save_pending_filename = None
        if pending:
            return self.autosave(filename)
        return False

    @classmethod
    def load_from_file(cls, filename=SAVE_PATH):
        backup_path = filename + ".bak"
        # 主存档丢失也可能是保存中断、手动误删等造成；只要备份仍在，
        # 就应进入统一恢复流程，而不是直接当作“从未存档”。
        if not os.path.exists(filename) and not os.path.exists(backup_path):
            print(f"{engine.Color.YELLOW}尚无可读取的存档。{engine.Color.RESET}")
            return None
        try:
            backup_used = False
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                if not isinstance(raw_data, dict):
                    raise ValueError("存档根节点不是对象")
                data, old_version = engine.migrate_save_data(raw_data)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                try:
                    with open(backup_path, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    if not isinstance(raw_data, dict):
                        raise ValueError("备份存档根节点不是对象")
                    data, old_version = engine.migrate_save_data(raw_data)
                    backup_used = True
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                    raise ValueError("主存档与备份均无法读取")

            if backup_used:
                print(f"{engine.Color.BRIGHT_YELLOW}[存档恢复] 主存档无法读取，已从备份恢复；建议重新保存一次。{engine.Color.RESET}")

            p = cls(data.get("name", "无名侠客"), data.get("sect", "散人"))
            p.level = data.get("level", 1)
            p.exp = data.get("exp", 0)
            p.exp_to_level = exp_needed_for_level(p.level)
            p.hp = data.get("hp", 100)
            p.max_hp = data.get("max_hp", 100)
            p.mp = data.get("mp", 50)
            p.max_mp = data.get("max_mp", 50)
            p.atk = data.get("atk", 10)
            p.defense = data.get("defense", 5)
            p.gold = data.get("gold", 50)
            p.inventory = data.get("inventory", [])
            p.equipment = data.get("equipment", {"weapon": None, "armor": None})
            p.equip_enhance = data.get("equip_enhance", {"weapon": 0, "armor": 0})
            raw_attributes = data.get("attributes")
            if isinstance(raw_attributes, dict):
                safe_attributes = {}
                for key in p.attributes:
                    try:
                        safe_attributes[key] = max(0, int(raw_attributes.get(key, 0)))
                    except (TypeError, ValueError, OverflowError):
                        safe_attributes[key] = 0
                p.attributes = safe_attributes
                try:
                    p.attribute_points = max(0, int(data.get("attribute_points", 0)))
                except (TypeError, ValueError, OverflowError):
                    p.attribute_points = 0
            else:
                # P2.13 首次引入属性点：旧 V12 存档按已达到的等级补发历史点数。
                p.attributes = {k: 0 for k in p.attributes}
                p.attribute_points = max(0, (p.level - 1) * 3)
            p.location = data.get("location", "village_gate")
            p.active_quests = data.get("active_quests", {})
            p.quest_states = data.get("quest_states", {})
            p.completed_quests = data.get("completed_quests", [])
            p.world_state = data.get("world_state", {"flags": {}, "variables": {}})
            p.economy_state = data.get("economy_state", {})
            if not isinstance(p.economy_state, dict):
                p.economy_state = {}
            if not isinstance(p.world_state, dict):
                p.world_state = {"flags": {}, "variables": {}}
            variables = p.world_state.setdefault("variables", {})
            p._jianghu_profile()  # P3.1.3：旧 V12 存档惰性补齐江湖路线数据。
            had_skill_state = isinstance(variables.get("skill_progress"), dict)
            p._ensure_sect_state()
            p.sect = p.get_sect()
            p._ensure_skill_state()
            if not had_skill_state:
                for skill in engine.SKILLS.get(p.get_sect(), []) or []:
                    if isinstance(skill, dict) and int(skill.get("learn_min_reputation", 0)) == 0 and int(skill.get("learn_min_rank", 0)) == 0 and p.level >= int(skill.get("level", 1)):
                        entry = p._skill_state().setdefault(skill.get("name", ""), {"learned": False, "mastery": 0})
                        entry["learned"] = True
                        entry["mastery"] = max(1, int(entry.get("mastery", 0)))
            if not isinstance(p.quest_states, dict):
                p.quest_states = {}
            for q_name, progress in p.active_quests.items():
                q_info = engine.QUESTS.get(q_name, {})
                if q_info.get("stages") and q_name not in p.quest_states:
                    p.quest_states[q_name] = {"stage": 0, "progress": progress if isinstance(progress, int) else 0}
            p.mark_visited(p.location)
            # 等级、属性、经验全部读入后再校正：旧曲线存档可能因新曲线需求下降而应升级。
            # 必须放在属性读取之后，否则升级获得的属性会被随后读入的存档值覆盖。
            p.normalize_exp_progress()

            engine.clear_statuses()
            if old_version < engine.SAVE_VERSION:
                print(f"{engine.Color.BRIGHT_YELLOW}[存档迁移] v{old_version} → v{engine.SAVE_VERSION}：已补充世界状态并校正旧位置。{engine.Color.RESET}")
            print(f"{engine.Color.BRIGHT_GREEN}[读档成功] 欢迎回来，{p.name}少侠！（存档版本：{engine.SAVE_VERSION}）{engine.Color.RESET}")
            return p
        except Exception as e:
            print(f"{engine.Color.RED}[读档失败] 存档内容无法读取或已损坏，请检查存档后重试。{engine.Color.RESET}")
            return None

