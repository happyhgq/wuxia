# -*- coding: utf-8 -*-
"""
actions.py - 观察、交谈、任务、交易、装备与打铁铺强化
"""

import random
import re
import json
import os
import unicodedata
from collections import Counter
import engine
import actor_display
from ui_output import BODY_WIDTH, safe_print as print, wrap_player_text, format_action_feedback, format_labeled_fields
from world_time import format_world_clock, ticks_until_next_dawn, world_hour
from item_feedback import add_inventory_items, format_item_change, remove_inventory_items
from player import request_autosave

Color = engine.Color

_ITEM_BRACKET_RE = re.compile(r"[【】\[\]〔〕『』「」]")
_ITEM_SPACE_RE = re.compile(r"\s+")


def _normalize_item_input(value):
    """统一物品名输入：全角转半角、去除括号与空白，便于叠放物品直接匹配。"""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _ITEM_BRACKET_RE.sub("", text)
    return _ITEM_SPACE_RE.sub("", text).casefold()


def _display_item_name(value):
    """把玩家输入还原成适合显示在【】中的干净物品名。"""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return _ITEM_BRACKET_RE.sub("", text).strip() or str(value or "").strip()


def _inventory_names(player):
    """返回背包中的不同物品名；同一名称的多个条目视为一叠。"""
    names = []
    for name in getattr(player, "inventory", []) or []:
        if name not in names:
            names.append(name)
    return names


def _inventory_signature(player):
    return tuple(getattr(player, "inventory", []) or [])


def _resolve_inventory_items(player, item_input):
    """按归一化后的名称解析背包物品；同叠物品只返回一个候选。"""
    key = _normalize_item_input(item_input)
    if not key:
        return []
    names = _inventory_names(player)
    exact = [name for name in names if _normalize_item_input(name) == key]
    if exact:
        return exact
    return [
        name for name in names
        if key in _normalize_item_input(name) or _normalize_item_input(name) in key
    ]


def _inventory_candidate_label(player, item_name):
    info = engine.ITEMS.get(item_name, {})
    info = info if isinstance(info, dict) else {}
    count = (getattr(player, "inventory", []) or []).count(item_name)
    details = []
    base_item = info.get("base_item")
    quality = str(info.get("quality") or "").strip()
    if base_item and base_item != item_name:
        details.append(f"基础：{base_item}")
    if quality and quality not in item_name:
        details.append(f"品质：{quality}")
    suffix = f"（{'，'.join(details)}）" if details else ""
    return f"{item_name}{suffix} ×{count}"


def _remember_use_candidates(player, item_names):
    player._use_item_candidates = (_inventory_signature(player), list(item_names))


def _save_without_success_message(player):
    """保存进度但不显示成功提示；存档失败仍由 save_to_file 正常提示。"""
    request_autosave(player, verbose=False)


def _use_inventory_item(player, item_name):
    before = (getattr(player, "inventory", []) or []).count(item_name)
    if not apply_consumable(player, item_name):
        return False
    remaining = player.inventory.count(item_name)
    if remaining == before:
        # 兜底反馈：正常情况下 apply_consumable 已输出完整结果。
        print(f"{Color.GREEN}已消耗 1 件，剩余：{item_name} ×{remaining}。{Color.RESET}")
    _save_without_success_message(player)
    return True


def _resource_stock_line(room_id, economy_state, resources=None, player=None):
    """返回当前场景可采伐/开采资源的真实储量提示；无配置时不显示。"""
    if resources is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), "data", "economy", "resources.json"), encoding="utf-8") as f:
                resources = json.load(f)
        except (OSError, ValueError, TypeError):
            resources = {}
    cfg = resources.get(room_id) if isinstance(resources, dict) else None
    if not isinstance(cfg, dict):
        return ""
    cfg = dict(cfg)
    if room_id == "herb_springbank" and player is not None and player.get_flag("world:main:mistwood_herb_route_safe", False):
        cfg["capacity"] = max(12, int(cfg.get("capacity", 0) or 0))
        cfg["regen_amount"] = max(3, int(cfg.get("regen_amount", 0) or 0))
    try:
        capacity = max(0, int(cfg.get("capacity", 20)))
    except (TypeError, ValueError, OverflowError):
        capacity = 20
    rows = economy_state.get("resources", {}) if isinstance(economy_state, dict) else {}
    row = rows.get(room_id, {}) if isinstance(rows, dict) else {}
    try:
        remaining = max(0, min(capacity, int(row.get("remaining", capacity)))) if isinstance(row, dict) else capacity
    except (TypeError, ValueError, OverflowError):
        remaining = capacity
    action = str(cfg.get("action", "mine"))
    command = "伐木" if action == "chop" else ("搜索 / 采集" if action == "gather" else "采矿")
    item = str(cfg.get("item", "资源"))
    try:
        interval = max(1, int(cfg.get("regen_interval", 8)))
    except (TypeError, ValueError, OverflowError):
        interval = 8
    try:
        amount = max(0, int(cfg.get("regen_amount", 2)))
    except (TypeError, ValueError, OverflowError):
        amount = 2
    state_tick = max(0, int(economy_state.get("tick", 0) or 0)) if isinstance(economy_state, dict) else 0
    last_tick = max(0, int(row.get("last_tick", state_tick) or 0)) if isinstance(row, dict) else state_tick
    if remaining < capacity:
        until_recovery = max(1, interval - max(0, state_tick - last_tick))
        recovery = f"每{interval}个世界时刻恢复{amount}份，下一次约{until_recovery}个世界时刻后"
    else:
        recovery = f"每{interval}个世界时刻恢复{amount}份（储量已满）"
    if remaining <= 0:
        status = f"暂时耗尽，等待自然恢复；{recovery}"
    else:
        status = (f"先输入“搜索”发现，再输入“采集”获取{item}；{recovery}" if action == "gather" else f"可输入“{command}”获取{item}；{recovery}")
    return f"资源储量：{remaining}/{capacity} | {status}"


def _highlight_room_desc(desc):
    """突出场景中的资源、交互对象和真实可用命令。"""
    text = str(desc or "")
    phrases = {
        "可采集草药": Color.BRIGHT_GREEN, "可持续恢复的林木": Color.BRIGHT_GREEN,
        "可开采的铁矿": Color.BRIGHT_YELLOW, "铁矿脉": Color.BRIGHT_YELLOW,
        "可伐木": Color.BRIGHT_GREEN, "可采矿": Color.BRIGHT_YELLOW,
        "可采集": Color.BRIGHT_GREEN, "铁矿": Color.BRIGHT_YELLOW,
        "木材": Color.BRIGHT_GREEN, "药草": Color.BRIGHT_GREEN,
        "草药": Color.BRIGHT_GREEN, "出口": Color.BRIGHT_YELLOW,
    }
    pattern = re.compile("|".join(re.escape(x) for x in sorted(phrases, key=len, reverse=True)))
    text = pattern.sub(lambda m: f"{phrases[m.group(0)]}{m.group(0)}{Color.RESET}", text)
    command_color = Color.BRIGHT_CYAN
    commands = r"伐木|采矿|采集|搜索|探索|交谈|查看|地图|建议|公告|商店|购买|出售|任务|装备|穿戴|使用|比较|住店|住宿|用餐|打尖"
    text = re.sub(rf"[“\"]({commands})[”\"]",
                  lambda m: f"{command_color}{m.group(0)}{Color.RESET}", text)
    return text


def _scene_action_hints(room_id, room, resources=None, npcs=None, economy_state=None):
    """依据地点数据生成新手可直接执行的操作提示，不暴露内部数据标识。"""
    if resources is None:
        try:
            with open(os.path.join(os.path.dirname(__file__), "data", "economy", "resources.json"), encoding="utf-8") as f:
                resources = json.load(f)
        except (OSError, ValueError, TypeError):
            resources = {}
    cfg = resources.get(room_id, {}) if isinstance(resources, dict) else {}
    actions = ["查看", "地图"]
    if isinstance(cfg, dict) and cfg:
        action = str(cfg.get("action", "mine"))
        item = str(cfg.get("item", "资源"))
        if action == "chop":
            command = "伐木"
        elif action == "gather":
            # 搜索是采集系统的实际入口；提示中只显示一次，避免同一操作重复列出。
            command = f"搜索（获取{item}）"
        else:
            command = "采矿"
        stock = _resource_stock_line(room_id, economy_state or {}, resources)
        action_hint = command if "暂时耗尽" not in stock else f"{command}（资源恢复后可用）"
        actions.append(action_hint)
    if room_id in ("inn", "guiyun_yunlai_inn", "guiyun_restaurant_hall"):
        actions.extend(["住店（睡到天亮，恢复气血与内力）", "吃饭或打尖（恢复气血与内力）", "喝茶（恢复内力）", "听消息（打听风声）", "商店（查看可买物品）"])
    if npcs:
        actions.append("交谈 人物名称")
    if room.get("enemies"):
        actions.append("查看威胁 / 攻击 目标名称")
    if room.get("exits"):
        actions.append("输入出口方向移动")
    return "、".join(actions)



def handle_inn_service(player, action, args=None):
    """客栈服务：住店、用餐、饮茶和打听风声；费用与收益写入既有玩家状态。"""
    args = args or []
    room = engine.ROOMS.get(player.location, {})
    inn_rooms = {"inn", "guiyun_yunlai_inn", "guiyun_restaurant_hall"}
    if player.location not in inn_rooms:
        print("这里没有可供住宿或用餐的客栈服务。请前往悦来客栈、云来客栈或醉仙楼。")
        return False
    action = str(action or "").lower()
    if action in ("住店", "住宿", "客房", "休息一晚"):
        cost = 12
        if player.gold < cost:
            print(f"掌柜摇摇头：住一晚需 {cost} 两银子，你身上的银钱还不够。")
            return 0
        steps = ticks_until_next_dawn(player.get_quest_clock())
        wake_clock = player.get_quest_clock() + steps
        player.gold -= cost
        old_hp, old_mp = player.hp, player.mp
        player.hp = player.max_hp
        player.mp = player.max_mp
        player.world_state.setdefault("variables", {})["inn_nights_stayed"] = int(player.world_state.get("variables", {}).get("inn_nights_stayed", 0) or 0) + 1
        print(f"你付了 {cost} 两，店小二引你上楼。关好房门后，你安心睡下，再睁眼时窗外已是{format_world_clock(wake_clock)}，这一觉过去 {steps} 个世界时刻。气血恢复 {player.hp-old_hp} 点，内力恢复 {player.mp-old_mp} 点，楼下已飘来热粥的香气。")
        print("住店不会自动保存进度；需要保留变化时，请输入“保存”。")
        return steps
    if action in ("吃饭", "用餐", "打尖", "饭菜"):
        cost = 4
        if player.gold < cost:
            print(f"一顿热饭需 {cost} 两，你的银钱不够。")
            return False
        player.gold -= cost
        old_hp, old_mp = player.hp, player.mp
        player.hp = min(player.max_hp, player.hp + 18)
        player.mp = min(player.max_mp, player.mp + 8)
        player.world_state.setdefault("variables", {})["inn_meals_eaten"] = int(player.world_state.get("variables", {}).get("inn_meals_eaten", 0) or 0) + 1
        print(f"你花了 {cost} 两，吃下一碗热汤面和两碟小菜。气血恢复 {player.hp-old_hp} 点，内力恢复 {player.mp-old_mp} 点。小二收走碗碟，笑问还要不要添茶。")
        return True
    if action in ("喝茶", "茶", "饮茶"):
        cost = 2
        if player.gold < cost:
            print(f"一壶粗茶需 {cost} 两，你的银钱不够。")
            return False
        player.gold -= cost
        old_mp = player.mp
        player.mp = min(player.max_mp, player.mp + 12)
        print(f"你花了 {cost} 两，捧着热茶听了一会儿堂中闲谈，内力恢复 {player.mp-old_mp} 点。")
        return True
    if action in ("听消息", "打听消息", "风声", "传闻"):
        cost = 3
        if player.gold < cost:
            print(f"小二压低声音：打听消息得请大家喝杯茶，至少要 {cost} 两。")
            return False
        player.gold -= cost
        variables = player.world_state.setdefault("variables", {})
        room_id = str(player.location)
        # 每家客栈有自己的风声池和轮换进度；消息以传闻口吻呈现，不冒充确定事实。
        rumor_pools = {
            "inn": [
                ("青石村风声·山林", "村里的樵夫说，林木与草药都有采尽的时候；若暂时无所获，可以先办别的事，过些时辰再回来看看。"),
                ("青石村风声·铁铺", "有人见铁匠近日收进几批矿料。若想卖掉采来的原料，先问清商店与行商的收价，未必处处相同。"),
                ("青石村风声·村道", "往来脚夫提醒，出村前最好看一眼地图和出口方向；官道虽好走，偏僻处却未必安全。"),
                ("青石村风声·行商", "有行商说，村中广场是打听货物与商队消息的好地方，遇到商队时不妨看看它带了什么。"),
            ],
            "guiyun_yunlai_inn": [
                ("归云城风声·商路", "靠窗的商客谈起，货价会受地区行情和商队供货影响；同一种货物，不同地方的买卖价未必一样。"),
                ("归云城风声·镖路", "一名镖师说，接远路差事前先确认目的地和沿途出口，若听到路上有变，宁可多问一遍。"),
                ("归云城风声·市集", "跑商的人常去万商坊打听行情。若要买卖材料，先看现有库存和价格，再决定是否出手。"),
                ("归云城风声·旅人", "外地旅人提到，城中消息常有真假，听到重要传闻后最好再向相关人物核实。"),
            ],
            "guiyun_restaurant_hall": [
                ("醉仙楼风声·江湖", "邻桌有人压低声音说，江湖人物未必会把来意写在脸上；交谈时先观察对方态度，比贸然追问稳妥。"),
                ("醉仙楼风声·护镖", "几名镖师谈到，路途上的危险会随区域而变。准备出城前，最好检查气血、内力与随身药物。"),
                ("醉仙楼风声·商队", "酒客说，商队停留的时间有限，若想交易就要趁它还在场时前去查看，不要只顾听故事。"),
                ("醉仙楼风声·传闻", "说书人提醒，酒桌上流传的消息可能掺了夸大之词；把它当作线索，再通过地图、人物或任务核实更稳妥。"),
            ],
        }
        rumors = rumor_pools.get(room_id, rumor_pools["inn"])
        progress = variables.setdefault("inn_rumor_progress", {})
        if not isinstance(progress, dict):
            progress = {}
            variables["inn_rumor_progress"] = progress
        index = max(0, int(progress.get(room_id, 0) or 0))
        topic, rumor = rumors[index % len(rumors)]
        progress[room_id] = index + 1
        variables["inn_rumor_index"] = int(variables.get("inn_rumor_index", 0) or 0) + 1
        player.learn_player_information(topic, rumor, room.get("name", "客栈闲谈"), 62, 24, "neutral")
        variables["inn_rumors_heard"] = int(variables.get("inn_rumors_heard", 0) or 0) + 1
        print(f"你花了 {cost} 两请小二和邻桌客人喝茶。片刻后，听到一条消息：\n“{rumor}”\n消息已记入你听来的信息，可输入“信息”回看；各桌闲谈只是线索，重要消息还需核实。")
        return True
    print("客栈可用服务：住店（12两，睡到天亮并恢复气血与内力）、吃饭（4两，小幅恢复）、喝茶（2两，恢复内力）、听消息（3两，获得一条风声）。")
    return False

def handle_npc_actions(player, args=None):
    """查看最近的 NPC 自主行动日志。"""
    args = args or []
    limit = 10
    if args:
        try:
            limit = max(1, min(30, int(args[0])))
        except (TypeError, ValueError):
            pass
    logs = player.get_npc_action_log(limit)
    events = player.get_npc_proactive_event_log(limit)
    if not logs and not events:
        print("目前还没有人物主动行动或主动剧情记录。")
        return
    print(f"\n{Color.BRIGHT_CYAN}【人物主动行动】{Color.RESET}")
    for item in logs:
        action_labels = {"patrol":"巡行", "investigate":"调查", "meet_npc":"会面", "seek_player":"寻找你", "rest":"休整"}
        label = action_labels.get(item.get("action"), "行动")
        destination = item.get("to")
        destination_name = engine.ROOMS.get(destination, {}).get("name", "") if destination else ""
        detail = f" → {destination_name}" if destination_name else ""
        target = f"（目标：{item.get('target')}）" if item.get("target") else ""
        print(f"{format_world_clock(item.get('clock', 0))}：{item.get('npc')}【{label}】{target}{detail} — {item.get('reason', '')}")
    if events:
        print(f"\n{Color.BRIGHT_YELLOW}【主动剧情事件】{Color.RESET}")
        for event in events:
            print(f"{format_world_clock(event.get('clock', 0))}：{event.get('npc')}【{event.get('title', '事件')}】{event.get('text', '')}")


def handle_world_activity(player, args=None):
    """主动查看经济模拟中真实发生的营生，用江湖口吻而非后台记录呈现。"""
    args = args or []
    try:
        limit = max(1, min(20, int(args[0]))) if args else 10
    except (TypeError, ValueError, OverflowError):
        limit = 10
    from economy import EconomyManager
    manager = EconomyManager(getattr(player, "economy_state", {}))
    manager.real_time_regen = True
    rows = manager.recent_world_activity(100)
    lines = _business_activity_lines(rows, limit)
    if not lines:
        print("目前还没有可供查看的营生动态。随着世界时刻推进，采集、制作和交易发生后会逐渐留下记录。")
        return
    print(f"\n{Color.BRIGHT_CYAN}【江湖营生动态】{Color.RESET}")
    print("近日采集、制作与交易间，江湖上有些营生动静：")
    for line in lines:
        print(f"  {line}")


def handle_local_business_rumor(player):
    """只主动查询当前场景的营生消息，不把后台日志塞进默认场景描述。"""
    economy_state = getattr(player, "economy_state", {})
    from economy import EconomyManager
    try:
        manager = EconomyManager(economy_state)
        manager.real_time_regen = True
    except Exception:
        print("附近的人说，眼下营生如常，没听到什么新鲜消息。")
        return
    rows = [
        row for row in manager.recent_world_activity(100)
        if isinstance(row, dict) and row.get("room_id") == player.location
    ]
    lines = _business_activity_lines(rows, 3)
    if not lines:
        print("附近的人说，眼下营生如常，没听到什么新鲜消息。")
        return
    print(f"\n{Color.BRIGHT_CYAN}【附近营生】{Color.RESET}")
    print("近来附近有些营生动静：")
    for line in lines:
        print(f"  {line}")


def _business_activity_lines(rows, limit):
    """把世界活动记录转成不暴露时辰、单价和内部字段的江湖说法。"""
    lines = []
    seen = set()
    for row in reversed(rows or []):
        if not isinstance(row, dict):
            continue
        sentence = _business_activity_sentence(row)
        if not sentence:
            continue
        # 同一人物反复做同一件事时只留最近一次，避免主动查询也变成刷屏。
        key = (str(row.get("actor", "")), str(row.get("action", "")), str(row.get("item", "")))
        if key in seen:
            continue
        seen.add(key)
        lines.append(sentence)
        if len(lines) >= max(1, int(limit)):
            break
    return lines


def _business_activity_sentence(row):
    actor = str(row.get("actor", "一名江湖人")).strip() or "一名江湖人"
    kind = str(row.get("kind", "")).strip()
    action = str(row.get("action", "")).strip()
    item = str(row.get("item", "货物")).strip() or "货物"
    amount = max(0, _safe_int_for_activity(row.get("amount", 0)))
    if not amount:
        return ""
    unit = "把" if ("剑" in item or "刀" in item) else ("瓶" if "药" in item and "草" not in item else "份")
    if kind == "采集":
        verb = {"伐木": "伐得", "采矿": "采得"}.get(action, "采得")
        return f"{actor}近日从附近{verb}{amount}{unit}{item}。"
    if kind == "制作":
        verb = "打好" if unit == "把" else ("配好" if unit == "瓶" else "做好")
        return f"{actor}近日{verb}{amount}{unit}{item}。"
    if kind == "交易":
        if action == "采购原料":
            return f"{actor}近日进了{amount}{unit}{item}。"
        if action == "采购成品":
            return f"{actor}近日从作坊进了{amount}{unit}{item}。"
        if action == "向采集者采购":
            return f"{actor}近日向采集者收了{amount}{unit}{item}。"
        if action == "交付矿石":
            return f"{actor}近日向作坊交付了{amount}{unit}{item}。"
        if action == "售予城镇":
            return f"{actor}近日在镇上卖出了{amount}{unit}{item}。"
        return f"{actor}近日经手了{amount}{unit}{item}。"
    # 行商开销等只影响账目，不构成玩家可打听的营生消息。
    return ""


def _npc_economy_context(npc_name, economy_state, room_id=""):
    """把近期真实营生融入交谈；仅引用已记录的库存变动，不虚构 NPC 行为。"""
    if not isinstance(economy_state, dict):
        return ""
    events = economy_state.get("events", {})
    rows = events.get("world_activity", []) if isinstance(events, dict) else []
    if not isinstance(rows, list):
        return ""
    name = str(npc_name or "").replace(" ", "")
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        actor = str(row.get("actor", ""))
        actor_norm = actor.replace(" ", "")
        same_actor = bool(name and (name in actor_norm or actor_norm in name))
        same_place = bool(room_id and row.get("room_id") == room_id)
        if same_actor or same_place:
            candidates.append(row)
    if not candidates:
        # 没有近期营生记录时，仍可依据真实工时、库存与配方给出当前状态；
        # 只对经济系统明确登记的 NPC 输出，避免替普通人物编造职业。
        try:
            from economy.manager import EconomyManager
            manager = EconomyManager(economy_state)
            manager.real_time_regen = True
            status = manager.npc_work_status(npc_name)
            meaningful = {"已歇工", "货物已满", "等待资源恢复", "等待原料", "缺少原料", "成品待售"}
            if status.get("status") in meaningful:
                return f"你问起眼下的营生，对方说道：‘{status.get('detail', status['status'])}。’"
        except Exception:
            pass
        return ""
    row = candidates[-1]
    action = str(row.get("action", "忙活"))
    item = str(row.get("item", "货物"))
    try:
        amount = max(0, min(9999, int(row.get("amount", 0))))
    except (TypeError, ValueError, OverflowError):
        amount = 0
    actor = str(row.get("actor", npc_name))
    if actor.replace(" ", "") == name or name in actor.replace(" ", ""):
        return f"你提起近来的营生，对方点头道：‘方才确实{action}了{amount}份{item}，都是按手头货物实做的。’"
    return f"谈话间，{actor}近来{action}的消息传来：已处理{amount}份{item}。"


def _safe_int_for_activity(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _npc_economy_scene_status(npc_name, economy_state, manager=None, room_id=""):
    """用经济模拟的真实营生状态补足人物行，避免“在休息”与制作记录并存。"""
    if manager is None:
        if not isinstance(economy_state, dict):
            return ""
        try:
            from economy.manager import EconomyManager
            manager = EconomyManager(economy_state)
            manager.real_time_regen = True
        except Exception:
            return ""
    try:
        work = manager.npc_work_status(npc_name)
        work_room = ""
        if npc_name in manager.gatherers:
            work_room = str((manager.gatherers.get(npc_name, {}) or {}).get("room_id", ""))
        elif npc_name in manager.recipes:
            work_room = str((manager.recipes.get(npc_name, {}) or {}).get("room_id", ""))
        if room_id and work_room and work_room != room_id:
            return ""
    except Exception:
        return ""
    status = str(work.get("status", ""))
    if status == "正在营生":
        if npc_name in manager.gatherers:
            cfg = manager.gatherers.get(npc_name, {}) or {}
            action = str(cfg.get("action", "gather"))
            item = str(cfg.get("item", ""))
            if action == "chop":
                return "正在伐木"
            if action == "mine":
                return "正在采矿"
            if item == "草药":
                return "正在采药"
            return f"正在采集{item}" if item else "正在采集"
        cfg = manager.recipes.get(npc_name, {}) or {}
        outputs = cfg.get("outputs", {})
        item = next(iter(outputs), "") if isinstance(outputs, dict) else ""
        if item == "铁剑" or "剑" in str(item) and "木" not in str(item):
            return "正在打铁"
        if item == "木剑":
            return "正在制作木剑"
        if "药" in str(item):
            return "正在配药"
        return f"正在制作{item}" if item else "正在忙于营生"
    if status == "货物已满":
        return "货物已备满，正歇口气"
    if status == "等待资源恢复":
        return "附近资源采尽，正等恢复"
    if status == "等待原料":
        return "正等着原料到货"
    if status == "缺少原料":
        return "原料不凑手，暂歇着"
    if status == "成品待售":
        return "成品已备好，正等买主"
    return ""


def _room_is_night(player, room):
    """判断房间是否处于夜间时段；数据未配置时始终为白天。"""
    hours = room.get("night_hours") if isinstance(room, dict) else None
    if not (isinstance(hours, list) and len(hours) == 2):
        return False
    try:
        start, end = int(hours[0]) % 24, int(hours[1]) % 24
        hour = world_hour(player.get_quest_clock())
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False
    return (start <= hour < end) if start < end else (hour >= start or hour < end)


def look(player, args=None, show_guidance=False):
    room = engine.ROOMS.get(player.location, engine.ROOMS["village_gate"])
    player.propagate_npc_information(player.location)
    npcs_here = player.get_npcs_in_room(player.location)

    if not args:
        print("\n" + engine.style(f"【{room['name']}】", "title"))
        print(f"{Color.BOLD}【环境】{Color.RESET}")
        room_desc = (room.get("night_desc") or room.get("desc", "")) if _room_is_night(player, room) else room.get("desc", "")
        if player.location == "herb_springbank" and player.get_flag("world:main:mistwood_herb_route_safe", False):
            room_desc += " 毒蛛已被清除，浅滩附近的草药长势渐旺，采集与恢复条件都比先前好些。"
        print(wrap_player_text(_highlight_room_desc(room_desc), width=BODY_WIDTH))
        absence_notes = room.get("absence_notes", {}) if isinstance(room.get("absence_notes"), dict) else {}
        for npc_name, note in absence_notes.items():
            if npc_name in npcs_here:
                continue
            public = player.get_npc_public_state(npc_name) if hasattr(player, "get_npc_public_state") else None
            if isinstance(public, dict) and public.get("offstage"):
                print(wrap_player_text(str(note), width=BODY_WIDTH))
        stock_line = _resource_stock_line(player.location, getattr(player, "economy_state", {}), player=player)
        if stock_line:
            print(f"{Color.BOLD}【资源】{Color.RESET}")
            print(wrap_player_text(stock_line, width=BODY_WIDTH))
        if player.location == "village_square":
            print(f"{engine.style('公告栏：', 'warning')}树下立着一面村中公告栏，输入“公告”查看近期江湖消息。")
        elif player.location == "guiyun_central_square":
            print(f"{engine.style('江湖榜墙：', 'warning')}广场西侧的榜墙贴满各路消息，输入“公告”查看。")
        zone = room.get("zone", "main")
        ecology = player.get_region_ecology(zone)
        level_labels = {"calm": "平静", "tension": "紧张", "confrontation": "对峙", "conflict": "冲突", "escalation": "升级", "war": "战争"}
        danger_labels = {"safe": "安全", "normal": "一般", "dangerous": "危险", "high": "高危", "extreme": "极危"}
        if room.get("safe_zone") is True or (engine.WORLD_REGIONS.get(zone, {}) or {}).get("indoor"):
            print(f"{Color.BOLD}【区域局势】{Color.RESET} 安全")
        else:
            level_text = level_labels.get(ecology.get("level"), str(ecology.get("level")))
            danger_text = danger_labels.get(ecology.get("danger"), str(ecology.get("danger")))
            print(f"{Color.BOLD}【区域局势】{Color.RESET} 势力动向：{level_text} | 危险度：{danger_text}")
        visible_exits = list((room.get("exits", {}) or {}).items())
        exit_notes = room.get("exit_notes", {}) if isinstance(room.get("exit_notes"), dict) else {}
        hidden_exits = room.get("hidden_exits", {}) if isinstance(room, dict) else {}
        if isinstance(hidden_exits, dict):
            for direction, entry in hidden_exits.items():
                if isinstance(entry, dict) and entry.get("flag") and player.get_flag(entry.get("flag")):
                    visible_exits.append((direction, entry.get("target")))
        if visible_exits:
            direction_order = {name: index for index, name in enumerate(("北", "南", "东", "西", "东北", "西北", "东南", "西南", "上", "下"))}
            visible_exits.sort(key=lambda item: (direction_order.get(str(item[0]), 99), str(item[0])))
            exit_parts = []
            for direction, target in visible_exits:
                if target not in engine.ROOMS:
                    target_name = "未知地点"
                else:
                    display_name = getattr(engine.MAP_ENGINE, "display_name", None)
                    target_name = display_name(target) if callable(display_name) else engine.ROOMS[target].get("name", "未知地点")
                note = str(exit_notes.get(direction, "")).strip()
                label = f"{direction}{note}" if note else direction
                exit_parts.append(f"{engine.style(label, 'exit')} → {engine.style(target_name, 'hint')}")
            exit_line = f"{Color.BOLD}【可前往地点】{Color.RESET} 出口：" + "　".join(exit_parts)
            print(wrap_player_text(exit_line, width=BODY_WIDTH))
        economy_state = getattr(player, "economy_state", {})
        economy_manager = None
        if isinstance(economy_state, dict):
            try:
                from economy.manager import EconomyManager
                economy_manager = EconomyManager(economy_state)
                economy_manager.real_time_regen = True
            except Exception:
                economy_manager = None
        if npcs_here:
            print(f"{Color.BOLD}【人物】{Color.RESET}")
            # 每个人物只显示一行名称与状态，避免重复列出姓名。
            for npc_name in npcs_here:
                npc_record = engine.NPCS.get(npc_name, {})
                # 岗位/场景状态优先于日常作息兜底，避免守山人物被误显示为“在住处休息”。
                scene_status = str(npc_record.get("scene_status", "")).strip()
                activity = player.get_npc_daily_activity(npc_name) if hasattr(player, "get_npc_daily_activity") else None
                activity_reason = str((activity or {}).get("reason", "")).strip().rstrip("。.!！")
                npc_state_record = player.get_npc_state_record(npc_name) if hasattr(player, "get_npc_state_record") else {}
                npc_state_source = str((npc_state_record or {}).get("source", ""))
                state_reason = str((npc_state_record or {}).get("reason", "")).strip().rstrip("。.!！")
                economy_reason = _npc_economy_scene_status(npc_name, economy_state, economy_manager, player.location)
                if scene_status:
                    reason = scene_status
                elif npc_state_source.startswith("faction_conflict:"):
                    # 势力冲突原因属于区域局势，不是人物行为；避免把“局势升级至对峙”显示成人物状态。
                    scheduled = player._schedule_state_record(npc_name) if hasattr(player, "_schedule_state_record") else None
                    reason = str((scheduled or {}).get("reason", "正在处理事务")).strip().rstrip("。.!！")
                elif npc_state_source not in ("", "schedule") and state_reason:
                    # 任务/事件留下的具体状态优先于营生模拟，只有作息兜底才让位给实际营生。
                    reason = state_reason
                elif economy_reason:
                    reason = economy_reason
                else:
                    reason = activity_reason
                if not reason:
                    reason = "在此处停留"
                reason = str(reason).strip().rstrip("。.!！")
                label = actor_display.format_room_label(npc_name, npc_record)
                print(f"  {engine.style(label, 'npc')}：{reason}。")
        events = economy_state.get("events", {}) if isinstance(economy_state, dict) else {}
        # 商队是独立的世界活动实体，不属于普通 NPC 名册；场景必须直接展示有效驻留记录。
        active_caravans = events.get("active_caravans", {}) if isinstance(events, dict) else {}
        current_tick = _safe_int_for_activity(economy_state.get("tick", 0)) if isinstance(economy_state, dict) else 0
        caravans_here = []
        if isinstance(active_caravans, dict):
            seen_caravans = set()
            for active_entry in active_caravans.values():
                if not isinstance(active_entry, dict) or active_entry.get("room") != player.location:
                    continue
                name = str(active_entry.get("name", "商队")).strip() or "商队"
                until_tick = _safe_int_for_activity(active_entry.get("until_tick", -1))
                if until_tick <= current_tick or name in seen_caravans:
                    continue
                seen_caravans.add(name)
                caravans_here.append((name, max(0, until_tick - current_tick)))
        if caravans_here:
            print(f"{Color.BOLD}【商旅】{Color.RESET}")
            caravan_names = "、".join(f"{engine.style(name, 'npc')}" for name, _ in caravans_here)
            print(f"商旅：{caravan_names}")
            for caravan_name, remaining in caravans_here:
                print(f"  {engine.style(caravan_name, 'npc')}正在此地停留，预计还停留 {remaining} 个世界时刻。")
                print(f"  查看货物：商店 {caravan_name}")
                print(f"  出售物品：出售 物品 数量 给 {caravan_name}")
        # 世界营生只保留在主动查询中；默认场景不展示后台经济记录，避免刷屏和人物状态矛盾。
        encounters = player.get_npc_encounters(player.location)
        for encounter in encounters:
            print(f"{engine.style('人物偶遇：', 'warning')}{engine.style(encounter['npc_a'], 'npc')} 与 {engine.style(encounter['npc_b'], 'npc')} 正在{encounter['tone']}交谈。")
        if room.get("enemies"):
            from world_lifecycle import visible_enemies
            active_enemies, corpses = visible_enemies(player, player.location, room.get("enemies", []))
            if active_enemies:
                print(f"{Color.BOLD}【危险与遗留】{Color.RESET}")
                print(f"出没的威胁：{engine.style('、'.join(active_enemies), 'enemy')}")
            if corpses:
                if not active_enemies:
                    print(f"{Color.BOLD}【危险与遗留】{Color.RESET}")
                corpse_names = [f"{row.get('name', '无名者')}的尸体" for row in corpses]
                print(f"遗留尸体：{engine.style('、'.join(corpse_names), 'enemy')}（可输入‘查看名称的尸体’查看）")
        if show_guidance:
            hints = _scene_action_hints(player.location, room, npcs=npcs_here, economy_state=getattr(player, "economy_state", {}))
            print(f"{Color.BOLD}【下一步可以做什么】{Color.RESET}")
            print(wrap_player_text(f"{engine.style('可用操作：', 'hint')}{hints}", width=BODY_WIDTH))
            print("不确定下一步时，输入“建议”获取当前地点的玩法建议。")
        if player.location in {"inn", "guiyun_yunlai_inn", "guiyun_restaurant_hall"}:
            print(f"{engine.style('客栈服务：', 'warning')}住店（12两，睡到天亮并恢复气血与内力）｜吃饭或打尖（4两，小幅恢复）｜喝茶（2两，恢复内力）｜听消息（3两，按客栈打听当地风声）。")
        return

    target = args[0]
    if str(target).strip() in {"商情", "营生", "营生消息", "附近营生"}:
        handle_local_business_rumor(player)
        return

    npc_target = " ".join(str(part) for part in args)
    if actor_display.is_self_target(npc_target):
        view = actor_display.build_player_view(player)
        print()
        for line in actor_display.format_look(view):
            print(wrap_player_text(line, width=BODY_WIDTH))
        return
    npc_name = actor_display.find_npc(npc_target, player.get_npcs_in_room(player.location))
    if npc_name:
        view = actor_display.build_npc_view(player, npc_name)
        print()
        for line in actor_display.format_look(view):
            print(wrap_player_text(line, width=BODY_WIDTH))
        return

    from world_lifecycle import visible_enemies
    active_enemies, corpses = visible_enemies(player, player.location, room.get("enemies", []))
    for corpse in corpses:
        corpse_label = f"{corpse.get('name', '无名者')}的尸体"
        if target in corpse_label or corpse_label in target or target in str(corpse.get('name', '')):
            print(f"\n{Color.BRIGHT_RED}【{corpse_label}】{Color.RESET}")
            print("尸体已经失去生命迹象，暂时还未被清理。")
            return

    for enemy_name in active_enemies:
        if target in enemy_name or enemy_name in target:
            from combat import get_enemy_profile
            e_data = get_enemy_profile(enemy_name, player.location)
            hp = e_data.get("hp", 0)
            atk = e_data.get("atk", 0)
            defense = e_data.get("defense", 0)
            print(f"\n{Color.BRIGHT_RED}【{enemy_name}】{Color.RESET}")
            if e_data.get("desc"):
                print(e_data["desc"])
            print(f"等级：{e_data.get('level', 1)} | 类型：{e_data.get('tier_label', '普通')} | 区域难度：{e_data.get('difficulty_label', '普通')}")
            print(f"属性评估：气血 {hp} | 攻击 {atk} | 防御 {defense}")
            if e_data.get("combat_hint"):
                print(f"应对建议：{e_data['combat_hint']}")
            if e_data.get("growth_levels", 0) > 0:
                print(f"区域成长：基础等级 {e_data.get('base_level', 1)} → 当前等级 {e_data.get('level', 1)}")
            print(f"{Color.RED}提示：输入“攻击 {enemy_name}”即可出手。{Color.RESET}")
            return

    all_items = player.inventory + list(player.equipment.values())
    for item_name in set(all_items):
        if item_name and (target in item_name or item_name in target):
            i_data = engine.ITEMS.get(item_name, {})
            i_type = i_data.get("type", "普通物品")
            type_cn = {"weapon": "兵刃", "armor": "防具", "consumable": "消耗药剂", "material": "材料"}.get(i_type, i_type)
            desc = i_data.get("desc", "暂无说明。")
            price = i_data.get("price", 0)
            print(f"\n{Color.BRIGHT_GREEN}【{item_name}】({type_cn}){Color.RESET}")
            detail_fields = [("描述：", desc)]
            if i_data.get("use_hint"):
                detail_fields.append(("用途：", i_data['use_hint']))
            if i_data.get("material"):
                detail_fields.append(("材质/来源：", f"{i_data['material']} | 状态：{i_data.get('condition', '普通')}"))
            if i_data.get("craft_note"):
                detail_fields.append(("物件细节：", i_data['craft_note']))
            if i_type in ("weapon", "armor"):
                detail_fields.append(("品质：", f"{i_data.get('quality', '普通')} | 词条槽：{int(i_data.get('affix_count', 0))}"))
            if i_type == "weapon":
                detail_fields.append(("攻击：", f"+{i_data.get('atk', 0)}"))
            elif i_type == "armor":
                detail_fields.append(("防御：", f"+{i_data.get('defense', 0)}"))
            for detail_line in format_labeled_fields(detail_fields, label_width=12):
                print(wrap_player_text(detail_line, width=BODY_WIDTH))
            affixes = []
            for key, label in (("accuracy_bonus", "命中"), ("crit_bonus", "暴击"), ("dodge_bonus", "闪避")):
                value = float(i_data.get(key, 0.0))
                if value:
                    affixes.append(f"{label}{value:+.0%}")
            attr_labels = {"strength": "力量", "constitution": "体魄", "internal": "内息", "agility": "身法", "insight": "洞察"}
            for key, value in (i_data.get("attribute_bonus", {}) or {}).items():
                if key in attr_labels and value:
                    affixes.append(f"{attr_labels[key]}{int(value):+d}")
            if affixes:
                print(f"词条：{' | '.join(affixes)}")
            print(f"价值：{price} 两银子")
            if i_type in ("weapon", "armor"):
                print(f"提示：输入“比较 {item_name}”可与当前装备比较。")
            return

    print(f"周围和行囊里并没有找到与【{target}】相关的目标。")


def _conditional_dialogue_text(player, npc_data):
    """返回当前世界状态下优先级最高的条件对白；没有则返回 None。"""
    matched = []
    for index, entry in enumerate(npc_data.get("conditional_dialogue", []) or []):
        if not isinstance(entry, dict) or not entry.get("text"):
            continue
        if engine.check_conditions(entry.get("requires"), player.world_state, player.completed_quests, player):
            try:
                priority = int(entry.get("priority", 0))
            except (TypeError, ValueError):
                priority = 0
            matched.append((priority, -index, str(entry["text"])))
    return max(matched)[2] if matched else None


def handle_talk_and_ask(player, args):
    if args and "".join(str(part) for part in args).strip() in {"营生", "商情", "营生消息", "附近营生"}:
        # “打听 营生”是本地商情查询，不应被当成人物名或普通话题。
        handle_local_business_rumor(player)
        return False
    room = engine.ROOMS.get(player.location, {})
    npcs_in_room = player.get_npcs_in_room(player.location)
    player.propagate_npc_information(player.location)
    player.propagate_npc_player_memories(player.location)

    if not npcs_in_room:
        print("此地空无一人，并无可以交谈的对象。")
        return False

    target_npc = npcs_in_room[0]
    topic = None
    if args:
        # 优先按“完整 NPC 名称前缀”匹配，避免多词姓名被误拆成话题。
        # 例如“交谈 青石村 老村长 安慰”应识别为 NPC“青石村老村长”、话题“安慰”。
        joined_args = " ".join(str(part) for part in args).strip()
        normalized_args = joined_args.replace(" ", "")
        exact_prefix_matches = []
        for name in npcs_in_room:
            normalized_name = str(name).replace(" ", "")
            if normalized_args == normalized_name or normalized_args.startswith(normalized_name):
                exact_prefix_matches.append((len(normalized_name), name, normalized_name))
        if exact_prefix_matches:
            _, target_npc, normalized_name = max(exact_prefix_matches, key=lambda item: item[0])
            # NPC 名称本身允许被空格分隔；保留名称之后话题中的原始空格。
            consumed = 0
            matched_chars = 0
            while consumed < len(joined_args) and matched_chars < len(normalized_name):
                if not joined_args[consumed].isspace():
                    matched_chars += 1
                consumed += 1
            topic = joined_args[consumed:].strip() or None
        else:
            # 若输入前缀明确对应游戏中的某个 NPC，但该 NPC 不在当前房间，不能静默改为询问首位 NPC。
            normalized_global_matches = [
                str(name).replace(" ", "") for name in engine.NPCS
                if normalized_args.startswith(str(name).replace(" ", ""))
            ]
            if normalized_global_matches:
                missing_name = max(normalized_global_matches, key=len)
                print(f"当前地点没有【{missing_name}】，请前往对方所在地点再交谈。")
                return False
            # 兼容旧用法：只输入 NPC 名称的一部分仍可定位；其余参数作为话题。
            matched = False
            for name in sorted(npcs_in_room, key=lambda value: len(str(value)), reverse=True):
                if args[0] in name or name in args[0]:
                    target_npc = name
                    matched = True
                    break
            if matched and len(args) > 1:
                topic = " ".join(args[1:])
            elif not matched:
                # 未识别为目标名时，保持既有行为：把输入作为对当前首位 NPC 的话题。
                topic = joined_args

    # Alpha202：随机路人只提供轻量闲谈，不进入固定 NPC 的任务、关系、记忆与日程流程。
    try:
        import random_npcs
        ambient_text = random_npcs.talk_text(player, target_npc)
    except (ImportError, TypeError, ValueError, KeyError):
        ambient_text = None
    if ambient_text:
        print(f"\n{Color.BRIGHT_YELLOW}【路人闲谈】{Color.RESET}")
        print(ambient_text)
        return

    npc_data = engine.NPCS.get(target_npc, {})
    npc_state = player.get_npc_state(target_npc)
    state_record = player.get_npc_state_record(target_npc)
    # 忙碌且没有具体话题时只展示状态与日常对白，不推进世界时钟；
    # 具体话题仍走正常交谈流程，任务接取/交付不会被忙碌状态拦截。
    busy_idle = npc_state == "busy" and not topic
    if target_npc == "青石村接引人" and (not topic or (any(word in topic for word in ("新手", "初来", "怎么玩", "做什么", "入门", "建议")) and not any(word in topic for word in ("接受", "领取", "接取", "接下", "接受委托", "领取委托")))):
        first_guide = not player.get_flag("newcomer:guide_seen", False)
        player.set_flag("newcomer:guide_seen", True)
        print()
        if npc_state == "busy":
            clause = actor_display.busy_clause(target_npc, state_record.get("reason"))
            if clause:
                print(f"{clause}，仍抽空应了你一声。")
        if first_guide:
            print("初入江湖，可以先从村中委托熟悉行路、交谈与任务交付。公告栏只提供求助线索；看到消息后，请去找相关人物问清详情，再决定是否接受委托。")
            print("资源操作分两步：输入“搜索”发现草药，输入“采集”实际获取；木材用“伐木”，矿石用“采矿”。")
            print("正式拜入门派需达到 10 级。先完成跑腿、采集和野外历练，不必急着远行。")
        else:
            print("村中广场公告栏张贴公开消息与求助线索；输入“公告”查看，随后与相关人物交谈领取委托，输入“任务”查看进度。资源先“搜索”发现，再“采集”获取。正式拜入门派需达到 10 级。")
        return False if busy_idle else None
    print()
    relation_value = player.get_relation(target_npc)
    behavior = engine.relation_behavior(relation_value)
    sect_stance = player.get_npc_sect_stance(target_npc)
    memory_behavior = player.get_npc_memory_behavior(target_npc)
    memory_action = memory_behavior.get("action")
    if memory_action == "welcome":
        print(f"{Color.GREEN}{target_npc} 显然记得你的过往善举，态度比普通来客亲近许多。{Color.RESET}")
    elif memory_action == "cooperate":
        print(f"{Color.CYAN}{target_npc} 记得你曾经的作为，愿意认真听你说话。{Color.RESET}")
    elif memory_action == "caution":
        print(f"{Color.YELLOW}{target_npc} 似乎记得一些不愉快的过往，言语间多了几分戒备。{Color.RESET}")
    elif memory_action == "refuse":
        print(f"{Color.RED}{target_npc} 记得你过去的失信或冲突：“旧账未清，我不会再轻易帮你。”{Color.RESET}")
        if not topic and behavior not in {"hostile", "refuse"}:
            return False
    fame_reaction = player.get_jianghu_npc_reaction()
    if fame_reaction:
        print(f"{Color.CYAN}{fame_reaction}{Color.RESET}")

    if npc_state == "away":
        print(f"{Color.YELLOW}{target_npc} 此刻暂时不在状态，无法与你正常交谈。{Color.RESET}")
        return False
    if npc_state == "fear" and not topic:
        print(f"{target_npc} 神色紧张：“最近的局势不太对劲，你也多加小心。”")
    if npc_state == "injured" and not topic:
        print(f"{target_npc} 看起来有些负伤，动作明显比平时迟缓。")
    if npc_state == "angry" and not topic:
        print(f"{target_npc} 仍在气头上：“现在不是闲聊的时候。”")

    # P2.22-R2：关系不再只是数值；极端负面关系会直接改变 NPC 行为。
    if behavior == "hostile":
        print(f"{Color.RED}{target_npc} 对你怒目而视：“少来烦我！再靠近一步，休怪我不客气。”{Color.RESET}")
        return False
    if behavior == "refuse":
        print(f"{Color.YELLOW}{target_npc} 冷冷说道：“我不信任你，不会与你合作，也不会透露更多消息。”{Color.RESET}")
        return False
    if sect_stance == "opposed" and not topic:
        print(f"{Color.RED}{target_npc} 对你所属的【{player.get_sect()}】明显抱有敌意：“门派立场不同，今日无话可谈。”{Color.RESET}")
        return False
    if sect_stance == "wary" and not topic:
        print(f"{Color.YELLOW}{target_npc} 对你所属的【{player.get_sect()}】保持戒心：“江湖门派各有规矩，先证明诚意再说。”{Color.RESET}")

    if busy_idle:
        # 忙碌且没有具体话题时只给一句短应答，不重复整段寒暄、关系变化与委托列表。
        record_source = str(state_record.get("source", ""))
        clause = ""
        if not record_source.startswith("faction_conflict:"):
            clause = actor_display.busy_clause(target_npc, state_record.get("reason"))
        if clause:
            print(f"{clause}，只匆匆应了一声：“稍等，忙完这阵再细说。”")
        else:
            print(f"{target_npc} 只匆匆应了你一声，似乎一时脱不开身。")
        return False

    # 忙碌只是人物状态描述，不拦截了解、接取或交付；真正的不可交互状态使用独立的“暂离”机制。
    quest_topic_words = ("委托", "任务", "帮忙", "差事", "历练", "悬赏", "接活", "接受", "领取", "接取", "接下", "交付", "交任务", "交差", "复命")

    # 新手引导不能成为领取第一项委托的隐性障碍：若玩家直接按公告线索向接引人询问/接受委托，
    # 这次有效交谈本身就完成基础引导前置。
    if target_npc == "青石村接引人" and topic and any(word in topic for word in quest_topic_words):
        player.set_flag("newcomer:guide_seen", True)

    # 若玩家明确要求交付某项活动任务，先核对原交付人，任何 NPC 都不能代收。
    delivery_words = ("交付", "交任务", "交差", "复命")
    if topic and any(word in topic for word in delivery_words):
        delivery_query = _quest_command_query(topic, delivery=True)
        match_state, requested_matches = _resolve_npc_quest_name(delivery_query, list(player.active_quests)) if delivery_query else ("empty", [])
        if match_state == "matched" and requested_matches:
            q_name = requested_matches[0]
            original = engine.QUESTS.get(q_name, {}).get("turn_in_npc") or engine.QUESTS.get(q_name, {}).get("npc")
            if original and original != target_npc:
                print(f"交付失败：此人不是【{_quest_title(q_name)}】的原委托人。请回到【{original}】处交付。")
                return

    # Alpha226：任务由发布 NPC 的交谈流程接取；交付则必须同时支持单独配置的交付 NPC。
    # 公告栏只提供线索，不提供任务接取入口。发布人与交付人不一致时，不能把任务误显示成对方发布。
    npc_quests = _quests_for_npc(target_npc)
    npc_turn_in_quests = [q for q, info in engine.QUESTS.items()
                          if isinstance(info, dict) and (info.get("turn_in_npc") or info.get("npc")) == target_npc]
    deliverable = [q for q in npc_turn_in_quests if q in player.active_quests and _quest_npc_status(player, q)[0] == "待交付"]
    delivery_intent = bool(topic and any(word in topic for word in ("交付", "交任务", "交差", "复命")))
    # 多项交付提示后的独立数字输入（1/2/…）也视为选择，不要求玩家重复输入指令。
    numeric_delivery_choice = bool(topic and topic.strip().isdigit() and deliverable)
    if topic and (npc_quests or npc_turn_in_quests) and (delivery_intent or numeric_delivery_choice):
        query = _quest_command_query(topic, delivery=True) if delivery_intent else topic.strip()
        if not deliverable:
            named = None
            if query and not query.isdigit():
                match_state, matches = _resolve_npc_quest_name(
                    query, list(dict.fromkeys(npc_quests + npc_turn_in_quests))
                )
                if match_state == "matched":
                    named = matches[0]
            if named:
                # 点名的任务尚未达成或已交付时，说明真实状态，不再笼统报“没有可交付委托”。
                state, detail = _quest_npc_status(player, named)
                if state == "未领取":
                    print(f"你还没有接取【{_quest_title(named)}】。")
                elif state == "已交付":
                    print(f"这件事已经办妥并交付完毕，无需重复交付【{_quest_title(named)}】。")
                else:
                    print(f"【{_quest_title(named)}】暂不能交付：{detail}")
                return
            if npc_quests or npc_turn_in_quests:
                print(f"{target_npc}说道：“你目前没有可交付的委托。”")
                _print_npc_quest_offers(player, target_npc, list(dict.fromkeys(npc_quests + npc_turn_in_quests)), detailed=True)
            else:
                print(f"{target_npc}说道：“我这里没有需要交付的委托。”")
            return
        chosen = None
        if query and query.isdigit():
            index = int(query) - 1
            if 0 <= index < len(deliverable):
                chosen = deliverable[index]
            else:
                print(f"序号无效，请输入 1 至 {len(deliverable)}。")
                _print_delivery_choices(player, target_npc, deliverable)
                return
        elif query:
            match_state, matches = _resolve_npc_quest_name(query, deliverable)
            if match_state == "matched":
                chosen = matches[0]
            elif match_state == "ambiguous":
                print(f"{target_npc}说道：“这个称呼对应多项委托，请按序号选择：”")
                _print_delivery_choices(player, target_npc, matches)
                print(f"请输入序号，或使用：交谈 {target_npc} 交付委托 任务名称")
                return
            else:
                print(f"未找到委托【{query}】，你可能想交付：")
                _print_delivery_choices(player, target_npc, deliverable)
                return
        elif deliverable:
            # 未点名任务时必须由玩家确认，不能在打开列表的同一次交谈中自动结算。
            print(f"{target_npc}说道：“你有以下可交付委托：”")
            _print_delivery_choices(player, target_npc, deliverable)
            print(f"请选择要交付的委托序号，或使用：交谈 {target_npc} 交付委托 任务名称")
            return

        if chosen:
            handle_quest(player, "jiaofu", [chosen])
        return
    if topic and npc_quests and any(word in topic for word in ("接受", "领取", "接取", "接下")):
        eligible = [q for q in npc_quests if _quest_npc_status(player, q)[0] == "未领取" and
                    engine.check_conditions(engine.QUESTS.get(q, {}).get("requires"), player.world_state, player.completed_quests, player)]
        query = topic
        for prefix in ("接受委托", "领取委托", "接受任务", "接取任务", "接任务", "接受", "领取", "接取", "接下"):
            if query.startswith(prefix):
                query = query[len(prefix):].strip()
                break
        match_state, matches = _resolve_npc_quest_name(query, npc_quests) if query else ("empty", [])
        if match_state == "matched":
            chosen = matches[0]
            if chosen in eligible:
                handle_quest(player, "jiequ", [chosen])
            else:
                state, detail = _quest_npc_status(player, chosen)
                title = str(engine.QUESTS.get(chosen, {}).get("title", chosen))
                print(f"{title}暂时不能接取：{detail}")
        elif match_state == "ambiguous":
            titles = [str(engine.QUESTS.get(q, {}).get("title", q)) for q in matches]
            print("任务简称对应多项委托，请使用完整名称选择：" + "；".join(titles))
        elif match_state == "missing":
            suggestions = [str(engine.QUESTS.get(q, {}).get("title", q)) for q in matches]
            if suggestions:
                print(f"未找到任务【{query}】，你可能想接取：【{'】、【'.join(suggestions)}】。")
            else:
                titles = [str(engine.QUESTS.get(q, {}).get("title", q)) for q in eligible]
                print(f"未找到任务【{query}】。当前可接委托：{'、'.join(titles) if titles else '暂无'}。")
        elif len(eligible) == 1:
            handle_quest(player, "jiequ", [eligible[0]])
        elif eligible:
            titles = [str(engine.QUESTS.get(q, {}).get("title", q)) for q in eligible]
            print("当前可接委托有：" + "、".join(titles) + "。请在命令后写明任务名称。")
        else:
            _print_npc_quest_offers(player, target_npc, npc_quests, detailed=True)
        return
    if topic and npc_quests and any(word in topic for word in ("委托", "任务", "帮忙", "差事", "历练", "悬赏", "接活")):
        _print_npc_quest_offers(player, target_npc, npc_quests, detailed=True)
        return

    # P2.22-R2：达到关系门槛后显示数据驱动的特殊/隐藏对话。
    relation_dialogue = npc_data.get("relation_dialogue", []) or []
    if not topic and relation_dialogue and behavior not in {"cold", "refuse", "hostile"}:
        eligible = []
        for entry in relation_dialogue:
            if not isinstance(entry, dict):
                continue
            try:
                minimum = int(entry.get("min_relation", 0))
            except (TypeError, ValueError):
                continue
            if relation_value < minimum:
                continue
            if entry.get("requires") and not engine.check_conditions(entry.get("requires"), player.world_state, player.completed_quests, player):
                continue
            eligible.append((minimum, entry))
        if eligible:
            _, entry = max(eligible, key=lambda item: item[0])
            entry_id = str(entry.get("id", f"relation_{minimum}"))
            once = bool(entry.get("once", False))
            if once and player.get_flag(f"npc_relation_dialogue:{target_npc}:{entry_id}", False):
                # 已领取过一次性的高关系内容时，继续回退到下一档可用内容。
                remaining = []
                for candidate_min, candidate in eligible:
                    candidate_id = str(candidate.get("id", f"relation_{candidate_min}"))
                    candidate_used = bool(candidate.get("once")) and player.get_flag(
                        f"npc_relation_dialogue:{target_npc}:{candidate_id}", False
                    )
                    if not candidate_used:
                        remaining.append((candidate_min, candidate))
                if remaining:
                    _, entry = max(remaining, key=lambda item: item[0])
                    entry_id = str(entry.get("id", f"relation_{minimum}"))
                    once = bool(entry.get("once", False))
                else:
                    entry = None
            if entry is not None:
                print(f"{target_npc} 低声说道：“{Color.GREEN}{entry.get('text', '……')}{Color.RESET}”")
                reward = entry.get("reward")
                if reward:
                    from rewards import apply_reward_bundle
                    reward_result = apply_reward_bundle(player, reward, source="关系奖励")
                    if not isinstance(reward_result, dict) or not reward_result.get("ok"):
                        detail = reward_result.get("message", "奖励结算未成功。") if isinstance(reward_result, dict) else "奖励结算未成功。"
                        print(f"{Color.YELLOW}这份心意暂时无法交付：{detail}请整理好背包后再来。{Color.RESET}")
                        return False if busy_idle else None
                # 奖励先成功结算，再落地一次性对话效果；背包满等失败不会白白消耗剧情。
                player.apply_jianghu_effects(entry.get("effects"))
                engine.apply_world_effects(player.world_state, entry.get("effects"))
                if once:
                    player.set_flag(f"npc_relation_dialogue:{target_npc}:{entry_id}", True)

    # P2.22：数据驱动对话选项。输入 talk NPC 选项关键词即可改变关系。
    choices = npc_data.get("dialogue_choices", []) or []
    if topic and choices:
        for idx, choice in enumerate(choices, 1):
            if not isinstance(choice, dict):
                continue
            keywords = choice.get("keywords", [])
            if topic not in keywords and not any(k in topic for k in keywords):
                continue
            choice_id = str(choice.get("id", f"choice_{idx}"))
            if choice.get("once") and player.is_dialogue_choice_used(target_npc, choice_id):
                print("这段话题你已经与对方谈过了。")
                return
            requires = choice.get("requires")
            if requires and not engine.check_conditions(requires, player.world_state, player.completed_quests, player):
                print("对方似乎不愿继续这个话题。")
                return
            # 接引人的“拜师”选项应直接办理入门，避免登记申请后仍重复提示玩家再次提出拜师。
            admission_sects = {
                "华山接引执事": ("华山", "sect:huashan:entry_interview"),
                "少林接引僧": ("少林", "sect:shaolin:entry_interview"),
                "武当接引道人": ("武当", "sect:wudang:entry_interview"),
                "铁衣门接引执事": ("铁衣门", "sect:tieyi:entry_interview"),
            }
            admission = admission_sects.get(target_npc)
            if admission and any(k in topic for k in ("拜师", "入门申请", "申请入门", "加入")):
                sect_name, application_flag = admission
                current_level = int(getattr(player, "level", 1) or 1)
                if current_level < 10:
                    print(f"拜师失败：正式拜入【{sect_name}】需达到 10 级，当前 {current_level} 级。可先完成村中委托、采集、伐木、采矿与野外历练；输入“任务”查看进度，村中广场可查看公告。")
                    return
                player.set_flag(application_flag, True)
                print(f"{target_npc} 点头道：“既有拜师之意，便按门规办理入门。”")
                handle_sect(player, ["join", sect_name])
                player.update_quest_progress(target_npc, event_type="talk")
                return
            line = choice.get("response", "对方没有回答。")
            delta = int(choice.get("relation_delta", 0))
            relation_before = player.get_relation(target_npc)
            relation_status_before = player.get_relation_status(target_npc)
            relation_after = player.change_relation(target_npc, delta)
            relation_status_after = player.get_relation_status(target_npc)
            player.apply_jianghu_effects(choice.get("effects"))
            engine.apply_world_effects(player.world_state, choice.get("effects"))
            if choice.get("once"):
                player.mark_dialogue_choice_used(target_npc, choice_id)
            # 对话可记录剧情/考核线索；未配置此字段的既有选项行为不变。
            flag_name = choice.get("flag")
            if isinstance(flag_name, str) and flag_name.strip():
                player.set_flag(flag_name.strip(), True)
            print(f"{target_npc} 回应：“{Color.GREEN}{line}{Color.RESET}”")
            if relation_after != relation_before:
                print(f"关系变化：{relation_status_before} {relation_before:+d} → {relation_status_after} {relation_after:+d}")
            player.update_quest_progress(target_npc, event_type="talk")
            return

    # 闲聊只在玩家明确提到闲聊话题时触发，避免混入询问、交付等主交互流程。
    small_talk_words = ("闲聊", "闲谈", "寒暄", "家常", "近况", "营生", "生意", "近来")
    if topic and any(word in topic for word in small_talk_words):
        economy_context = _npc_economy_context(target_npc, getattr(player, "economy_state", {}), player.location)
        print(f"\n{Color.BRIGHT_CYAN}【闲谈】{Color.RESET}")
        if economy_context:
            print(f"{Color.CYAN}{economy_context}{Color.RESET}")
        else:
            dialogues = npc_data.get("dialogue", ["……"])
            line = random.choice(dialogues) if isinstance(dialogues, list) else dialogues
            print(f"{target_npc} 随口应道：“{Color.GREEN}{line}{Color.RESET}”")
        delta = int(npc_data.get("talk_relation_delta", 1))
        if behavior == "cold" and delta > 0:
            delta = 0
        if npc_state in {"fear", "injured", "angry", "event_affected"} and delta > 0:
            delta = 0
        if sect_stance in {"wary", "opposed"} and delta > 0:
            delta = 0
        if delta:
            cap = int(npc_data.get("talk_relation_cap", engine.DEFAULT_TALK_RELATION_CAP))
            before = player.get_relation(target_npc)
            before_status = player.get_relation_status(target_npc)
            after = player.change_talk_relation(target_npc, delta, cap)
            if after != before:
                print(f"关系变化：{before_status} {before:+d} → {player.get_relation_status(target_npc)} {after:+d}")
        player.update_quest_progress(target_npc, event_type="talk")
        return

    if topic:
        if behavior == "cold":
            print(f"{Color.YELLOW}{target_npc} 的态度明显冷淡：“有话就直说，别浪费我的时间。”{Color.RESET}")
        # P2.32：先尝试从该 NPC 的动态信息记忆中获取线索；关系越高，越容易听到可信消息。
        dynamic_learned = player.learn_information_from_npc(target_npc, topic)
        dynamic_record = None
        for learned_topic in dynamic_learned:
            if topic in learned_topic or learned_topic in topic:
                dynamic_record = player.get_player_information(learned_topic)
                break
        if dynamic_record:
            print(f"{target_npc} 压低声音回答说：“{Color.YELLOW}{dynamic_record.get('text', '')}{Color.RESET}”")
            print(f"消息可信度：{dynamic_record.get('confidence', 0)} / 100")
            player.change_talk_relation(target_npc, int(npc_data.get("ask_relation_delta", 1)), int(npc_data.get("talk_relation_cap", engine.DEFAULT_TALK_RELATION_CAP)))
            player.update_quest_progress(target_npc, event_type="talk")
            return
        info_dict = npc_data.get("info", {})
        matched_info = None
        for key_phrase, val_text in info_dict.items():
            if topic in key_phrase or key_phrase in topic:
                matched_info = val_text
                break
        if matched_info:
            print(f"{target_npc} 压低声音回答说：“{Color.YELLOW}{matched_info}{Color.RESET}”")
            delta = int(npc_data.get("ask_relation_delta", 1))
            if delta > 0:
                player.change_talk_relation(target_npc, delta, int(npc_data.get("talk_relation_cap", engine.DEFAULT_TALK_RELATION_CAP)))
            else:
                player.change_relation(target_npc, delta)
        else:
            # 没有对应情报时，若人物有当前世界状态对白，就用它回应，避免
            # “不知道”与随后完成交谈目标互相矛盾。
            conditional_line = _conditional_dialogue_text(player, npc_data)
            if conditional_line:
                print(f"{target_npc} {actor_display.npc_talk_verb(target_npc)}：“{Color.GREEN}{conditional_line}{Color.RESET}”")
            else:
                print(f"{target_npc} 摇了摇头：“关于‘{topic}’，老夫并不知道什么信息。”")
                player.change_relation(target_npc, int(npc_data.get("failed_ask_relation_delta", 0)))
        player.update_quest_progress(target_npc, event_type="talk")
        return

    print(f"{Color.CYAN}{npc_data.get('desc', '一言不发。')}{Color.RESET}")
    # Alpha241：固定 NPC 可按世界进展切换日常对白，让已完成的任务在场景中留下可感知的结果。
    # 条件按 priority 从高到低选择；没有满足条件的对白时，完全沿用原有随机对白。
    line = _conditional_dialogue_text(player, npc_data)
    if line is None:
        dialogues = npc_data.get("dialogue", ["……"])
        line = random.choice(dialogues) if isinstance(dialogues, list) else dialogues
    print(f"\n{target_npc} {actor_display.npc_talk_verb(target_npc)}：“{Color.GREEN}{line}{Color.RESET}”")
    delta = int(npc_data.get("talk_relation_delta", 1))
    if behavior == "cold" and delta > 0:
        delta = 0
    if npc_state in {"fear", "injured", "angry", "event_affected"} and delta > 0:
        delta = 0
    if sect_stance in {"wary", "opposed"} and delta > 0:
        delta = 0
    if delta:
        cap = int(npc_data.get("talk_relation_cap", engine.DEFAULT_TALK_RELATION_CAP))
        before = player.get_relation(target_npc)
        before_status = player.get_relation_status(target_npc)
        after = player.change_talk_relation(target_npc, delta, cap)
        applied = after - before
        if applied:
            after_status = player.get_relation_status(target_npc)
            print(f"关系变化：{before_status} {before:+d} → {after_status} {after:+d}")
        elif delta > 0:
            print("这番寒暄已经无法进一步拉近你们的关系了。")
    if choices:
        print("可选对话：" + " / ".join(str(c.get("keywords", [""])[0]) for c in choices if c.get("keywords")))
    player.update_quest_progress(target_npc, event_type="talk")

    _print_npc_quest_offers(player, target_npc, npc_quests)
    return False if busy_idle else None


BOARD_ROOMS = {"village_square", "guiyun_central_square"}


def _quests_for_npc(npc_name):
    """返回配置中明确由该 NPC 发布的任务，兼容旧版 NPC quests 列表。"""
    configured = [name for name, info in engine.QUESTS.items() if isinstance(info, dict) and info.get("npc") == npc_name]
    legacy = engine.NPCS.get(npc_name, {}).get("quests", []) or []
    return list(dict.fromkeys(configured + [q for q in legacy if q in engine.QUESTS]))


def _quest_command_query(topic, delivery=False):
    """从 NPC 话题中剥离接取/交付动作词，保留任务名原文。"""
    query = str(topic or "").strip()
    prefixes = ("交付委托", "交付任务", "交任务", "交差", "复命") if delivery else ("接受委托", "领取委托", "接受任务", "接取任务", "接任务")
    for prefix in prefixes:
        if query.startswith(prefix):
            return query[len(prefix):].strip()
    for prefix in (("交付",) if delivery else ("接受", "领取", "接取", "接下")):
        if query.startswith(prefix):
            return query[len(prefix):].strip()
    return query


def _quest_title(quest_name):
    """玩家界面统一使用任务显示名，内部键仅用于存档与状态判断。"""
    return engine.quest_display_name(quest_name)


def _print_delivery_choices(player, npc_name, quest_names):
    """按稳定顺序列出可交付任务、交付地点与可直接使用的完整指令。"""
    for index, quest_name in enumerate(quest_names, 1):
        print(f"{index} {_quest_title(quest_name)}")
        print(f"   {_quest_delivery_guidance(player, quest_name, npc_name)}")


def _normalize_quest_name(value):
    """任务名匹配统一忽略空格、间隔号及全半角标点。"""
    import unicodedata
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P"))


def _resolve_npc_quest_name(raw_name, quest_names):
    """按任务键/显示名精确或简称匹配；返回 (状态, 任务键列表)。"""
    import difflib
    query = _normalize_quest_name(raw_name)
    if not query:
        return "empty", []
    candidates = []
    exact = []
    for quest_name in quest_names:
        title = _quest_title(quest_name)
        aliases = {_normalize_quest_name(alias) for alias in engine.quest_aliases(quest_name)}
        aliases.discard("")
        candidates.append((quest_name, aliases, title))
        if query in aliases:
            exact.append(quest_name)
    if len(exact) == 1:
        return "matched", exact
    if len(exact) > 1:
        return "ambiguous", exact

    # 合理简称：输入连续出现在任务键或显示名中；多项命中必须让玩家选择。
    partial = [quest_name for quest_name, aliases, _ in candidates
               if any(query in alias for alias in aliases)]
    if len(partial) == 1:
        return "matched", partial
    if len(partial) > 1:
        return "ambiguous", partial

    all_aliases = {}
    for quest_name, aliases, title in candidates:
        for alias in aliases:
            all_aliases[alias] = quest_name
    close = difflib.get_close_matches(query, list(all_aliases), n=3, cutoff=0.48)
    suggestions = list(dict.fromkeys(all_aliases[name] for name in close))
    return ("missing", suggestions)


def _quest_npc_status(player, quest_name):
    """返回 NPC 对话使用的任务状态和自然语言反馈，不用于公告栏展示内部状态。"""
    info = engine.QUESTS.get(quest_name, {})
    if quest_name in player.active_quests:
        state = player.quest_states.get(quest_name, {})
        stages = info.get("stages") or []
        if stages:
            stage_index = min(int(state.get("stage", 0) or 0), len(stages) - 1)
            progress = int(state.get("progress", player.active_quests.get(quest_name, 0)) or 0)
            required = int(stages[stage_index].get("required_cnt", 1) or 1)
        else:
            progress = int(player.active_quests.get(quest_name, 0) or 0)
            required = int(info.get("required_cnt", 1) or 1)
        complete = player.is_quest_goal_complete(quest_name)
        detail = "目标已经办妥，等待你当面交付。" if complete else f"事情还没办完，目前进展为 {progress}/{required}。"
        return ("待交付" if complete else "进行中"), detail
    # V12/早期剧情旗标可能先于 completed_quests 列表写入；两种完成记录统一视为已交付，
    # 避免公告栏把已完成的前置任务再次当作可接委托，遮住真正开放的后续线索。
    quest_completed = quest_name in player.completed_quests or player.get_flag(f"quest_completed:{quest_name}", False)
    if quest_completed and not info.get("repeatable", False):
        return "已交付", "这件事已经交付完毕，多谢你先前相助。"
    # 可重复委托在冷却期内不能再次接取；对话与公告入口必须与“接取”判断一致，
    # 否则会先显示为可接取，玩家再操作才被拒绝。
    if quest_completed and info.get("repeatable", False):
        cooldown = max(0, int(info.get("repeat_cooldown_ticks", 0) or 0))
        if cooldown:
            last_completed = player.get_var(f"quest_repeat_last_completed:{quest_name}", None)
            if last_completed is not None:
                try:
                    remaining = cooldown - (player.get_quest_clock() - int(last_completed))
                except (TypeError, ValueError):
                    remaining = 0
                if remaining > 0:
                    return "未开放", f"这项历练刚刚完成过，需再等待 {remaining} 个世界时刻才能重新接取。"
    if player.get_flag(f"quest_failed:{quest_name}") and not info.get("retryable", True):
        return "已结束", "这件事已经错过时机，暂时不能再接。"
    if not engine.check_conditions(info.get("requires"), player.world_state, player.completed_quests, player):
        failures = engine.explain_condition_failures(info.get("requires"), player.world_state, player.completed_quests, player)
        # 多项未满足条件可能落到同一句泛化说明，去重后再拼接，避免重复刷屏。
        failures = list(dict.fromkeys(failures))
        if not failures:
            failures = ["尚有未满足的剧情条件（当前条件配置无法进一步说明）"]
        return "未开放", "接取条件未满足：" + "；".join(failures) + "。"
    return "未领取", "若愿意帮忙，可以当面接受这项委托。"


def _quest_delivery_guidance(player, quest_name, fallback_npc=""):
    """输出可交付任务的委托人、地点与完整指令。"""
    guide = player.get_quest_delivery_guide(quest_name)
    if not guide:
        npc_name = fallback_npc or "原委托人"
        return f"交付方式：回到【{npc_name}】处，输入“交谈 {npc_name} 交付委托 {_quest_title(quest_name)}”。"
    place = f"前往【{guide['location']}】" if guide.get("location") else "回到委托人处"
    return f"交付方式：{place}找【{guide['npc']}】，输入“{guide['command']}”。"


def _print_region_effect_changes(region_changes):
    """结算时直接展示任务选择对区域的实际影响。"""
    if not isinstance(region_changes, dict):
        return
    regions = getattr(engine, "WORLD_REGIONS", {}) or {}
    for zone, changes in region_changes.items():
        if not isinstance(changes, dict):
            continue
        parts = []
        for field, label in (("security", "安全度"), ("commerce", "商路"), ("travel", "通行")):
            delta = changes.get(field)
            if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
                continue
            parts.append(f"{label} {delta:+d}")
        if parts:
            name = str((regions.get(zone) or {}).get("name", zone))
            print(f"{Color.CYAN}区域变化：{name} {'、'.join(parts)}{Color.RESET}")


def _quest_difficulty_text(info):
    """任务难度只作展示与校验，不另建难度计算系统。"""
    difficulty = str((info or {}).get("difficulty", "")).strip()
    return f"【{difficulty}】" if difficulty else ""


def _print_npc_quest_offers(player, npc_name, quest_names, detailed=False):
    """按“可交付 > 进行中 > 可接取”分层；详细模式才列出未满足与已交付。"""
    if not quest_names:
        return
    available, active, deliverable, locked, completed = [], [], [], [], []
    for quest_name in quest_names:
        state, detail = _quest_npc_status(player, quest_name)
        if state == "未领取":
            available.append((quest_name, detail))
        elif state == "进行中":
            active.append((quest_name, detail))
        elif state == "待交付":
            deliverable.append((quest_name, detail))
        elif state == "未开放":
            locked.append((quest_name, detail))
        elif state == "已交付":
            completed.append((quest_name, detail))

    if deliverable:
        print("\n【可交付委托】")
        for quest_name, detail in deliverable:
            title = _quest_title(quest_name)
            print(f"{title}：{detail}")
            print(_quest_delivery_guidance(player, quest_name, npc_name))
    if active:
        print("\n【进行中委托】")
        for quest_name, detail in active:
            print(f"{_quest_title(quest_name)}：{detail}")
    if available:
        print("\n【可接取委托】")
        for quest_name, _ in available:
            info = engine.QUESTS.get(quest_name, {})
            title = _quest_title(quest_name)
            desc = str(info.get("desc", "有件事需要帮忙。"))
            print(f"{title}{_quest_difficulty_text(info)}：{desc}")
            print(f"接取方式：交谈 {npc_name} 接受委托 {title}")
    if detailed and locked:
        print("\n【当前不可接取】")
        for quest_name, detail in locked:
            print(f"{_quest_title(quest_name)}：{detail}")
        print("以上委托需先满足对应前置条件，完成后再来询问即可。")
    if detailed and completed:
        print("\n【已完成委托】")
        print("已交付：" + "、".join(_quest_title(quest_name) for quest_name, _ in completed))


def _public_topic_label(topic):
    """把内部情报主题转换成玩家可理解的江湖分类；绝不泄漏内部 topic ID。"""
    topic = str(topic or "")
    if topic.startswith("faction_conflict:"):
        return "势力冲突"
    if topic.startswith("faction:"):
        return "势力消息"
    if topic.startswith("region:"):
        return "区域动态"
    labels = {
        "guard_patrol_alert": "官府消息",
        "medicine_shortage": "民生消息",
        "new_wulin_rumor": "江湖传闻",
        "prison_alert": "官府警讯",
    }
    return labels.get(topic, "江湖消息")


def _public_information_records(player):
    """筛选可公开张贴到公告栏的消息，隐藏空文本及纯内部状态记录。"""
    records = []
    for record in player.list_information_summary():
        text = str(record.get("text", "")).strip()
        confidence = int(record.get("confidence", 0) or 0)
        if not text or confidence <= 0:
            continue
        item = dict(record)
        item["label"] = _public_topic_label(record.get("topic"))
        records.append(item)
    records.sort(key=lambda x: int(x.get("learned_at", 0) or 0), reverse=True)
    return records


def _quest_notice_clues(player=None):
    """只公布当前确实能向发布 NPC 接取的任务线索；不暴露任务名或内部状态。"""
    if player is None:
        return []
    priority_lines = []
    lines = []
    seen = set()
    # 同一发布人只公布一条当前可接委托，避免后续任务或多条委托同时刷屏。
    seen_givers = set()
    for quest_name, info in engine.QUESTS.items():
        if not isinstance(info, dict):
            continue
        notice = str(info.get("notice", "")).strip()
        giver = str(info.get("npc", "")).strip()
        if not notice or not giver or giver not in engine.NPCS or giver in seen_givers:
            continue
        location = str(info.get("notice_location", "")).strip()
        if location and not any(room.get("name") == location for room in engine.ROOMS.values()):
            continue

        # 与 NPC 实际接取入口共用任务状态判断：完整 requires（等级、关系、门派、
        # 物品、世界旗标等）必须满足，且任务不能已接取、已交付或已结束。
        quest_state, _detail = _quest_npc_status(player, quest_name)
        if quest_state != "未领取":
            continue

        if notice in seen:
            seen_givers.add(giver)
            continue
        seen.add(notice)
        seen_givers.add(giver)
        requires = info.get("requires")
        has_prerequisites = isinstance(requires, dict) and bool(requires)
        # 新开放的后续委托优先展示，但同一发布人仍只保留第一条可接线索。
        if has_prerequisites:
            priority_lines.append(notice)
        else:
            lines.append(notice)
    return priority_lines + lines


def handle_notice_board(player, args=None):
    """Alpha226：公告栏展示自然语言线索；不展示任务状态、内部任务名或接取指令。"""
    args = args or []
    if player.location not in BOARD_ROOMS:
        print("附近没有公告栏。可前往村中广场或天衡广场查看江湖榜墙。")
        return
    room_name = engine.ROOMS.get(player.location, {}).get("name", "公告栏")
    records = _public_information_records(player)
    title = "村中公告栏" if player.location == "village_square" else "天衡公告栏 · 江湖榜墙"
    print(f"\n{Color.BRIGHT_CYAN}========== {title} =========={Color.RESET}")
    print(f"{room_name}上张贴着近日流传的消息。")
    grouped = {"委托线索": [], "地方消息": [], "江湖见闻": [], "势力摘要": []}
    conflict_topics = []
    region_notice = False
    seen_text = set()
    for record in records:
        topic = str(record.get("topic", ""))
        raw_text = re.sub(r"\s*[（(]\s*可信度\s*\d+\s*/\s*100.*?[）)]\s*$", "", str(record.get("text", ""))).strip()
        raw_text = re.sub(r"\s*[（(]\s*有效至时辰\s*\d+\s*[）)]\s*$", "", raw_text).strip()
        if topic.startswith("faction_conflict:"):
            conflict_topics.append(topic)
            continue
        if topic.startswith("region:") or "安全度" in raw_text or "局势变为" in raw_text:
            region_notice = True
            continue
        if not raw_text or raw_text in seen_text:
            continue
        seen_text.add(raw_text)
        label = record["label"]
        bucket = "江湖见闻" if label == "江湖传闻" else ("势力摘要" if label in ("势力消息", "势力冲突") else "地方消息")
        grouped[bucket].append(raw_text)
    if conflict_topics:
        factions = []
        for topic in conflict_topics:
            for faction in topic.split(":")[1:]:
                faction = faction.strip()
                if faction and faction not in factions:
                    factions.append(faction)
        if len(factions) >= 2:
            grouped["势力摘要"].append(f"近期{'、'.join(factions[:4])}之间摩擦增多，出行时宜留意盘查与道路动静。")
        else:
            grouped["势力摘要"].append("近期当地势力关系紧张，出行时宜多加留意。")
    if region_notice:
        grouped["势力摘要"].append("周边数处局势不稳，出行时宜留意道路与巡查变化。")
    if player.location == "village_square":
        grouped["委托线索"].extend(_quest_notice_clues(player))
    printed = 0
    total_limit = 7
    for section in ("委托线索", "地方消息", "江湖见闻", "势力摘要"):
        if printed >= total_limit:
            break
        lines = list(dict.fromkeys(grouped[section]))
        if not lines:
            continue
        lines = lines[:min(5 if section == "委托线索" else 3, total_limit - printed)]
        if not lines:
            continue
        print(f"\n【{section}】")
        for line in lines:
            print(f"- {line}")
            printed += 1
    if not printed:
        print("暂时没有新的消息。多走动、多与人物交谈，江湖消息自然会汇聚而来。")
    if player.location == "village_square":
        print("\n以上仅为消息线索，具体委托请与相关人物交谈领取。")


def handle_information(player, args=None):
    """P2.51：查看个人掌握的江湖消息；公开消息统一在公告栏查看。"""
    args = args or []
    if args and args[0].lower() in ("memory", "memories", "记忆", "评价"):
        npc_name = args[1] if len(args) > 1 and args[1] in engine.NPCS else None
        records = player.list_npc_memory_summary(npc_name)
        if not records:
            print("当前没有可见的 人物对你的记忆。")
            return
        print("\n【人物对你的记忆】")
        for record in records:
            sentiment_labels = {"positive": "友善", "negative": "不满", "neutral": "中立", "fearful": "戒备"}
            sentiment = sentiment_labels.get(record.get("sentiment", "neutral"), "中立")
            print(f"- {record['npc']}：{record['text']}（{sentiment}，强度 {int(record.get('strength',0))}）")
        if npc_name:
            print(f"当前评价倾向：{player.get_npc_memory_attitude(npc_name)}（综合 {player.get_npc_player_reputation(npc_name):+d}）")
        return
    if not args:
        if player.location in BOARD_ROOMS:
            handle_notice_board(player)
            return
        records = _public_information_records(player)
        print(f"\n{Color.BRIGHT_CYAN}========== 你听来的消息 =========={Color.RESET}")
        if not records:
            print("目前没有可靠的额外消息。多与人物交谈，或前往村中广场、天衡广场查看公告。")
        for record in records:
            expiry = record.get("expires_at")
            expires = f"｜有效至 {format_world_clock(expiry)}" if expiry is not None else "｜长期"
            print(f"- 【{record['label']}】{record.get('text','')}（可信度 {int(record.get('confidence',0))}/100{expires}）")
        print("用法：信息 <话题>；公开消息可在村中广场、天衡广场查看公告。")
        return
    topic = " ".join(args)
    npcs = player.get_npcs_in_room(player.location)
    if not npcs:
        print("此地没有人物可以继续打听消息。")
        return
    for npc in npcs:
        learned = player.learn_information_from_npc(npc, topic)
        if learned:
            record = next((player.get_player_information(k) for k in learned if topic in k or k in topic), None)
            if record:
                print(f"{npc} 告诉你：“{Color.YELLOW}{record.get('text','')}{Color.RESET}”")
                print(f"消息可信度：{record.get('confidence',0)} / 100")
                return
    print(f"在场人物没有人愿意透露与“{topic}”有关的新消息。")


def _skill_rank_requirement_label(player, rank_index):
    """把武学配置中的阶位索引转换为玩家熟悉的正式门派职位名称。"""
    ranks = (engine.SECTS.get(player.get_sect(), {}) or {}).get("ranks", []) or []
    try:
        index = int(rank_index)
    except (TypeError, ValueError):
        index = 0
    if 0 <= index < len(ranks):
        return str(ranks[index].get("name", f"第 {index + 1} 阶身份"))
    return f"第 {index + 1} 阶身份"


def handle_skills(player, args=None):
    """武学总入口：查看、学习、遗忘；门派传承武学需在对应传功地点请教。"""
    args = args or []
    if not args:
        print(f"\n{Color.BRIGHT_CYAN}╔══════════════ 当前武学 ══════════════╗{Color.RESET}")
        for info in player.get_skill_summary():
            if info["learned"]:
                availability = "" if info.get("usable", True) else "｜当前职位不足，暂不可施展"
                print(f"【{info['name']}】{info.get('title', '初学乍练')}｜武学等级 {info['level']} / 熟练度 {info['mastery']}/{info['mastery_max']}（角色等级要求 {info['character_level']}）{availability}")
            else:
                rank_label = _skill_rank_requirement_label(player, info["learn_min_rank"])
                rank_requirement = f"职位 {rank_label}" if info["learn_min_rank"] > 0 else "基础职位即可"
                print(f"【{info['name']}】未学习｜需要等级 {info['character_level']} / 声望 {info['learn_min_reputation']} / {rank_requirement}")
        print("用法：武学｜武学 学习 <武学>｜武学 遗忘 <武学>｜武学 查看 <武学>")
        print(f"{Color.BRIGHT_CYAN}╚══════════════════════════════════════╝{Color.RESET}")
        return
    sub = str(args[0]).lower()
    name = " ".join(args[1:]) if len(args) > 1 else ""
    if sub in ("learn", "学习", "修习") and name:
        skill_owner = next((sect for sect, rows in engine.SKILLS.items()
                            if any(isinstance(row, dict) and row.get("name") == name for row in (rows or []))), None)
        progress = player.get_skill_progress(name) if player.get_skill_info(name) else {"learned": False}
        # 门派传承武学的授课地点与授课者由 data/sects.json 配置，
        # 避免新增门派/武学时继续堆叠硬编码分支。
        if skill_owner and skill_owner == player.get_sect() and not progress.get("learned"):
            sect_info = engine.SECTS.get(skill_owner, {}) or {}
            training = sect_info.get("training", {}) or {}
            teacher_by_skill = sect_info.get("skill_teachers", {}) or {}
            required_teacher = teacher_by_skill.get(name)
            room_id = training.get("room_id")
            place = training.get("place", "本门演武场")
            if required_teacher and room_id:
                if player.location != room_id:
                    print(f"{Color.YELLOW}学习本门武学须前往{place}，向对应传功师长请教。{Color.RESET}")
                    return
                if required_teacher not in player.get_npcs_in_room(player.location):
                    teacher_label = "传功师父" if "师父" in required_teacher or "授业师父" in required_teacher else "传功师兄"
                    print(f"{Color.YELLOW}{place}当前没有{teacher_label}在场，暂时无法传授【{name}】。{Color.RESET}")
                    return
        ok, msg = player.learn_skill(name)
        print(f"{Color.GREEN if ok else Color.RED}{msg}{Color.RESET}")
        return
    if sub in ("forget", "遗忘", "忘却") and name:
        ok, msg = player.forget_skill(name)
        print(f"{Color.YELLOW if ok else Color.RED}{msg}{Color.RESET}")
        return
    if sub in ("info", "详情", "查看") and name:
        info = player.get_skill_info(name)
        if not info:
            print(f"不存在武学【{name}】。")
            return
        progress = player.get_skill_progress(name)
        skill_owner = next((sect for sect, rows in engine.SKILLS.items()
                            if any(isinstance(row, dict) and row.get("name") == name for row in (rows or []))), None)
        if skill_owner and skill_owner != player.get_sect():
            current_sect = player.get_sect()
            print(f"【{name}】属于【{skill_owner}】门派传承武学；你当前身份为【{current_sect}】，不能在当前身份下修习或施展。")
            if progress.get("learned"):
                print(f"既往修习记录：{progress.get('title', '初学乍练')} / 熟练度 {progress['mastery']}/{progress['mastery_max']}（仅保留历练记录，不代表当前可用）")
            else:
                print("当前没有这门武学的已学记录。")
        else:
            print(f"【{name}】：{progress.get('title', '初学乍练')} / 威力 {float(info.get('power', 0)):.2f} / 耗内 {info.get('mp_cost', 0)} / 武学等级 {progress['level']} / 熟练度 {progress['mastery']}/{progress['mastery_max']}")
        if info.get("desc"):
            print(f"招式描写：{info['desc']}")
        if info.get("combat_hint"):
            print(f"运用提示：{info['combat_hint']}")
        rank_label = _skill_rank_requirement_label(player, info.get("learn_min_rank", 0))
        rank_requirement = f"正式职位：{rank_label}" if int(info.get("learn_min_rank", 0)) > 0 else "正式职位：基础弟子即可"
        print(f"学习条件：角色等级 {info.get('level', 1)} / 门派声望 {info.get('learn_min_reputation', 0)} / {rank_requirement}")
        return
    print("用法：武学｜武学 学习 <武学>｜武学 遗忘 <武学>｜武学 查看 <武学>")


def handle_sect(player, args=None):
    """门派总入口：查看、拜入、退出、声望与门派关系。"""
    args = list(args or [])
    # 命令解析层为兼容旧 MUD 输入会将门派参数合并为单个字符串，
    # 在此恢复子命令边界，兼容“sect join 少林”和“门派 加入 华山”。
    if len(args) == 1 and isinstance(args[0], str) and " " in args[0].strip():
        args = args[0].split()
    if not args:
        summary = player.get_sect_summary()
        print(f"\n{Color.BRIGHT_CYAN}========== 门派信息 =========={Color.RESET}")
        print(f"当前门派：{Color.MAGENTA}{summary['title']}{Color.RESET}（{summary['name']}）")
        print(f"门派定位：{summary['alignment']}")
        print(f"门派声望：{summary['reputation']}")
        print(f"简介：{summary['desc']}")
        skills = summary.get("exclusive_skills", [])
        print(f"门派武学：{'、'.join(skills) if skills else '无'}")
        if summary.get("relations"):
            print("门派关系：" + "；".join(f"{k} {v:+d}" for k, v in summary["relations"].items()))
        questline = player.get_sect_questline_summary()
        if questline:
            print(f"{Color.BRIGHT_CYAN}---------- 门派任务线 ----------{Color.RESET}")
            status_labels = {
                "completed": "已完成", "active": "进行中",
                "available": "可接取", "locked": "未解锁",
            }
            for entry in questline:
                label = status_labels.get(entry["status"], entry["status"])
                optional = "（可选）" if entry.get("optional") else ""
                line = f"  [{label}] {entry['title']}{optional}"
                if entry.get("giver"):
                    line += f"｜发布：{entry['giver']}"
                if entry.get("location"):
                    line += f"｜地点：{entry['location']}"
                print(line)
                if entry["status"] == "locked" and entry.get("missing"):
                    print("      条件：" + "；".join(entry["missing"]))
        print("用法：门派 查看 <门派> / 拜师 <门派> / 门派 晋升 / 门派 修习 / 门派 受戒（少林） / 门派 师徒 拜师 / 门派 师徒 请教 / 门派 声望 / 门派 关系 / 门派 退出")
        print(f"{Color.BRIGHT_CYAN}=============================={Color.RESET}")
        return

    sub = str(args[0]).lower()
    if sub in ("info", "详情", "查看") and len(args) >= 2:
        sect_name = " ".join(args[1:])
        if sect_name not in engine.SECTS:
            print(f"{Color.RED}不存在门派：【{sect_name}】。{Color.RESET}")
            return
        info = player.get_sect_summary(sect_name)
        print(f"\n{Color.BRIGHT_YELLOW}【{info['title']}】{Color.RESET}")
        print(info["desc"]); print(f"定位：{info['alignment']} | 当前声望：{info['reputation']}")
        print(f"对应身份：{info['rank']}")
        print(f"可用武学：{'、'.join(info['exclusive_skills']) if info['exclusive_skills'] else '无'}")
        if info.get("relations"):
            print("门派关系：" + "；".join(f"{k} {v:+d}" for k, v in info["relations"].items()))
        return

    if sub in ("join", "加入", "拜入", "拜师") and len(args) >= 2:
        sect_name = " ".join(args[1:])
        if sect_name == "华山":
            if player.location != "huashan_guest_hall":
                print(f"{Color.YELLOW}拜入华山需亲自前往华山迎客厅，向接引执事说明来意并办理入门申请。{Color.RESET}")
                return
            if not player.get_flag("sect:huashan:entry_interview", False):
                print(f"{Color.YELLOW}接引执事尚未登记你的入门申请。请先交谈华山接引执事，并说明“拜师”。{Color.RESET}")
                return
        if sect_name == "少林":
            if player.location != "shaolin_guest_hall":
                print(f"{Color.YELLOW}拜入少林需亲自前往少林迎客堂，向接引僧说明来意并办理入门申请。{Color.RESET}")
                return
            if not player.get_flag("sect:shaolin:entry_interview", False):
                print(f"{Color.YELLOW}接引僧尚未登记你的入门申请。请先交谈少林接引僧，并说明“拜师”。{Color.RESET}")
                return
        if sect_name == "武当":
            if player.location != "wudang_guest_hall":
                print(f"{Color.YELLOW}拜入武当需亲自前往武当迎客厅，向接引道人说明来意并办理入门申请。{Color.RESET}")
                return
            if not player.get_flag("sect:wudang:entry_interview", False):
                print(f"{Color.YELLOW}接引道人尚未登记你的入门申请。请先交谈武当接引道人，并说明“拜师”。{Color.RESET}")
                return
        if sect_name == "铁衣门":
            if player.location != "tieyi_guest_hall":
                print(f"{Color.YELLOW}拜入铁衣门需亲自前往铁衣门接待堂，向接引执事说明来意并办理入门申请。{Color.RESET}")
                return
            if not player.get_flag("sect:tieyi:entry_interview", False):
                print(f"{Color.YELLOW}接引执事尚未登记你的入门申请。请先交谈铁衣门接引执事，并说明“拜师”。{Color.RESET}")
                return
        # 正式入门统一要求达到 10 级；山门访问、交谈和了解门规不受此限制。
        if int(getattr(player, "level", 1) or 1) < 10:
            print(f"{Color.YELLOW}正式拜入【{sect_name}】需达到 10 级，你当前为 {int(getattr(player, 'level', 1) or 1)} 级。可先完成村中委托、采集、制作与野外历练；输入“任务”查看进度，村中广场可查看公告。{Color.RESET}")
            return
        ok, message = player.join_sect(sect_name)
        if ok and sect_name == "华山":
            player.set_flag("sect:huashan:joined", True)
            player.set_flag("sect:huashan:entry_interview", False)
            player.change_relation("华山接引执事", 8)
            message += " 接引执事在访客簿上记下你的身份，并嘱咐你前往演武场向传功师兄请教。"
        elif ok and sect_name == "少林":
            player.set_flag("sect:shaolin:joined", True)
            player.set_flag("sect:shaolin:entry_interview", False)
            player.change_relation("少林接引僧", 8)
            message += " 接引僧登记了你的身份，并嘱咐你前往罗汉场向传功师父打好武学根基。"
        elif ok and sect_name == "武当":
            player.set_flag("sect:wudang:joined", True)
            player.set_flag("sect:wudang:entry_interview", False)
            player.change_relation("武当接引道人", 8)
            message += " 接引道人登记了你的身份，并嘱咐你先到太和演武场向传功师父请教基础剑法。"
        elif ok and sect_name == "铁衣门":
            player.set_flag("sect:tieyi:joined", True)
            player.set_flag("sect:tieyi:entry_interview", False)
            player.change_relation("铁衣门接引执事", 8)
            message += " 接引执事登记了你的身份，并嘱咐你前往演武场打好横练根基，再承担护运历练。"
        print(f"{Color.GREEN if ok else Color.RED}{message}{Color.RESET}")
        return

    if sub in ("受戒", "剃度", "戒仪"):
        if player.get_sect() != "少林":
            print("受戒仪礼仅适用于已正式拜入少林的弟子。")
            return
        if player.location != "shaolin_dharma_hall":
            print("须亲自前往少林讲经堂，在戒律僧面前办理受戒仪礼。")
            return
        if "少林戒律僧" not in player.get_npcs_in_room(player.location):
            print("戒律僧此刻不在讲经堂，暂时无法主持仪礼。")
            return
        rank_index = player.get_sect_official_rank_index("少林")
        if rank_index == 0:
            flag = "sect:shaolin:ordination:novice"
            target_name = "沙弥"
            required_level, required_rep, required_mastery = 3, 20, 10
            rite_name = "入门受戒"
        elif rank_index == 1:
            flag = "sect:shaolin:ordination:full"
            target_name = "僧人"
            required_level, required_rep, required_mastery = 8, 50, 30
            rite_name = "正式受戒"
        else:
            print("你已完成当前阶段所需的受戒仪礼，无需重复办理。")
            return
        skill_name = (engine.SECTS.get("少林", {}) or {}).get("exclusive_skills", [""])[0]
        mastery = player.get_skill_progress(skill_name).get("mastery", 0) if skill_name else 0
        missing = []
        if player.level < required_level:
            missing.append(f"人物等级需达到 {required_level} 级")
        if player.get_sect_reputation("少林") < required_rep:
            missing.append(f"少林声望需达到 {required_rep}")
        if mastery < required_mastery:
            missing.append(f"罗汉拳熟练度需达到 {required_mastery}")
        if missing:
            print("受戒条件尚未满足：" + "；".join(missing) + "。")
            return
        if player.get_flag(flag, False):
            print(f"你已完成{rite_name}，可向传功师兄申请晋升为【{target_name}】。")
            return
        player.set_flag(flag, True)
        player.change_relation("少林戒律僧", 5)
        print(f"戒律僧依寺规为你主持{rite_name}。仪礼已记录；请前往少林罗汉场，向传功师兄申请晋升为【{target_name}】。")
        return

    if sub in ("promote", "promotion", "晋升", "授阶"):
        if player.get_sect() == "散人":
            print(f"{Color.YELLOW}你尚未加入门派，无法办理晋升。{Color.RESET}")
            return
        if player.get_sect() in ("华山", "少林", "武当", "铁衣门"):
            sect_name = player.get_sect()
            sect_info = engine.SECTS.get(sect_name, {}) or {}
            training = sect_info.get("training", {}) or {}
            training_room = training.get("room_id", {"华山": "huashan_training_ground", "少林": "shaolin_training_ground", "武当": "wudang_training_ground", "铁衣门": "tieyi_training_ground"}[sect_name])
            examiner = training.get("promotion_teacher", {"华山": "华山传功师兄", "少林": "少林传功师兄", "武当": "武当传功师兄", "铁衣门": "铁衣门传功师父"}[sect_name])
            place = training.get("place", {"华山": "华山演武场", "少林": "少林罗汉场", "武当": "太和演武场", "铁衣门": "铁衣门演武场"}[sect_name])
            teacher_title = training.get("promotion_title", "传功师父" if sect_name == "铁衣门" else "传功师兄")
            if player.location != training_room:
                print(f"{Color.YELLOW}{sect_name}弟子须亲自前往{place}，向{examiner}申请考核晋升。{Color.RESET}")
                return
            if examiner not in player.get_npcs_in_room(player.location):
                print(f"{Color.YELLOW}{examiner}此刻不在场，暂时无法进行晋升考核。{Color.RESET}")
                return
            relation = player.get_relation(examiner)
            if relation < -20:
                print(f"{Color.YELLOW}{teacher_title}对你仍有戒心，请先修复关系，再谈晋升。{Color.RESET}")
                return
        ok, message = player.promote_sect_rank()
        if ok and player.get_sect() in ("华山", "少林", "武当", "铁衣门"):
            sect_info = engine.SECTS.get(player.get_sect(), {}) or {}
            training = sect_info.get("training", {}) or {}
            examiner = training.get("promotion_teacher", {"华山": "华山传功师兄", "少林": "少林传功师兄", "武当": "武当传功师兄", "铁衣门": "铁衣门传功师父"}[player.get_sect()])
            player.change_relation(examiner, 5)
        print(f"{Color.GREEN if ok else Color.YELLOW}{message}{Color.RESET}")
        return

    if sub in ("修习", "请教", "门派修习", "练功"):
        sect_name = player.get_sect()
        sect_info = engine.SECTS.get(sect_name, {}) or {}
        training = sect_info.get("training", {}) or {}
        if not training.get("room_id") or not training.get("lesson_teacher"):
            print("你尚未加入可办理门派修习的门派。")
            return
        room_id = training["room_id"]
        place = training.get("place", "本门演武场")
        teacher = training["lesson_teacher"]
        if player.location != room_id:
            print(f"门派修习须亲自前往{place}，向授业师长请教。")
            return
        if teacher not in player.get_npcs_in_room(player.location):
            print("授业师长此刻不在场，暂时无法指点修习。")
            return
        now = player.get_quest_clock()
        cooldown_key = f"sect:reputation_lesson:last_tick:{sect_name}"
        last_tick = player.get_var(cooldown_key, None)
        if last_tick is not None:
            try:
                elapsed = now - int(last_tick)
            except (TypeError, ValueError):
                elapsed = 4
            if elapsed < 4:
                print(f"师长已为你指点过功课，请再历练 {4 - max(0, elapsed)} 个世界时刻后回来。")
                return
        new_rep = player.change_sect_reputation(sect_name, 5)
        player.set_var(cooldown_key, now)
        skill = (engine.SECTS.get(sect_name, {}) or {}).get("exclusive_skills", ["本门武学"])[0]
        print(f"{teacher}结合【{skill}】为你讲解基本功与门规。此次修习记入门内考评，{sect_name}声望提升 5，当前为 {new_rep}。")
        return

    if sub in ("师徒", "师承", "mentorship", "师门"):
        operation = str(args[1]).lower() if len(args) >= 2 else "查看"
        if player.get_sect() != "华山":
            print("师承事务目前仅在华山开放；请先正式拜入华山。")
            return
        if player.location != "huashan_training_ground":
            print("师承事务须亲自前往华山演武场办理。")
            return
        present = player.get_npcs_in_room(player.location)
        if "华山授业师父" not in present:
            print("授业师父此刻不在演武场，暂时无法办理师承事务。")
            return
        if operation in ("拜师", "建立", "行礼"):
            ok, message = player.establish_sect_mentorship("华山授业师父")
            print(f"{Color.GREEN if ok else Color.YELLOW}{message}{Color.RESET}")
            return
        if operation in ("请教", "指点", "上课"):
            ok, message = player.record_mentorship_lesson()
            if ok:
                player.change_sect_reputation("华山", 1)
            print(f"{Color.GREEN if ok else Color.YELLOW}{message}{Color.RESET}")
            return
        if operation in ("查看", "身份", "状态"):
            print("师承信息已整合到“人物面板”，输入“状态”即可查看；此处保留拜师与请教操作。")
            return
        print("用法：门派 师徒 拜师 / 门派 师徒 请教")
        return

    if sub in ("rank", "身份", "授阶记录"):
        print("门派职位已整合到“人物面板”，输入“状态”即可查看；需要晋升时输入“门派 晋升”办理考核。")
        return

    if sub in ("leave", "退出", "退门"):
        ok, message = player.leave_sect()
        print(f"{Color.GREEN if ok else Color.YELLOW}{message}{Color.RESET}")
        return

    if sub in ("rep", "reputation", "声望"):
        print(f"当前【{player.get_sect()}】门派声望：{player.get_sect_reputation()}")
        return

    if sub in ("relations", "relation", "关系"):
        current = player.get_sect()
        print(f"【{current}】门派关系：")
        for name, info in engine.SECTS.items():
            if name == current:
                continue
            print(f"- {name}：{player.get_sect_relation(name):+d}")
        return

    print("用法：门派 / 门派 查看 <门派> / 拜师 <门派> / 门派 晋升 / 门派 师徒 拜师 / 门派 师徒 请教 / 门派 退出 / 门派 声望 / 门派 关系")



def handle_factions(player, args=None):
    """P2.41 势力生态：查看动态势力关系。"""
    args = args or []
    if args and str(args[0]).lower() in ("info", "详情", "查看") and len(args) >= 2:
        faction = " ".join(args[1:])
        info = engine.FACTIONS.get(faction)
        if not info:
            print(f"{Color.RED}不存在势力【{faction}】。{Color.RESET}")
            return
        print(f"\n{Color.BRIGHT_YELLOW}【{info.get('title', faction)}】{Color.RESET}")
        print(info.get("desc", ""))
        print(f"定位：{info.get('stance', '未定义')} | 影响力：{player.get_faction_influence(faction)}")
        for other in engine.FACTIONS:
            if other == faction:
                continue
            print(f"- {other}：{player.get_faction_relation(faction, other):+d}（{player.get_faction_stance(faction, other)}）")
        return
    print(f"\n{Color.BRIGHT_CYAN}========== 江湖势力 =========={Color.RESET}")
    for row in player.get_faction_summary():
        hostile = [x for x in row["relations"] if x["relation"] <= -20]
        friendly = [x for x in row["relations"] if x["relation"] >= 20]
        print(f"【{row['faction']}】{row['title']} | 影响力 {row['influence']} | {row['stance']}")
        if friendly:
            print("  友好：" + "、".join(f"{x['faction']} {x['relation']:+d}" for x in friendly))
        if hostile:
            print("  对立：" + "、".join(f"{x['faction']} {x['relation']:+d}" for x in hostile))
    print("用法：势力 / 势力 查看 <势力>")

def handle_player_influence(player, args=None):
    """P2.45 查看玩家对江湖势力的影响。"""
    print("\n========== 玩家势力影响 ==========")
    for row in player.get_player_world_influence_summary():
        print(f"- {row['faction']}：{row['influence']:+d}")
    print("影响会随着任务、事件和选择逐渐变化。")


def handle_faction_conflicts(player, args=None):
    """P2.43 查看动态势力冲突与世界局势。"""
    rows = player.get_faction_conflicts()
    print(f"\n{Color.BRIGHT_RED}========== 势力冲突局势 =========={Color.RESET}")
    level_labels = {"calm": "平静", "tension": "紧张", "confrontation": "对峙", "conflict": "冲突", "escalation": "升级", "war": "战争"}
    if not rows:
        print("当前尚未形成持续性的势力冲突。")
    for row in rows:
        if row["level"] == "calm":
            continue
        a, b = row["factions"]
        print(f"- {a} ↔ {b}：{level_labels.get(row['level'], row['level'])} | 压力 {row['pressure']} | 关系 {row['relation']:+d}")
    print(f"世界紧张度：{int(player.get_var('world_tension', 0))}")
    print("用法：冲突 / 局势")


def handle_security_governance(player, args=None):
    """Alpha86：展示当地治安治理状态与可参与的恶人清剿目标。"""
    args = args or []
    room = engine.ROOMS.get(getattr(player, "location", ""), {}) or {}
    zone = str(room.get("zone", "main"))
    zone_name = (engine.WORLD_REGIONS.get(zone, {}) or {}).get("name", zone)
    ecology = player.get_region_ecology(zone)
    from region_activity import get_security_incident, get_config, assist_world_crisis, list_world_crises
    incident = get_security_incident(player, zone)
    if args and str(args[0]).lower() in ("协助", "处置", "救援", "平乱"):
        ok, message, _crisis = assist_world_crisis(player, zone)
        print((Color.BRIGHT_GREEN if ok else Color.BRIGHT_YELLOW) + message + Color.RESET)
    print(f"\n{Color.BRIGHT_CYAN}========== 地区治安治理 =========={Color.RESET}")
    print(f"所在地区：{zone_name} | 安全度：{int(ecology.get('security', 70))}/100 | 商路：{int(ecology.get('commerce', 70))}/100")
    status = incident.get("status")
    if status == "active":
        required = max(1, int(incident.get("required_patrols", 1)))
        progress = max(0, int(incident.get("progress", 0)))
        print(f"当前事件：{incident.get('title', '地区治安事件')}（进度 {progress}/{required}）")
        print(str(incident.get("result_text", "官府正在处理当地治安问题。")))
        print("参与方式：协助巡逻人员，或在本地区击败悬赏目标；有效行动会推进事件。")
    elif status == "completed":
        print(f"最近事件：{incident.get('title', '地区治安事件')}（已完成）")
        print(str(incident.get("result_text", "当地治安有所改善。")))
    elif status == "expired":
        print(f"最近事件：{incident.get('title', '地区治安事件')}（未能及时完成）")
        print(str(incident.get("result_text", "当地治安问题仍未解决。")))
    else:
        print("当前没有正在进行的官府治安事件。治安恶化时，官府可能组织巡查或缉查。")
    config = get_config()
    targets = []
    criminal_profiles = config.get("criminal_enemies", {}) or {}
    if args and str(args[0]).lower() not in ("悬赏", "目标", "查看", "榜", "bounty", "协助", "处置", "救援", "平乱"):
        print("用法：治安 / 治安 悬赏 / 治安 协助")
        return
    for pool in (config.get("extra_enemy_pools", {}) or {}).get(zone, []) or []:
        try:
            threshold = int(pool.get("max_security", -1))
        except (TypeError, ValueError):
            continue
        if int(ecology.get("security", 70)) <= threshold:
            targets.extend(str(name) for name in pool.get("enemies", []) if name in criminal_profiles)
    urban = config.get("urban_crime", {}) or {}
    if zone == urban.get("zone") and getattr(player, "location", "") in (urban.get("rooms", []) or []):
        targets.extend(str(name) for name in (urban.get("enemies", []) or []) if name in criminal_profiles)
        if int(ecology.get("security", 70)) <= int(urban.get("severe_threshold", 20)):
            targets.extend(str(name) for name in (urban.get("severe_enemies", []) or []) if name in criminal_profiles)
    targets = list(dict.fromkeys(targets))
    print("可关注的治安目标：" + ("、".join(targets) if targets else "当前地区暂无额外配置的恶人悬赏目标。"))
    print("提示：击败当地恶人可改善治安；普通野兽通常不计入治安功绩。重复目标受冷却限制，不能无限刷取。")


def handle_region_ecology(player, args=None):
    """查询当前/指定/全部区域的生态状态与关联事件。"""
    args = args or []
    regions = getattr(engine, "WORLD_REGIONS", {}) or {}
    zone_names = {str(info.get("name", zone)): zone for zone, info in regions.items() if isinstance(info, dict)}
    target = " ".join(str(x) for x in args).strip()
    show_all = target.lower() in ("all", "全部", "各地", "全域")
    if show_all:
        zones = list(regions.keys())
    elif target:
        zone = target if target in regions else zone_names.get(target)
        if not zone:
            print("找不到该区域。可输入“区域 全部”查看各地，或使用地图上的区域名称。")
            return
        zones = [zone]
    else:
        zones = [engine.ROOMS.get(player.location, {}).get("zone", "main")]

    level_labels = {"calm": "平静", "tension": "紧张", "confrontation": "对峙", "conflict": "冲突", "escalation": "升级", "war": "战争"}
    danger_labels = {"safe": "安全", "normal": "一般", "dangerous": "危险", "high": "高危", "extreme": "极危"}
    for zone in zones:
        info = player.get_region_ecology(zone)
        print(f"\n{Color.BRIGHT_CYAN}【区域局势：{info['name']}】{Color.RESET}")
        print(f"势力动向：{level_labels.get(info.get('level'), '未知')} | 安全度：{info['security']}/100 | 商路：{info['commerce']}/100 | 通行：{info['travel']}/100 | 危险度：{danger_labels.get(info.get('danger'), '未知')}")
        print(f"局势压力：{info['tension']}")
        # Alpha83：将区域指标翻译成玩家可理解的实际影响提示，避免只显示数字。
        security = int(info.get("security", 70))
        commerce = int(info.get("commerce", 70))
        travel = int(info.get("travel", 70))
        hints = []
        if security <= 35:
            hints.append("治安偏差，行路遭遇风险较高")
        elif security >= 75:
            hints.append("治安较好，行路风险相对较低")
        else:
            hints.append("治安一般，仍需留意沿途风险")
        if commerce <= 35:
            hints.append("商路不畅，商队到场间隔可能更长，交易价格更容易偏高")
        elif commerce >= 75:
            hints.append("商路繁荣，商队往来较活跃，货物供应通常更便利")
        else:
            hints.append("商贸往来处于一般水平")
        if travel <= 35:
            hints.append("道路通行较差，沿途遭遇风险上升")
        elif travel >= 75:
            hints.append("道路通行较顺畅")
        else:
            hints.append("道路通行条件一般")
        # Alpha84：把治安等级翻译为敌人活动与官府巡逻状态，提示对应真实规则。
        try:
            from region_activity import security_band
            band = security_band(security)
            hints.append(f"当地恶人活动{band.get('criminal_activity', '不明')}，官府巡逻：{band.get('patrol', '常态')}")
            if security <= 50:
                hints.append("危险场景中可能遇到额外的恶人或更强敌人")
            if security <= 25:
                hints.append("高危敌人出现机会进一步增加")
        except (ImportError, TypeError, ValueError):
            pass
        print("当前影响：" + "；".join(hints) + "。")
        # Alpha87：明确展示外部世界局势对当前区域的持续影响。
        try:
            from region_activity import list_world_crises
            crises = list_world_crises(player, zone)
            for crisis in crises:
                stage_name = str(crisis.get("stage", "发生"))
                if crisis.get("status") == "active":
                    stage = f"（{stage_name}）" if stage_name != "发生" else ""
                    print(f"外部局势：{crisis.get('title', '江湖事件')}{stage}（预计还将持续 {crisis.get('remaining', 0)} 个世界时刻）")
                    action = crisis.get("player_action", {})
                    if isinstance(action, dict) and action.get("label"):
                        print("  可参与：" + str(action["label"]) + "；输入“治安 协助”尝试影响局势。")
                else:
                    print(f"局势余波：{crisis.get('title', '江湖事件')}（{crisis.get('outcome', '逐步平息')}；地区影响预计还将持续 {crisis.get('recovery_remaining', 0)} 个世界时刻）")
                if crisis.get("announcement"):
                    print("  " + str(crisis["announcement"]))
        except (ImportError, TypeError, ValueError):
            pass
        # Alpha85：展示正在进行或最近完成的地区治安事件，方便玩家理解数值变化来源。
        try:
            from region_activity import get_security_incident
            incident = get_security_incident(player, zone)
            status = incident.get("status")
            if status == "active":
                progress = max(0, int(incident.get("progress", 0)))
                required = max(1, int(incident.get("required_patrols", 1)))
                print(f"治安事件：{incident.get('title', '地区治安巡查')}（官府巡查进度 {progress}/{required}）")
                print(str(incident.get("result_text", "当地正在开展治安巡查。")))
            elif status in ("completed", "expired"):
                print(f"最近治安事件：{incident.get('title', '地区治安巡查')}（{'已完成' if status == 'completed' else '未能完成'}）")
                if incident.get("result_text"):
                    print(str(incident["result_text"]))
        except (ImportError, TypeError, ValueError):
            pass
        print("势力影响：" + "、".join((regions.get(zone, {}) or {}).get("faction_exposure", []) or ["无"]))
        events = player.list_world_events(zone=zone)
        if events:
            print("关联事件：")
            for event in events:
                state = player.get_world_event_state(event["id"])
                count = max(0, int(state.get("count", 0) or 0)) if isinstance(state, dict) else 0
                if engine.WORLD_EVENTS.get(event["id"], {}).get("once") and count > 0:
                    status = "已处理"
                elif zone != engine.ROOMS.get(player.location, {}).get("zone", "main"):
                    status = "需前往该区域核查"
                else:
                    status = "可处理" if event["available"] else "条件未满足或冷却中"
                print(f"- {event['title']}：{status}")
        if info.get("last_change"):
            print(f"最近一次局势结算：江湖时刻 {info['last_change']}")
    if show_all:
        print("\n提示：区域数据会随势力冲突和世界事件变化；事件是否可处理仍受当前位置限制。")

def handle_relations(player, args=None):
    if args:
        target = " ".join(args)
        npc_name = target if target in engine.NPCS else actor_display.find_npc(target, list(engine.NPCS))
        if not npc_name:
            print(f"找不到人物【{target}】。")
            return
        npc_data = engine.NPCS.get(npc_name, {})
        type_labels = {
            "trader": "商贾", "master": "武学师傅", "villager": "百姓", "smith": "铁匠",
            "guard": "护卫", "traveler": "游侠", "sect_guard": "门派守卫",
            "sect_reception": "门派接引", "sect_instructor": "门派传功",
            "sect_master": "门派授业", "sect_member": "门派弟子",
        }
        identity = str(npc_data.get("title") or npc_data.get("name") or npc_name)
        type_label = type_labels.get(npc_data.get("type"), "江湖人物")
        print(f"【{actor_display.format_room_label(npc_name, npc_data, include_id=True)}】")
        print(f"身份：{identity}（{type_label}）")
        print(f"势力：{npc_data.get('faction') or '无'}")
        print(f"关系：{player.get_relation_status(npc_name)} ({player.get_relation(npc_name):+d})")
        state = player.get_npc_state(npc_name)
        state_record = player.get_npc_state_record(npc_name)
        state_label = actor_display.NPC_STATE_LABELS.get(state, state)
        state_reason = str(state_record.get("reason") or "").strip()
        if str(state_record.get("source") or "").startswith("faction_conflict:"):
            state_reason = ""
        print(f"状态：{state_label}" + (f"（{state_reason}）" if state_reason else ""))
        sect_stance = player.get_npc_sect_stance(npc_name)
        if sect_stance != "neutral":
            stance_labels = {"preferred": "门派亲善", "friendly": "门派友好", "wary": "门派戒备", "opposed": "门派敌视"}
            print(f"门派立场：{stance_labels.get(sect_stance, sect_stance)}（当前门派：{player.get_sect()}）")
        memory_action = player.get_npc_memory_behavior(npc_name).get("action")
        impression_labels = {
            "welcome": "念你过往善举，态度亲近",
            "cooperate": "记得你的作为，愿意合作",
            "caution": "记得一些不愉快的过往，存有戒备",
            "refuse": "旧账未清，不愿相助",
            "neutral": "暂无特别印象",
        }
        print(f"印象：{impression_labels.get(memory_action, impression_labels['neutral'])}")
        return
    print(f"\n{Color.CYAN}========== 人物关系 =========={Color.RESET}")
    shown = False
    for name, value in player.get_all_relations().items():
        print(f"- {name}：{player.get_relation_status(name)} ({value:+d})")
        shown = True
    if not shown:
        print("目前尚未与任何人物建立明显关系。")
    print(f"{Color.CYAN}------------------------------{Color.RESET}")


def handle_world_events(player, args=None):
    """P2.26：查看并触发当前区域的动态世界事件。"""
    args = args or []
    if not args:
        events = player.list_world_events()
        print(f"\n{Color.BRIGHT_CYAN}========== 当前区域事件 =========={Color.RESET}")
        if not events:
            print("当前区域暂无配置动态事件。")
        for event in events:
            status = f"{Color.GREEN}可触发{Color.RESET}" if event["available"] else f"{Color.YELLOW}条件未满足/冷却中{Color.RESET}"
            print(f"- {event['title']} [{status}]")
            if event.get("description"):
                print(f"  {event['description']}")
        print("输入“事件 触发 事件名称”可处理当前可触发事件；也可直接输入“事件 触发”处理一个可触发事件。")
        return
    sub = str(args[0]).lower()
    event_id = " ".join(args[1:]) if len(args) > 1 else None
    if sub in ("trigger", "触发", "resolve", "处理"):
        if event_id:
            event_id = next((key for key, value in engine.WORLD_EVENTS.items()
                             if key == event_id or value.get("title") == event_id), event_id)
        ok, message, info = player.trigger_world_event(event_id)
        print(f"\n{Color.BRIGHT_YELLOW}【世界事件】{Color.RESET}{message}")
        if ok and info:
            rewards = info.get("rewards", {}) or {}
            if rewards.get("gold"):
                print(f"获得银两：{rewards['gold']} 两")
            if rewards.get("item"):
                print(f"获得物品：【{rewards['item']}】")
            if rewards.get("sect_reputation"):
                print("门派声望变化：" + "；".join(f"{k} {v:+d}" for k,v in rewards["sect_reputation"].items()))
            if rewards.get("relations"):
                print("人物关系变化：" + "；".join(f"{k} {v:+d}" for k,v in rewards["relations"].items()))
        return
    print("用法：事件；或输入“事件 触发 事件名称”。")

def handle_explore(player):
    room = engine.ROOMS.get(player.location, {})
    zone = room.get("zone", "main")
    regions = getattr(engine, "WORLD_REGIONS", {})
    region = regions.get(zone, {})
    if room.get("safe", False) and not room.get("exploration_events") and not region.get("exploration_events"):
        print("这里过于安稳，没有值得深入搜索的特殊探索点。")
        return
    key = f"explore:{player.location}"
    count = player.get_var(key, 0)
    events = room.get("exploration_events") or region.get("exploration_events") or ["发现一些脚印", "找到少量资源", "没有特别发现"]
    events = player.get_region_exploration_event(zone, events)
    eligible = []
    for candidate in events:
        if isinstance(candidate, dict) and candidate.get("requires"):
            if not engine.check_conditions(candidate.get("requires"), player.world_state, player.completed_quests, player):
                continue
        eligible.append(candidate)
    if not eligible:
        eligible = ["你仔细搜索了一番，但当前没有发现符合条件的特殊线索。"]
    event = eligible[count % len(eligible)]
    player.set_var(key, count + 1)
    player.increment_var(f"exploration:{zone}", 1)
    print(f"\n{Color.BRIGHT_CYAN}【探索】{Color.RESET} {room.get('name', player.location)}")
    if isinstance(event, dict):
        text = event.get("text", "")
        print(text)
        effects = event.get("effects") or {}
        engine.apply_world_effects(player.world_state, effects)
        reward = event.get("item")
        if reward and reward in engine.ITEMS:
            add_inventory_items(player, reward, 1, action="获得")
        if event.get("gold"):
            player.gold += int(event["gold"]); print(f"发现银两：{event['gold']} 两")
    else:
        print("你仔细搜索了一番，没有发现值得记录的线索。")
    print(f"区域探索进度：{player.get_var(f'exploration:{zone}', 0)}")

def handle_quest(player, cmd, args):
    player.mark_visited(player.location)
    # Alpha226：底层仍兼容旧任务接取 API；游戏主循环会拦截独立接取指令，
    # 正常玩家流程由对应 NPC 的交谈选项调用接取处理器。交付/放弃/分支仍可使用指令。
    if cmd == "quests" and args:
        sub = str(args[0]).lower()
        sub_map = {
            "接取": "jiequ", "接受": "jiequ", "接任务": "jiequ", "接取任务": "jiequ", "接受任务": "jiequ",
            "交付": "jiaofu", "交任务": "jiaofu", "完成": "jiaofu",
            "放弃": "fangqi", "放弃任务": "fangqi",
            "选择": "xuanze", "分支": "xuanze", "选择分支": "xuanze",
        }
        if sub in sub_map:
            cmd = sub_map[sub]
            args = [" ".join(args[1:])] if cmd != "xuanze" else [" ".join(args[1:])]

    if cmd == "quests":
        if args:
            raw_name = " ".join(str(part) for part in args).strip()
            q_name = raw_name if raw_name in engine.QUESTS else None
            if q_name is None:
                match_state, matches = _resolve_npc_quest_name(raw_name, list(engine.QUESTS))
                if match_state == "matched":
                    q_name = matches[0]
                elif match_state == "ambiguous":
                    print("任务简称对应多项委托，请使用完整名称查看：" + "、".join(_quest_title(q) for q in matches))
                    return False
                else:
                    suggestions = "、".join(_quest_title(q) for q in matches)
                    print(f"不存在名为【{raw_name}】的任务。" + (f"你可能想查看：{suggestions}。" if suggestions else ""))
                    return False
            q_info = engine.QUESTS[q_name]
            public_title = _quest_title(q_name)
            print(f"\n{Color.CYAN}========== 任务详情：{public_title} =========={Color.RESET}")
            print(f"{public_title}")
            if q_info.get("difficulty"):
                print(f"难度：{q_info.get('difficulty')}")
            print(f"{q_info.get('desc', '暂无描述。')}")
            stages = q_info.get('stages') or []
            if q_name in player.active_quests:
                state = player.quest_states.get(q_name, {"stage": 0, "progress": player.active_quests[q_name]})
                idx = min(state.get('stage', 0), max(0, len(stages)-1)) if stages else 0
                goal_complete = player.is_quest_goal_complete(q_name)
                print(f"当前状态：{'待交付' if goal_complete else '进行中'}")
                if stages:
                    stage = stages[idx]
                    print(f"当前阶段：{idx+1}/{len(stages)} — {stage.get('desc', '')}")
                    target_type_labels = {"talk": "交谈", "kill": "击败", "collect": "收集", "search": "探索", "visit": "前往", "deliver": "交付", "interact": "互动"}
                    target_type = target_type_labels.get(stage.get('target_type', 'talk'), '完成目标')
                    print(f"阶段目标：{target_type} / {stage.get('target_name', '')} ({state.get('progress', 0)}/{stage.get('required_cnt', 1)})")
                else:
                    print(f"进度：{player.active_quests[q_name]}/{q_info.get('required_cnt', 1)}")
                if goal_complete:
                    print("目标已经完成，但奖励尚未结算；必须回到委托人处主动交付。")
                    print(_quest_delivery_guidance(player, q_name))
            elif q_name in player.completed_quests or (not q_info.get("repeatable", False) and player.get_flag(f"quest_completed:{q_name}", False)):
                print("当前状态：已交付")
            elif player.get_flag(f"quest_failed:{q_name}"):
                retryable = q_info.get("retryable", True)
                print(f"当前状态：已失败{'（可重试）' if retryable else '（不可重试）'}")
            else:
                # 与 NPC 对话共用同一判定：未开放时列出具体前置，而不是只说“条件未满足”。
                offer_state, offer_detail = _quest_npc_status(player, q_name)
                print(f"当前状态：{'可接取' if offer_state == '未领取' else '条件未满足'}")
                if offer_state == "未开放":
                    print(offer_detail)
            if q_name in player.active_quests and player.quest_states.get(q_name, {}).get("branch_pending"):
                options = player.get_quest_branch_options(q_name)
                print(f"  {Color.BRIGHT_CYAN}待选择路线：{' / '.join(f"{i + 1}. {c.get('title', '分支选项')}" for i, c in enumerate(options)) or '无'}；输入“选择 {_quest_title(q_name)}|序号”继续。{Color.RESET}")
            if q_info.get("time_limit") is not None and q_name in player.active_quests:
                state = player.quest_states.get(q_name, {})
                elapsed = player.get_quest_clock() - int(state.get("accepted_at", player.get_quest_clock()))
                print(f"剩余行动：{max(0, int(q_info.get('time_limit', 0)) - elapsed)}")
            choices = q_info.get("choices") or []
            if choices:
                print("可选结局：" + " / ".join(str(c.get("title", "结局选项")) for c in choices if isinstance(c, dict)))
            reward = q_info.get('reward', {})
            if reward:
                sect_rep = reward.get("sect_reputation", {}) or {}
                sect_text = " / 门派声望 " + "、".join(f"{k}{int(v):+d}" for k, v in sect_rep.items()) if sect_rep else ""
                from rewards import normalize_reward_items
                item_entries = normalize_reward_items(reward)
                item_text = "、".join(
                    f"{name}×{quantity}" if quantity > 1 else name for name, quantity in item_entries
                ) or "无"
                print(f"奖励：经验 {reward.get('exp', 0)} / 银两 {reward.get('gold', 0)} / 物品 {item_text}{sect_text}")
            print(f"{Color.CYAN}----------------------------------{Color.RESET}")
            return True

        print(f"\n{Color.CYAN}========== 当前任务列表 =========={Color.RESET}")
        if not player.active_quests:
            print("目前没有正在进行中的任务。")
        for q_name, progress in player.active_quests.items():
            q_info = engine.QUESTS.get(q_name, {})
            stages = q_info.get("stages")
            goal_complete = player.is_quest_goal_complete(q_name)
            status_suffix = f"  {Color.BRIGHT_GREEN}【待交付】{Color.RESET}" if goal_complete else ""
            if stages:
                state = player.quest_states.get(q_name, {"stage": 0, "progress": progress})
                idx = min(state.get("stage", 0), len(stages)-1)
                stage = stages[idx]
                req = stage.get("required_cnt", 1)
                print(f"- {Color.YELLOW}{_quest_title(q_name)}{Color.RESET}{_quest_difficulty_text(q_info)}：阶段 {idx+1}/{len(stages)} ({state.get('progress', 0)}/{req}) - {stage.get('desc', q_info.get('desc', ''))}{status_suffix}")
                if state.get("branch_pending"):
                    options = player.get_quest_branch_options(q_name)
                    print(f"  {Color.BRIGHT_CYAN}待选择路线：{' / '.join(f"{i + 1}. {c.get('title', '分支选项')}" for i, c in enumerate(options)) or '无'}；输入“选择 {_quest_title(q_name)}|序号”继续。{Color.RESET}")
            else:
                req = q_info.get("required_cnt", 1)
                print(f"- {Color.YELLOW}{_quest_title(q_name)}{Color.RESET}{_quest_difficulty_text(q_info)}：({progress}/{req}) - {q_info.get('desc', '')}{status_suffix}")
        if any(player.is_quest_goal_complete(q_name) for q_name in player.active_quests):
            print(f"{Color.CYAN}【待交付】表示目标已完成但奖励未结算，需回到委托人处主动交付。{Color.RESET}")
        print(f"{Color.CYAN}----------------------------------{Color.RESET}")

    elif cmd == "xuanze":
        if not args:
            print("请输入：选择 任务名称|序号。")
            return False
        raw = " ".join(str(part) for part in args).strip()
        if "|" in raw:
            parts = [part.strip() for part in raw.split("|", 1)]
        else:
            parts = []
            known_names = []
            for candidate in player.active_quests:
                known_names.extend(engine.quest_aliases(candidate))
            for candidate in sorted(set(known_names), key=len, reverse=True):
                if raw.startswith(candidate + " "):
                    parts = [candidate, raw[len(candidate):].strip()]
                    break
        if len(parts) != 2 or not parts[0] or not parts[1]:
            print("格式错误，请输入：任务 选择 任务名称 分支名称。旧格式“任务 选择 任务名称|分支名称”仍兼容。")
            return False
        match_state, matches = _resolve_npc_quest_name(parts[0], list(player.active_quests))
        if match_state == "matched":
            q_name = matches[0]
        elif match_state == "ambiguous":
            print("任务简称对应多项委托，请使用完整名称选择：" + "、".join(_quest_title(q) for q in matches))
            return False
        else:
            titles = "、".join(_quest_title(q) for q in player.active_quests)
            print(f"没有找到进行中的任务【{parts[0]}】。当前任务：{titles or '暂无'}。")
            return False
        ok, msg = player.choose_quest_branch(q_name, parts[1])
        print(f"{Color.BRIGHT_GREEN if ok else Color.RED}{msg}{Color.RESET}")
        return ok

    elif cmd == "jiequ":
        if not args:
            print("请输入要接取的任务名称。")
            return False
        raw_name = " ".join(str(part) for part in args).strip()
        q_name = raw_name if raw_name in engine.QUESTS else None
        if q_name is None:
            match_state, matches = _resolve_npc_quest_name(raw_name, list(engine.QUESTS))
            if match_state == "matched":
                q_name = matches[0]
            elif match_state == "ambiguous":
                print("任务简称对应多项委托，请使用完整名称接取：" + "、".join(_quest_title(q) for q in matches))
                return False
            else:
                suggestions = "、".join(_quest_title(q) for q in matches)
                print(f"不存在名为【{raw_name}】的任务。" + (f"你可能想接取：{suggestions}。" if suggestions else ""))
                return False
        if q_name in player.active_quests:
            print("你已经接取了该任务！")
            return False
        q_info = engine.QUESTS[q_name]
        already_completed = q_name in player.completed_quests or player.get_flag(f"quest_completed:{q_name}", False)
        if already_completed and not q_info.get("repeatable", False):
            print("该任务你已经完成过了！")
            return False
        if already_completed and q_info.get("repeatable", False):
            cooldown = max(0, int(q_info.get("repeat_cooldown_ticks", 0) or 0))
            if cooldown:
                last_completed = player.get_var(f"quest_repeat_last_completed:{q_name}", None)
                if last_completed is not None:
                    try:
                        remaining = cooldown - (player.get_quest_clock() - int(last_completed))
                    except (TypeError, ValueError):
                        remaining = 0
                    if remaining > 0:
                        print(f"该历练刚刚完成过，请再等待 {remaining} 个世界时刻后重新接取。")
                        return False
        if player.get_flag(f"quest_failed:{q_name}") and not q_info.get("retryable", True):
            print("该任务已经失败，且当前任务不允许重试。")
            return False
        if not engine.check_conditions(q_info.get("requires"), player.world_state, player.completed_quests, player):
            failures = engine.explain_condition_failures(q_info.get("requires"), player.world_state, player.completed_quests, player)
            reason = "；".join(failures) if failures else "尚有未满足的剧情条件，当前配置无法进一步说明。"
            print(f"{Color.RED}接取失败：目前不满足接取任务【{_quest_title(q_name)}】的条件。{reason}{Color.RESET}")
            return False
        quest_npc = q_info.get("npc")
        if quest_npc and quest_npc not in player.get_npcs_in_room(player.location):
            print(f"请先在当前地点找到任务发布人【{quest_npc}】再接取此任务。")
            return False
        player.active_quests[q_name] = 0
        if q_info.get("stages"):
            first_stage = q_info["stages"][0]
            player.quest_states[q_name] = {"stage": 0, "progress": 0, "accepted_at": player.get_quest_clock()}
        else:
            player.quest_states[q_name] = {"stage": 0, "progress": 0, "accepted_at": player.get_quest_clock()}
        engine.apply_world_effects(player.world_state, q_info.get("on_accept"))
        player.set_flag(f"quest_active:{q_name}", True)
        public_title = _quest_title(q_name)
        print(f"{Color.BRIGHT_GREEN}已接取任务【{public_title}】，已加入你的任务列表。输入“任务”可查看目标与进度。{Color.RESET}")
        return True

    elif cmd in ("fangqi", "abandon"):
        if not args:
            print("请输入要放弃的任务名称。")
            return False
        raw_name = " ".join(str(part) for part in args).strip()
        q_name = raw_name if raw_name in player.active_quests else None
        if q_name is None:
            match_state, matches = _resolve_npc_quest_name(raw_name, list(player.active_quests))
            if match_state == "matched":
                q_name = matches[0]
            elif match_state == "ambiguous":
                print("任务简称对应多项委托，请使用完整名称放弃：" + "、".join(_quest_title(q) for q in matches))
                return False
            else:
                titles = "、".join(_quest_title(q) for q in player.active_quests)
                print("你未接取该任务！" + (f"当前任务：{titles}。" if titles else ""))
                return False
        ok, msg = player.abandon_quest(q_name)
        print(f"{Color.YELLOW if ok else Color.RED}{msg}{Color.RESET}")
        return ok

    elif cmd == "jiaofu":
        if not args:
            print("请输入要交付的任务名称；若需选择结局，可在任务名后加“|序号”。")
            return False
        raw_name = " ".join(str(part) for part in args).strip()
        parts = [part.strip() for part in raw_name.split("|", 1)]
        q_name = parts[0]
        selected_choice = parts[1] if len(parts) > 1 else None
        if q_name not in player.active_quests:
            match_state, matches = _resolve_npc_quest_name(q_name, list(player.active_quests))
            if match_state == "matched":
                q_name = matches[0]
            elif match_state == "ambiguous":
                print("任务简称对应多项委托，请使用完整名称交付：" + "、".join(_quest_title(q) for q in matches))
                return False
            else:
                titles = "、".join(_quest_title(q) for q in player.active_quests)
                print("你未接取该任务！" + (f"当前可交付任务：{titles}。" if titles else ""))
                return False
        q_info = engine.QUESTS.get(q_name, {})
        # 防止旧档/异常运行态同时保留 active 与完成旗标时重复结算一次性奖励。
        # 可重复任务仍按 repeat_reward 与冷却规则处理。
        if not q_info.get("repeatable", False) and (
            q_name in player.completed_quests or player.get_flag(f"quest_completed:{q_name}", False)
        ):
            player.active_quests.pop(q_name, None)
            player.quest_states.pop(q_name, None)
            player.set_flag(f"quest_active:{q_name}", False)
            print("该任务已经完成，不能重复交付或领取奖励。")
            return False
        if q_info.get("stages"):
            state = player.quest_states.get(q_name, {"stage": 0, "progress": player.active_quests[q_name]})
            all_done = state.get("stage", 0) >= len(q_info["stages"])-1 and state.get("progress", 0) >= q_info["stages"][-1].get("required_cnt", 1)
            if not all_done:
                print(f"{Color.RED}任务目标未全部达成，无法交付！{Color.RESET}")
                return False
        else:
            req = q_info.get("required_cnt", 1)
            if player.active_quests[q_name] < req:
                print(f"{Color.RED}任务目标未达成，无法交付！{Color.RESET}")
                return False
        # 未单独配置交付人时，默认回到原发布 NPC，避免任务完成后在任意地点结算。
        turn_in_npc = q_info.get("turn_in_npc") or q_info.get("npc")
        if turn_in_npc and turn_in_npc not in player.get_npcs_in_room(player.location):
            print(f"请回到【{turn_in_npc}】处交付任务。")
            return False

        # Alpha227：采集类委托不仅检查进度计数，还必须核实对应物品仍在背包中。
        # 此处只校验，不提前消耗；若玩家还需选择任务结局，不能因显示选项而丢失物品。
        delivered_items = []
        objective_type = q_info.get("target_type")
        item_name = ""
        required_items = 0
        if objective_type == "collect":
            item_name = str(q_info.get("target_name", "")).strip()
            try:
                required_items = max(1, int(q_info.get("required_cnt", 1)))
            except (TypeError, ValueError, OverflowError):
                required_items = 1
            inventory = getattr(player, "inventory", None)
            held_count = inventory.count(item_name) if item_name and isinstance(inventory, list) else 0
            if not item_name or held_count < required_items:
                print(f"{Color.RED}交付失败：需要 {item_name or '任务所需物品'} ×{required_items}，当前 {held_count}。请补齐后再来交付。{Color.RESET}")
                return False

        # 可重复任务允许再次领取基础报酬，但复做奖励由数据单独定义，避免
        # 门派声望、侠义值等永久成长奖励被无限重复刷取。缺少 repeat_reward 时
        # 也不回退到首做奖励，宁可本轮不发奖也不让永久成长可被刷取。
        repeat_completion = q_name in player.completed_quests and bool(q_info.get("repeatable", False))
        reward = (q_info.get("repeat_reward") or {}) if repeat_completion else q_info.get("reward", {})
        choices = q_info.get("choices") or []
        if choices:
            eligible = [c for c in choices if isinstance(c, dict) and engine.check_conditions(c.get("requires"), player.world_state, player.completed_quests, player)]
            if selected_choice:
                chosen = next((c for c in eligible if str(c.get("id")) == selected_choice or str(c.get("title", "")).strip() == selected_choice), None)
                if chosen is None and selected_choice.isdigit():
                    choice_index = int(selected_choice) - 1
                    if 0 <= choice_index < len(eligible):
                        chosen = eligible[choice_index]
                if not chosen:
                    candidate = next((c for c in choices if isinstance(c, dict) and (str(c.get("id")) == selected_choice or str(c.get("title", "")).strip() == selected_choice)), None)
                    if candidate is None:
                        print(f"{Color.RED}没有找到对应结局。当前可选：{', '.join(f"{i + 1}. {c.get('title', '结局选项')}" for i, c in enumerate(eligible)) or '暂无可选结局'}{Color.RESET}")
                    else:
                        reasons = engine.explain_condition_failures(candidate.get("requires"), player.world_state, player.completed_quests, player)
                        detail = "相关剧情条件尚未满足" if reasons else "结局条件不满足或配置无效"
                        print(f"{Color.RED}结局【{candidate.get('title', '该结局')}】暂不可选：{detail}。当前可选：{', '.join(f"{i + 1}. {c.get('title', '结局选项')}" for i, c in enumerate(eligible)) or '暂无可选结局'}{Color.RESET}")
                    return False
            elif len(eligible) == 1:
                chosen = eligible[0]
            else:
                labels = ' / '.join(f"{i + 1}. {c.get('title', '结局选项')}" for i, c in enumerate(eligible)) or '暂无可选结局'
                print(f"{Color.BRIGHT_YELLOW}请选择任务结局：{labels}；输入“交付 {_quest_title(q_name)}|序号”确认。{Color.RESET}")
                for candidate in choices:
                    if not isinstance(candidate, dict) or candidate in eligible:
                        continue
                    reasons = engine.explain_condition_failures(candidate.get("requires"), player.world_state, player.completed_quests, player)
                    if reasons:
                        print(f"  - 【{candidate.get('title', '结局选项')}】未解锁：{'；'.join(reasons)}")
                return False
            reward = chosen.get("reward", reward)
        from rewards import apply_reward_bundle
        # 确认结局后再正式收取交付物。先移除物品可释放背包格供奖励使用；
        # 奖励结算失败时，下方会将交付物原样退回。
        original_inventory = None
        if objective_type == "collect":
            original_inventory = list(player.inventory) if isinstance(player.inventory, list) else None
            removed, remaining = remove_inventory_items(
                player, item_name, required_items, action="交付物品"
            )
            if not removed:
                print(f"{Color.RED}交付失败：需要 {item_name} ×{required_items}，当前 {remaining}。{Color.RESET}")
                return False
            delivered_items = [item_name] * required_items
        result = apply_reward_bundle(player, reward, source="任务奖励")
        if not result["ok"]:
            # 奖励失败时按原顺序回滚交付物，任务状态与玩家物品均保持可重试。
            if delivered_items:
                if original_inventory is not None:
                    player.inventory[:] = original_inventory
                else:
                    add_inventory_items(player, item_name, len(delivered_items), action="退还", announce=False)
                print(f"{Color.YELLOW}{format_item_change(item_name, len(delivered_items), player.inventory.count(item_name), action='退还')}{Color.RESET}")
            print(f"{Color.RED}任务奖励暂时无法结算，交付物已退还，任务状态保持不变，请稍后重试。{Color.RESET}")
            return False

        # 奖励成功后才正式完成任务，避免奖励异常导致“任务完成但奖励丢失”。
        del player.active_quests[q_name]
        player.quest_states.pop(q_name, None)
        if q_name not in player.completed_quests:
            player.completed_quests.append(q_name)
        if q_info.get("repeatable", False):
            player.set_var(f"quest_repeat_last_completed:{q_name}", player.get_quest_clock())
        player.set_flag(f"quest_active:{q_name}", False)
        player.set_flag(f"quest_completed:{q_name}", True)
        world_report = {}
        engine.apply_world_effects(player.world_state, q_info.get("on_complete"), report=world_report)
        if choices and chosen.get("effects"):
            engine.apply_world_effects(player.world_state, chosen.get("effects"), report=world_report)
        player.react_npcs_to_quest(q_name, "complete")
        public_title = _quest_title(q_name)
        print(f"\n{Color.BRIGHT_YELLOW}🎉 恭喜完成任务【{public_title}】！已向委托人交代清楚，奖励已结算。{Color.RESET}")
        _print_region_effect_changes(world_report.get("region_effects"))
        follow_up = q_info.get("follow_up_hint")
        if follow_up:
            print(f"后续指引：{follow_up}")
        else:
            print("后续指引：可继续探索周边、查看公告栏，或与人物交谈了解新的消息。")
        request_autosave(player)
        return True


def apply_consumable(player, item_name, battle_context=None):
    info = engine.ITEMS.get(item_name, {})
    inventory = getattr(player, "inventory", None)
    held = inventory.count(item_name) if isinstance(inventory, list) else 0
    if info.get("type") == "manual":
        if held < 1:
            print(f"行囊里已经没有【{item_name}】，无法研习。")
            return False
        skill_name = info.get("teaches_skill")
        if not skill_name or not callable(getattr(player, "learn_skill_from_manual", None)):
            print(f"【{item_name}】的研习方式暂不可用，物品没有消耗。")
            return False
        ok, message = player.learn_skill_from_manual(skill_name)
        if not ok:
            print(message)
            return False
        removed, remaining = remove_inventory_items(
            player, item_name, 1, action="消耗", announce=False
        )
        if not removed:
            print(f"研习失败：需要 {item_name} ×1，当前 {remaining}。")
            return False
        from economy.flow import record_player_consumption
        record_player_consumption(player, item_name, 1, source="研习武学秘籍")
        print(message)
        print(f"{Color.GREEN}{format_item_change(item_name, 1, remaining, action='消耗')}{Color.RESET}")
        return True
    if info.get("type") != "consumable":
        print(f"【{item_name}】并非可直接使用的消耗道具。")
        return False
    if held < 1:
        print(f"行囊里已经没有【{item_name}】，无法使用。")
        return False

    eff = info.get("effect", {})
    needs_target = bool(eff.get("target_damage") or eff.get("target_status"))
    if needs_target and not isinstance(battle_context, dict):
        print(f"【{item_name}】需要在战斗中对敌人使用；物品没有消耗。")
        return False
    if needs_target and (battle_context.get("enemy_hp", 0) <= 0 or not isinstance(battle_context.get("enemy_statuses"), dict)):
        print(f"【{item_name}】当前没有有效的攻击目标；物品没有消耗。")
        return False

    removed, remaining = remove_inventory_items(
        player, item_name, 1, action="消耗", announce=False
    )
    if not removed:
        print(f"使用失败：需要 {item_name} ×1，当前 {remaining}。")
        return False
    # Alpha110：只有在物品已实际移除后，才把消耗记入经济流水。
    from economy.flow import record_player_consumption
    record_player_consumption(player, item_name, 1, source="使用消耗品")
    from engine import STATUS_EFFECTS
    effect_parts = []
    if "hp" in eff:
        actual_gain = min(player.max_hp, player.hp + eff["hp"]) - player.hp
        player.hp += actual_gain
        effect_parts.append(f"恢复 {actual_gain} 点气血")
    if "mp" in eff:
        actual_gain = min(player.max_mp, player.mp + eff["mp"]) - player.mp
        player.mp += actual_gain
        effect_parts.append(f"恢复 {actual_gain} 点内力")
    if "status" in eff:
        st = eff["status"]
        st_name = st.get("name")
        if st_name:
            cn_name = STATUS_EFFECTS.get(st_name, {}).get("name", st_name)
            engine.add_status(engine.p_statuses_global, st_name, st.get("turns", 1), st.get("value", 0))
            effect_parts.append(f"获得【{cn_name}】效果")
    if effect_parts:
        color = Color.GREEN if "hp" in eff else (Color.BLUE if "mp" in eff else Color.CYAN)
        print(f"{color}你服下了【{item_name}】，{'，'.join(effect_parts)}。已消耗 1 件，剩余：{item_name} ×{remaining}。{Color.RESET}")
    if needs_target:
        damage = max(0, int(eff.get("target_damage", 0) or 0))
        if damage:
            actual = min(damage, int(battle_context["enemy_hp"]))
            battle_context["enemy_hp"] = max(0, int(battle_context["enemy_hp"]) - actual)
            target_name = battle_context.get("enemy_name", "敌人")
            print(f"{Color.BRIGHT_RED}你掷出【{item_name}】，命中{target_name}，造成 {actual} 点伤害！{Color.RESET}")
        st = eff.get("target_status")
        if isinstance(st, dict) and st.get("name"):
            st_name = st["name"]
            cn_name = STATUS_EFFECTS.get(st_name, {}).get("name", st_name)
            engine.add_status(battle_context["enemy_statuses"], st_name, int(st.get("turns", 1)), int(st.get("value", 0)))
            print(f"{Color.YELLOW}{battle_context.get('enemy_name', '敌人')}受到【{cn_name}】效果！{Color.RESET}")
        if not effect_parts:
            print(f"{Color.YELLOW}已消耗 1 件，剩余：{item_name} ×{remaining}。{Color.RESET}")
    return True


def _parse_trade_quantity(args):
    """解析 buy/sell 的数量；默认 1，支持 buy 物品 数量。"""
    if len(args) <= 1:
        return 1
    try:
        quantity = int(args[1])
    except (TypeError, ValueError):
        return None
    return quantity if quantity > 0 else None


def _merchant_rates(npc_data):
    """返回玩家买入/卖出倍率；旧 NPC 未配置时保持 P2.9 的 1.0/0.5。"""
    try:
        buy_rate = float(npc_data.get("buy_rate", 1.0))
        sell_rate = float(npc_data.get("sell_rate", 0.5))
    except (TypeError, ValueError):
        buy_rate, sell_rate = 1.0, 0.5
    buy_rate = max(0.0, buy_rate)
    sell_rate = max(0.0, min(1.0, sell_rate))
    return buy_rate, sell_rate


def _trade_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _config_trade_price(config, item, default):
    """读取商队配置价；缺失或损坏时回退默认报价。"""
    if isinstance(config, dict) and item in config:
        return max(1, _trade_int(config.get(item), default))
    return max(1, _trade_int(default, 1))


def _resolve_trade_item(item_input, candidates):
    """优先精确匹配，其次唯一包含匹配；多个候选返回歧义列表。"""
    item_input = str(item_input or "").strip()
    if not item_input:
        return None, []
    if item_input in candidates:
        return item_input, []
    matches = [name for name in candidates if item_input in name or name in item_input]
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _merchant_stock(player, npc_name, item):
    """返回模拟型商人的真实库存件数；不属于模拟货品的物品返回 None。"""
    from economy import TradeService
    if not TradeService.sells_from_real_stock(npc_name, item):
        return None
    state = getattr(player, "economy_state", None)
    stocks = state.get("npc_inventory", {}) if isinstance(state, dict) else {}
    stock = stocks.get(str(npc_name)) if isinstance(stocks, dict) else None
    if not isinstance(stock, dict):
        return 0
    return max(0, _trade_int(stock.get(str(item), 0)))


def _market_event_rate(player):
    """读取当前经济行情倍率；旧存档缺少事件状态时使用常态倍率。"""
    state = getattr(player, "economy_state", {})
    events = state.get("events", {}) if isinstance(state, dict) else {}
    if not isinstance(events, dict):
        return 1.0
    try:
        return max(0.5, min(2.0, float(events.get("market_event_rate", 1.0))))
    except (TypeError, ValueError, OverflowError):
        return 1.0


def _market_quote(player, item_name, base_price, side, merchant_rate=1.0):
    """统一计算普通店铺货架显示价与实际成交价，确保行情事件两处一致。"""
    from economy import TradeService
    return TradeService.market_price(
        player, item_name, base_price, side, merchant_rate, _market_event_rate(player)
    )


def _handle_caravan_trading(player, cmd, args, caravan_id, caravan_config):
    """商队到场时优先提供真实库存交易；交易直接写入经济存档状态。"""
    from economy import TradeService
    caravan_config = caravan_config if isinstance(caravan_config, dict) else {}
    economy_state = getattr(player, "economy_state", {})
    caravan = economy_state.get("caravans", {}).get(caravan_id, {}) if isinstance(economy_state, dict) else {}
    caravan = caravan if isinstance(caravan, dict) else {}
    inventory = caravan.get("inventory", {}) if isinstance(caravan, dict) else {}
    if not isinstance(inventory, dict):
        print("商队货物清点暂时出了问题，请稍后再试。")
        return False
    events = economy_state.get("events", {}) if isinstance(economy_state, dict) else {}
    event_rate = events.get("market_event_rate", 1.0) if isinstance(events, dict) else 1.0
    region_rate = caravan_config.get("region_rate", 1.0)
    sale_prices = caravan_config.get("sale_prices", {})
    buy_prices = caravan_config.get("buy_prices", {})

    def goods_on_sale():
        return [(str(item), _trade_int(amount)) for item, amount in inventory.items() if _trade_int(amount) > 0]

    if cmd in ("shop", "list"):
        print(f"\n========== {caravan_id}的行商货单 ==========")
        available = goods_on_sale()
        if not available:
            print("商队暂时没有可出售的货物。")
        for item, amount in available:
            info = engine.ITEMS.get(item, {})
            base_price = max(1, _trade_int(info.get("price", 10), 10))
            configured_price = _config_trade_price(sale_prices, item, round(base_price * 1.2))
            price = TradeService.market_price(player, item, configured_price, "buy", region_rate, event_rate)
            print(f"  【{item}】×{amount}，每件售价 {price} 两")
        if isinstance(buy_prices, dict) and buy_prices:
            print("商队收购报价：")
            for item, base_offer in buy_prices.items():
                offer_base = _config_trade_price(buy_prices, item, 1)
                offer = TradeService.market_price(player, str(item), offer_base, "sell", region_rate, event_rate)
                print(f"  【{item}】每件收购 {offer} 两")
            print("  货单以外的行货，商队按行情六成折价收购。")
        cargo_used = sum(max(0, _trade_int(v)) for v in inventory.values())
        capacity = max(0, _trade_int(caravan.get("capacity", caravan_config.get("capacity", 8)), 8))
        print(f"商队现银：{max(0, _trade_int(caravan.get('gold', 0)))} 两；货舱容量：{cargo_used}/{capacity}")
        print("可用指令：买 物品名称 数量；卖 物品名称 数量。可在末尾追加‘给 商队名称’指定对象。")
        return True
    if cmd not in ("buy", "sell"):
        return False
    if not args:
        print(f"请指定要{'购买' if cmd == 'buy' else '出售'}的物品名称和数量。")
        return False
    quantity = _parse_trade_quantity(args)
    if quantity is None:
        print("交易数量必须是正整数。")
        return False
    item_input = str(args[0])
    if cmd == "buy":
        candidates = [item for item, _ in goods_on_sale()]
        item, ambiguous = _resolve_trade_item(item_input, candidates)
        if item is None:
            if not ambiguous:
                print(f"商队没有可出售的【{item_input}】。")
                return False
            print(f"商队的货单里有几样与【{item_input}】相近：")
            for idx, name in enumerate(ambiguous, 1):
                print(f"  {idx}. {name}（余 {_trade_int(inventory.get(name, 0))} 件）")
            print(f"请改用完整货物名称，例如：买 {ambiguous[0]} {quantity}")
            return False
        info = engine.ITEMS.get(item, {})
        base_price = max(1, _trade_int(info.get("price", 10), 10))
        configured_price = _config_trade_price(sale_prices, item, round(base_price * 1.2))
        unit_price = TradeService.market_price(player, item, configured_price, "buy", region_rate, event_rate)
        ok, message = TradeService.buy_from_caravan(player, caravan_id, item, quantity, unit_price)
    else:
        candidates = list(dict.fromkeys(str(item) for item in getattr(player, "inventory", []) or []))
        item, ambiguous = _resolve_trade_item(item_input, candidates)
        if item is None:
            if not ambiguous:
                print(f"你的行囊中没有【{item_input}】。")
                return False
            print(f"你的行囊里有几样与【{item_input}】相近：")
            for idx, name in enumerate(ambiguous, 1):
                print(f"  {idx}. {name}（{player.inventory.count(name)} 件）")
            print(f"请改用完整货物名称，例如：卖 {ambiguous[0]} {quantity}")
            return False
        info = engine.ITEMS.get(item, {})
        base_price = max(1, _trade_int(info.get("price", 10), 10))
        configured_price = _config_trade_price(buy_prices, item, round(base_price * 0.6))
        unit_price = TradeService.market_price(player, item, configured_price, "sell", region_rate, event_rate)
        ok, message = TradeService.sell_to_caravan(player, caravan_id, item, quantity, unit_price)
    if not ok:
        print(message)
        return False
    print(message)
    request_autosave(player)
    return True


def handle_trading(player, cmd, args):
    room = engine.ROOMS.get(player.location, {})
    if room.get("trade_closed") is True:
        closed_text = str(room.get("trade_closed_text", "") or "").strip()
        print(closed_text or f"{room.get('name', '这里')}已经打烊，柜台无人，无法交易。")
        return False
    economy_state = getattr(player, "economy_state", {})
    events = economy_state.get("events", {}) if isinstance(economy_state, dict) else {}
    active = events.get("active_caravans", {}) if isinstance(events, dict) else {}
    args = list(args or [])
    # 支持“卖 草药 6 给 村镇行商”“查看 南路商队”等明确指定交易对象的写法。
    from economy import EconomyManager
    manager = EconomyManager(economy_state if isinstance(economy_state, dict) else {})
    caravan_names = list(manager.caravan_config) if isinstance(manager.caravan_config, dict) else []
    room_npcs = player.get_npcs_in_room(player.location)
    trader_names = [n for n in room_npcs if engine.NPCS.get(n, {}).get("type") == "trader" or "shop" in engine.NPCS.get(n, {})]
    # 交易对象按全游戏商人名册识别：玩家点名某位商人时，不能因为此人不在场就
    # 悄悄改与同场景另一位商人成交。
    all_merchants = [name for name, info in engine.NPCS.items()
                     if isinstance(info, dict) and info.get("shop")]
    explicit_target = None
    joined_args = " ".join(str(a) for a in args)
    for name in sorted(set(caravan_names + all_merchants), key=len, reverse=True):
        if name and name in joined_args:
            explicit_target = name
            args = [str(a) for a in args if str(a) != name and str(a) not in ("给", "向", "对", "找", "跟")]
            break
    active_here = []
    if isinstance(active, dict):
        for active_key, visit in active.items():
            if not isinstance(visit, dict) or visit.get("room") != player.location:
                continue
            try:
                current_tick = int(economy_state.get("tick", 0))
                if int(visit.get("until_tick", -1)) <= current_tick:
                    continue
            except (TypeError, ValueError, OverflowError):
                continue
            caravan_id = str(visit.get("name", str(active_key).split(":", 1)[0]))
            if caravan_id in caravan_names and caravan_id in economy_state.get("caravans", {}):
                if caravan_id not in [row[0] for row in active_here]:
                    active_here.append((caravan_id, manager.caravan_config.get(caravan_id, {})))
    if explicit_target in caravan_names:
        selected = next((row for row in active_here if row[0] == explicit_target), None)
        if selected:
            return _handle_caravan_trading(player, cmd, args, selected[0], selected[1])
        print(f"{explicit_target}此刻不在这里，请先查看场景或商旅消息确认到场。")
        return False
    if len(active_here) > 1 and not explicit_target:
        print("这里有多支商队，请指定交易对象：")
        for caravan_id, _ in active_here:
            print(f"  查看 {caravan_id}；买 物品 数量 给 {caravan_id}；卖 物品 数量 给 {caravan_id}")
        return False
    if len(active_here) == 1 and not explicit_target:
        return _handle_caravan_trading(player, cmd, args, active_here[0][0], active_here[0][1])

    # 玩家点名了其他场景的商人：明确拒绝，不能把交易转给同场景旁人。
    if explicit_target and explicit_target in all_merchants and explicit_target not in trader_names:
        print(f"{explicit_target}此刻不在此处，无法与其交易；请先确认所在场景。")
        return False

    npcs_in_room = room_npcs
    trader_npc = None
    if explicit_target in trader_names:
        trader_npc = explicit_target
    else:
        candidates = [n for n in trader_names if player.get_npc_state(n) != "away"]
        if len(candidates) > 1 and cmd in ("shop", "list", "buy", "sell"):
            print("这里有多位商人，请先指定对象，例如：查看 药铺老板，或：卖 草药 2 给 药铺老板。")
            print("当前可交易对象：" + "、".join(candidates))
            return False
        trader_npc = candidates[0] if candidates else None

    if not trader_npc:
        if explicit_target and explicit_target in all_merchants:
            print(f"{explicit_target}此刻不在此处，无法与其交易；请先确认所在场景。")
            return False
        print("此处没有可以交易的商贾或店家。")
        return False

    npc_data = engine.NPCS[trader_npc]
    npc_state = player.get_npc_state(trader_npc)
    if npc_state == "away":
        print(f"{Color.YELLOW}{trader_npc} 此刻暂时离开了，无法交易。{Color.RESET}")
        return False
    shop_items = npc_data.get("shop", [])
    buy_rate, sell_rate = _merchant_rates(npc_data)

    if cmd in ("shop", "list"):
        from economy import TradeService
        merchant_wallet = TradeService.merchant_wallet(player, trader_npc)
        print(f"\n{Color.YELLOW}======== {trader_npc} 的店铺货架 ========{Color.RESET}")
        for idx, item in enumerate(shop_items, 1):
            info = engine.ITEMS.get(item, {})
            base_price = info.get("price", 0)
            stock = _merchant_stock(player, trader_npc, item)
            if stock is not None and stock <= 0:
                print(f"  {idx}. {item} - 暂无现货 ({info.get('desc', '')})")
                continue
            buy_price = _market_quote(player, item, base_price, "buy", buy_rate) if base_price > 0 else 0
            sell_price = _market_quote(player, item, base_price, "sell", sell_rate) if base_price > 0 else 0
            notes = []
            if stock is not None and stock > 0:
                notes.append(f"余 {stock} 件")
            if isinstance(merchant_wallet, int) and 0 <= merchant_wallet < sell_price:
                notes.append("店家现银不足")
            line = f"  {idx}. {item} - 买入 {buy_price} 两 / 回收 {sell_price} 两"
            if notes:
                line += "，" + "；".join(notes)
            print(f"{line} ({info.get('desc', '')})")
        print(f"手头银两：{player.gold} 两")
        return True

    if cmd not in ("buy", "sell"):
        return False
    if not args:
        print(f"请指定要{'购买' if cmd == 'buy' else '出售'}的物品名称，并可追加数量，例如：{'购买' if cmd == 'buy' else '出售'} 金创药 3。")
        return False

    quantity = _parse_trade_quantity(args)
    if quantity is None:
        print("交易数量必须是正整数，例如：购买 金创药 3。")
        return False

    item_input = args[0]
    if cmd == "buy":
        matching = [i for i in shop_items if item_input in i or i in item_input]
        if not matching:
            print(f"店家表示这里并不出售【{item_input}】。")
            return False
        target = matching[0]
        info = engine.ITEMS.get(target, {})
        if info.get("price", 0) <= 0:
            print(f"【{target}】当前无法交易。")
            return False
        from economy import TradeService
        stock = _merchant_stock(player, trader_npc, target)
        if stock is not None and stock < quantity:
            if stock <= 0:
                print(f"{trader_npc} 的【{target}】暂无现货，请稍后再来。")
            else:
                print(f"{trader_npc} 的【{target}】只剩 {stock} 件，暂时买不了 {quantity} 件。")
            return False
        unit_price = _market_quote(player, target, info.get("price", 0), "buy", buy_rate)
        total_price = unit_price * quantity
        wallet = _trade_int(getattr(player, "gold", -1), -1)
        if wallet < total_price:
            failure = format_action_feedback("交易", False, f"银两不足，需要 {total_price} 两，你目前只有 {wallet} 两。", next_step="减少购买数量，或先出售物品赚取银两。")
            print(f"{Color.RED}{failure[0]}{Color.RESET}")
            print(failure[1])
            return False
        ok, message = TradeService.buy(player, target, quantity, unit_price, trader_npc)
        if not ok:
            print(message)
            return False
        feedback = format_action_feedback(
            "交易", True,
            f"买入【{target}】×{quantity}，单价 {unit_price} 两，共花费 {total_price} 两。",
            f"行囊中现有【{target}】×{player.inventory.count(target)}；剩余银两 {player.gold} 两。",
        )
        print(f"{Color.GREEN}{feedback[0]}{Color.RESET}")
        for line in feedback[1:]:
            print(line)
        request_autosave(player)
        return True

    matching = [i for i in player.inventory if item_input in i or i in item_input]
    if not matching:
        failure = format_action_feedback("交易", False, f"行囊中没有【{item_input}】。", next_step="输入“背包”核对物品名称与数量。")
        for line in failure:
            print(line)
        return False
    target = matching[0]
    owned = player.inventory.count(target)
    if quantity > owned:
        failure = format_action_feedback("交易", False, f"【{target}】只有 {owned} 件，无法出售 {quantity} 件。", next_step="减少出售数量，或先查看背包库存。")
        for line in failure:
            print(line)
        return False
    info = engine.ITEMS.get(target, {})
    base_price = info.get("price", 0)
    if base_price <= 0:
        print(f"【{target}】没有有效交易价格，无法出售。")
        return False
    from economy import TradeService
    unit_price = _market_quote(player, target, base_price, "sell", sell_rate)
    total_price = unit_price * quantity
    ok, message = TradeService.sell(player, target, quantity, unit_price, trader_npc)
    if not ok:
        print(message)
        return False
    feedback = format_action_feedback(
        "交易", True,
        f"卖出【{target}】×{quantity}，单价 {unit_price} 两，共获得 {total_price} 两。",
        f"行囊中剩余【{target}】×{player.inventory.count(target)}；当前银两 {player.gold} 两。",
    )
    print(f"{Color.GREEN}{feedback[0]}{Color.RESET}")
    for line in feedback[1:]:
        print(line)
    request_autosave(player)
    return True


def _find_inventory_item(player, item_input):
    matches = _resolve_inventory_items(player, item_input)
    return matches[0] if matches else None


def _print_equipment_compare(player, item_name):
    result = player.compare_equipment(item_name)
    if not result:
        print(f"{Color.RED}【{item_name}】不是可比较的装备。{Color.RESET}")
        return
    slot_name = "武器" if result["slot"] == "weapon" else "防具"
    current = result["current"]
    current_name = current.get("name") or "无"
    print(f"\n{Color.BRIGHT_CYAN}========== 装备比较 =========={Color.RESET}")
    compare_fields = [
        (f"候选{slot_name}：", f"{Color.GREEN}{item_name}{Color.RESET}"),
        ("品质：", f"{result.get('quality', '普通')} | 词条槽：{result.get('affix_count', 0)}"),
        (f"当前{slot_name}：", f"{Color.YELLOW}{current_name}{Color.RESET}"),
    ]
    if result["slot"] == "weapon":
        compare_fields.append(("攻击：", f"{current.get('atk', 0)} → {result['candidate_atk']}  变化：{result['delta_atk']:+d}"))
    else:
        compare_fields.append(("防御：", f"{current.get('defense', 0)} → {result['candidate_defense']}  变化：{result['delta_defense']:+d}"))
    for compare_line in format_labeled_fields(compare_fields, label_width=12):
        print(wrap_player_text(compare_line, width=BODY_WIDTH))
    affixes = result.get("candidate_affixes", {})
    pieces = []
    for key, label in (("accuracy_bonus", "命中"), ("crit_bonus", "暴击"), ("dodge_bonus", "闪避")):
        value = float(affixes.get(key, 0.0))
        if value:
            pieces.append(f"{label}{value:+.0%}")
    attr_labels = {"strength": "力量", "constitution": "体魄", "internal": "内息", "agility": "身法", "insight": "洞察"}
    for key, value in (affixes.get("attribute_bonus", {}) or {}).items():
        if key in attr_labels and value:
            pieces.append(f"{attr_labels[key]}{int(value):+d}")
    if pieces:
        print(f"词条：{' | '.join(pieces)}")
    build_preview = player.get_build_preview_for_item(item_name)
    if build_preview and build_preview.get("changed"):
        before = (build_preview.get("before") or {}).get("name", "无流派")
        after = (build_preview.get("after") or {}).get("name", "无流派")
        print(f"流派变化：{before} → {after}")
    print(f"装备评分：{result.get('current_score', 0)} → {result.get('candidate_score', 0)} "
          f"({result.get('candidate_score', 0) - result.get('current_score', 0):+d})")
    print(f"售价参考：{result['price']} 两")
    print(f"{Color.BRIGHT_CYAN}=============================={Color.RESET}")


def show_equipment(player):
    print(f"\n{Color.CYAN}========== 当前装备 =========={Color.RESET}")
    equipment_fields = []
    for slot, label in (("weapon", "兵刃："), ("armor", "防具：")):
        info = player.get_equipment_stats(slot)
        name = info.get("name") or "无"
        lv = info.get("enhance", 0)
        quality = info.get("quality", "普通")
        stat_label = "攻击装备加成" if slot == "weapon" else "防御装备加成"
        stat_value = info.get("atk", 0) if slot == "weapon" else info.get("defense", 0)
        equipment_fields.append((label, f"{Color.GREEN}{name}{Color.RESET} [{quality}] (+{lv}) | {stat_label} +{stat_value}"))
        weapon_effect = info.get("weapon_effect", {}) if slot == "weapon" else {}
        if weapon_effect:
            status = engine.STATUS_EFFECTS.get(weapon_effect.get("status"), {})
            chance = max(0.0, min(1.0, float(weapon_effect.get("chance", 0.0))))
            equipment_fields.append(("兵刃特性：", f"命中时 {chance:.0%} 概率触发【{status.get('name', weapon_effect.get('status', '特殊效果'))}】"))
    affixes = player.get_equipment_affixes()
    equipment_fields.extend([
        ("总攻击：", str(player.get_total_atk())),
        ("总防御：", str(player.get_total_defense())),
        ("命中词条：", f"{affixes['accuracy_bonus']:+.0%} | 暴击词条：{affixes['crit_bonus']:+.0%} | 闪避词条：{affixes['dodge_bonus']:+.0%}"),
    ])
    for equipment_line in format_labeled_fields(equipment_fields, label_width=12):
        print(wrap_player_text(equipment_line, width=BODY_WIDTH))
    print(f"{Color.CYAN}=============================={Color.RESET}")


def handle_equipment_and_items(player, cmd, args):
    if cmd == "equipment":
        show_equipment(player)
        return True
    if cmd == "compare":
        if not args:
            print("请指定要比较的装备（如 compare 玄铁重剑）。")
            return False
        item_name = _find_inventory_item(player, args[0])
        if not item_name:
            print(f"你的背包里没有【{args[0]}】。")
            return False
        _print_equipment_compare(player, item_name)
        return True
    if cmd == "unequip":
        if not args:
            print("请指定卸下部位：武器或防具。")
            return False
        slot_input = args[0].lower()
        slot = {"weapon": "weapon", "武器": "weapon", "w": "weapon",
                "armor": "armor", "防具": "armor", "a": "armor"}.get(slot_input)
        if not slot:
            print("部位无效，请输入武器或防具。")
            return False
        ok, msg = player.unequip_item(slot)
        if ok:
            for line in format_action_feedback("卸下装备", True, msg, detail="装备栏已更新，卸下的物品已放回行囊。"):
                print(f"{Color.GREEN}{line}{Color.RESET}")
            request_autosave(player)
        else:
            for line in format_action_feedback("卸下装备", False, msg, next_step="检查当前装备部位后重试。"):
                print(f"{Color.RED}{line}{Color.RESET}")
        return ok
    if not args:
        print(f"请指定物品名称（如 {cmd} 精铁剑）。")
        return False
    item_input = args[0]

    if cmd in ("wield", "wear", "equip"):
        item_name = _find_inventory_item(player, item_input)
        if not item_name:
            print(f"你的背包里没有【{item_input}】。")
            return False
        item_type = engine.ITEMS.get(item_name, {}).get("type")
        if cmd == "wield" and item_type != "weapon":
            print(f"{Color.RED}【{item_name}】不是武器，无法使用“装备武器”。{Color.RESET}")
            return False
        if cmd == "wear" and item_type != "armor":
            print(f"{Color.RED}【{item_name}】不是防具，无法使用“穿戴”。{Color.RESET}")
            return False
        if cmd == "equip" and item_type not in ("weapon", "armor"):
            print(f"{Color.RED}【{item_name}】无法装备。{Color.RESET}")
            return False
        before_atk = player.get_total_atk()
        before_defense = player.get_total_defense()
        ok, msg = player.equip_item(item_name)
        if ok:
            after_atk = player.get_total_atk()
            after_defense = player.get_total_defense()
            detail = (f"总攻击 {before_atk} → {after_atk}（{after_atk - before_atk:+d}）；"
                      f"总防御 {before_defense} → {after_defense}（{after_defense - before_defense:+d}）。")
            for line in format_action_feedback("装备", True, msg, detail=detail):
                print(f"{Color.GREEN}{line}{Color.RESET}")
            request_autosave(player)
        else:
            for line in format_action_feedback("装备", False, msg, next_step="确认物品类型与装备部位后重试。"):
                print(f"{Color.RED}{line}{Color.RESET}")
        return ok

    if cmd == "use":
        if item_input.isdigit():
            stored = getattr(player, "_use_item_candidates", None)
            if stored:
                signature, candidate_names = stored
                names = list(candidate_names)
                index = int(item_input)
                if signature == _inventory_signature(player) and 1 <= index <= len(names):
                    player._use_item_candidates = None
                    return _use_inventory_item(player, names[index - 1])
            print("没有可选择的物品序号。请先输入物品名称，或重新查看背包后再试。")
            return False
        matches = _resolve_inventory_items(player, item_input)
        if not matches:
            print(f"行囊里没有【{_display_item_name(item_input)}】。")
            return False
        if len(matches) > 1:
            _remember_use_candidates(player, matches)
            print("你要使用哪一种物品？")
            for idx, name in enumerate(matches[:10], 1):
                print(f"  {idx}. {_inventory_candidate_label(player, name)}")
            if len(matches) > 10:
                print(f"  ……另有 {len(matches) - 10} 种相近物品，请输入更完整的名称。")
            print("请选择序号（如：使用 1）；如仍不确定，请尽量输入完整物品名称。")
            return False
        player._use_item_candidates = None
        return _use_inventory_item(player, matches[0])
    return False



def show_build(player):
    """显示当前装备与属性形成的激活流派及其战斗加成。"""
    active = player.get_active_build()
    print(f"\n{Color.BRIGHT_CYAN}========== 流派 =========={Color.RESET}")
    if not active:
        print("当前尚未形成明确流派。可通过属性加点与装备组合激活流派。")
    else:
        print(f"当前流派：{Color.GREEN}{active['name']}{Color.RESET}")
        print(f"定位：{active.get('description', '')}")
        bonuses = active.get("bonuses", {})
        parts = []
        if bonuses.get("atk"): parts.append(f"攻击 {int(bonuses['atk']):+d}")
        if bonuses.get("defense"): parts.append(f"防御 {int(bonuses['defense']):+d}")
        if bonuses.get("hit_bonus"): parts.append(f"命中 {float(bonuses['hit_bonus']):+.0%}")
        if bonuses.get("crit_bonus"): parts.append(f"暴击 {float(bonuses['crit_bonus']):+.0%}")
        if bonuses.get("dodge_bonus"): parts.append(f"闪避 {float(bonuses['dodge_bonus']):+.0%}")
        print("流派加成：" + (" | ".join(parts) if parts else "无"))
    print(f"总攻击：{player.get_total_atk()} | 总防御：{player.get_total_defense()}")
    print(f"命中：{player.get_hit_chance()*100:.0f}% | 暴击：{player.get_crit_chance()*100:.0f}% | 闪避：{player.get_dodge_chance()*100:.0f}%")
    print(f"{Color.BRIGHT_CYAN}=============================={Color.RESET}")


def show_attributes(player):
    labels = (("strength", "力量", "每点 +2 攻击"),
              ("constitution", "体魄", "每点 +8 最大气血 / +8 当前气血"),
              ("internal", "内息", "每点 +6 最大内力 / +6 当前内力"),
              ("agility", "身法", "每点 +1% 命中 / +1% 闪避"),
              ("insight", "洞察", "每点 +1% 暴击"))
    print(f"\n{Color.CYAN}========== 角色属性与流派 ==========={Color.RESET}")
    print(f"可用属性点：{Color.YELLOW}{player.attribute_points}{Color.RESET}")
    for key, label, effect in labels:
        print(f"{label}：{Color.GREEN}{player.get_attribute(key)}{Color.RESET}  （{effect}）")
    print(f"总攻击：{player.get_total_atk()} | 总防御：{player.get_total_defense()}")
    print(f"命中：{player.get_hit_chance()*100:.0f}% | 暴击：{player.get_crit_chance()*100:.0f}% | 闪避：{player.get_dodge_chance()*100:.0f}%")
    print(f"{Color.CYAN}=================================={Color.RESET}")


def handle_attributes(player, args):
    if not args:
        show_attributes(player)
        return
    if args[0].lower() in ("help", "?", "帮助"):
        print("用法：属性 查看；加点 力量 1。")
        return
    if args[0].lower() in ("view", "show", "查看", "info"):
        show_attributes(player)
        return
    if args[0].lower() in ("add", "addpoint", "加点", "投入"):
        if len(args) < 2:
            print("请指定属性，例如：加点 力量 1")
            return
        amount = args[2] if len(args) >= 3 else "1"
        ok, msg = player.allocate_attribute(args[1], amount)
        print(f"{Color.GREEN if ok else Color.RED}{msg}{Color.RESET}")
        if ok:
            request_autosave(player)
        return
    # 允许直接输入“属性 力量 2”作为简写。
    amount = args[1] if len(args) >= 2 else "1"
    ok, msg = player.allocate_attribute(args[0], amount)
    print(f"{Color.GREEN if ok else Color.RED}{msg}{Color.RESET}")
    if ok:
        request_autosave(player)

def _print_forge_preview(player):
    print(f"\n{Color.BRIGHT_YELLOW}============= 强化预览 ============={Color.RESET}")
    for slot, label in (("weapon", "兵刃"), ("armor", "防具")):
        preview = player.get_enhancement_preview(slot)
        if not preview or not preview.get("name"):
            print(f"{label}：未装备")
            continue
        if not preview.get("available"):
            reason = "已达强化上限" if preview.get("reason") == "max" else "无法强化"
            print(f"{label}：{preview['name']} +{preview.get('current_level', 0)}/{preview.get('max_level', 0)} —— {reason}")
            continue
        print(
            f"{label}：{preview['name']} [{preview['quality']}] "
            f"+{preview['current_level']} → +{preview['next_level']} "
            f"| 属性 {preview['current_stat']} → {preview['next_stat']} "
            f"({preview['stat_delta']:+d}) "
            f"| 成本 {preview['ore_cost']} 铁矿石 + {preview['gold_cost']} 两"
        )
    print(f"{Color.BRIGHT_YELLOW}===================================={Color.RESET}")


def handle_forge(player, args):
    if player.location not in ("blacksmith", "guiyun_forge"):
        print("只有在打铁铺才可以强化装备！")
        return False

    if args and args[0].lower() in ("preview", "预览", "查看"):
        _print_forge_preview(player)
        return False

    print(f"\n{Color.BRIGHT_YELLOW}================ 铁匠打造炉 ================{Color.RESET}")
    w_name = player.equipment.get("weapon") or "无"
    a_name = player.equipment.get("armor") or "无"
    w_lv = player.equip_enhance.get("weapon", 0)
    a_lv = player.equip_enhance.get("armor", 0)
    ore_cnt = player.inventory.count("铁矿石")

    w_info = player.get_equipment_stats("weapon") if w_name != "无" else {}
    a_info = player.get_equipment_stats("armor") if a_name != "无" else {}
    print(f"当前兵刃：{Color.GREEN}{w_name} (+{w_lv}/{w_info.get('enhance_max', 5)}){Color.RESET}")
    print(f"当前防具：{Color.GREEN}{a_name} (+{a_lv}/{a_info.get('enhance_max', 5)}){Color.RESET}")
    print(f"拥有铁矿石：{Color.YELLOW}{ore_cnt} 块{Color.RESET}  银两：{Color.YELLOW}{player.gold} 两{Color.RESET}")
    print("--------------------------------------------")
    print(f"1. 强化兵刃（{w_info.get('enhance_ore_cost', 1)} 块铁矿石 + {w_info.get('enhance_gold_cost', 30)} 银两）")
    print(f"2. 强化防具（{a_info.get('enhance_ore_cost', 1)} 块铁矿石 + {a_info.get('enhance_gold_cost', 30)} 银两）")
    print("p. 查看下一等级属性与成本预览")
    print("0. 离开打造炉")

    choice = input("请选择打造项目 (0-2)：").strip()
    if choice.lower() in ("p", "预览"):
        _print_forge_preview(player)
        return False
    if choice == "1":
        slot_key, target_name = "weapon", w_name
    elif choice == "2":
        slot_key, target_name = "armor", a_name
    else:
        return False

    if target_name == "无":
        print(f"{Color.RED}你身上并未装备对应的{'兵刃' if slot_key=='weapon' else '防具'}！{Color.RESET}")
        return False

    equip_info = player.get_equipment_stats(slot_key)
    max_lv = equip_info.get("enhance_max", 5)
    ore_cost = equip_info.get("enhance_ore_cost", 1)
    gold_cost = equip_info.get("enhance_gold_cost", 30)
    current_lv = player.equip_enhance.get(slot_key, 0)
    if current_lv >= max_lv:
        print(f"{Color.RED}该装备已经强化至最高等级 (+{max_lv})！{Color.RESET}")
        return False

    if ore_cnt < ore_cost or player.gold < gold_cost:
        print(f"{Color.RED}强化材料不足！需要 {ore_cost} 块铁矿石及 {gold_cost} 银两。{Color.RESET}")
        return False

    removed, remaining = remove_inventory_items(
        player, "铁矿石", ore_cost, action="消耗", announce=False
    )
    if not removed:
        print(f"{Color.RED}强化失败：需要 铁矿石 ×{ore_cost}，当前 {remaining}。{Color.RESET}")
        return False
    print(f"{Color.YELLOW}{format_item_change('铁矿石', ore_cost, remaining, action='消耗')}{Color.RESET}")
    player.gold -= gold_cost
    # Alpha110：强化消耗的矿石与银两退出流通，避免只统计交易、不统计实际消耗。
    from economy.flow import record_player_consumption
    record_player_consumption(player, "铁矿石", ore_cost, source="装备强化", gold=gold_cost)
    before = player.get_equipment_stats(slot_key)
    before_stat = before.get("atk", 0) if slot_key == "weapon" else before.get("defense", 0)
    player.equip_enhance[slot_key] += 1
    new_lv = player.equip_enhance[slot_key]
    after = player.get_equipment_stats(slot_key)
    after_stat = after.get("atk", 0) if slot_key == "weapon" else after.get("defense", 0)
    print(f"\n{Color.BRIGHT_GREEN}锤打叮当，火花四溅！你的【{target_name}】成功强化至 +{new_lv}！{Color.RESET}")
    print(f"强化属性：{before_stat} → {after_stat}（+{after_stat - before_stat}）")
    print(f"剩余材料：铁矿石 {player.inventory.count('铁矿石')} 块 | 银两 {player.gold} 两")
    request_autosave(player)
    return True
