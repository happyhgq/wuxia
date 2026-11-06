# -*- coding: utf-8 -*-
"""
main.py - 孤侠初入江湖总引擎入口
"""

import os
import random
import sys
import difflib
import engine
import help_system
import weather
import world_ambience
from entry_events import trigger_entry_events
from item_feedback import add_inventory_items, format_item_change
from world_time import format_world_clock
from ui_output import (
    BODY_WIDTH,
    colors_enabled,
    format_action_feedback,
    get_color_mode,
    safe_print as print,
    set_color_mode,
    wrap_player_text,
)

Color = engine.Color
SAVE_PATH = engine.SAVE_PATH


def _apply_player_world_resource_effects(manager, player):
    """把已完成的世界委托反馈到真实资源点、NPC 供料与生产；不改变存档结构。"""
    apply_progress = getattr(manager, "apply_world_progress", None)
    if callable(apply_progress):
        apply_progress(getattr(player, "world_state", {}))
    resources = getattr(manager, "resources", {})
    if not isinstance(resources, dict):
        return
    if player.get_flag("world:main:mistwood_herb_route_safe", False):
        cfg = resources.get("herb_springbank")
        if isinstance(cfg, dict):
            # 蛛患清除后，浅滩可安全采集的区域扩大，资源恢复也略快。
            cfg["capacity"] = max(12, int(cfg.get("capacity", 0) or 0))
            cfg["regen_amount"] = max(3, int(cfg.get("regen_amount", 0) or 0))


def _resource_result_status(manager, room_id):
    """用与场景提示一致的储量口径反馈本次采集后的真实剩余量。"""
    cfg = manager.resources.get(room_id, {}) if isinstance(getattr(manager, "resources", {}), dict) else {}
    if not isinstance(cfg, dict) or not cfg:
        return ""
    try:
        capacity = max(0, int(cfg.get("capacity", 0) or 0))
    except (TypeError, ValueError, OverflowError):
        capacity = 0
    state = manager.export_state() if hasattr(manager, "export_state") else {}
    rows = state.get("resources", {}) if isinstance(state, dict) else {}
    row = rows.get(room_id, {}) if isinstance(rows, dict) else {}
    try:
        remaining = max(0, min(capacity, int(row.get("remaining", capacity) or 0))) if isinstance(row, dict) else capacity
    except (TypeError, ValueError, OverflowError):
        remaining = capacity
    item = str(cfg.get("item", "资源"))
    return f"当前地点剩余{item}储量：{remaining}/{capacity}。"


def select_random_encounter(player, room, zone, security, travel):
    """按治安/通行抽取一次随机遭遇；死亡或尸体计时中的敌人不会重复刷新。"""
    room = room if isinstance(room, dict) else {}
    try:
        security = max(0, min(100, int(security)))
        travel = max(0, min(100, int(travel)))
    except (TypeError, ValueError, OverflowError):
        security, travel = 70, 70
    safe = bool(room.get("safe", False))
    room_id = getattr(player, "location", "")
    if not safe and room.get("enemies"):
        from world_lifecycle import calculate_encounter_chance
        chance = calculate_encounter_chance(security, travel)
    elif safe:
        from region_activity import urban_crime_chance
        chance = urban_crime_chance(zone, room_id, security)
    else:
        chance = 0.0
    if chance <= 0 or random.random() >= chance:
        return None
    from world_lifecycle import visible_enemies, random_encounter_candidates
    living, _ = visible_enemies(player, room_id, room.get("enemies", []))
    if safe:
        from region_activity import urban_crime_enemies
        extras = urban_crime_enemies(zone, room_id, security)
    else:
        from region_activity import extra_enemies
        extras = extra_enemies(zone, security)
    extras = [name for name in extras if name in engine.ENEMIES and name not in living]
    extra_alive, _ = visible_enemies(player, room_id, extras)
    living.extend(extra_alive)
    living = random_encounter_candidates(living, engine.ENEMIES)
    if not living:
        return None
    return random.choice(living)


clear_screen = engine.clear_screen
reload_game_data = engine.reload_game_data
battle_pause = engine.battle_pause
clear_statuses = engine.clear_statuses
from player import Player
from combat import combat, handle_attack
from actions import look, handle_world_activity, handle_local_business_rumor, handle_npc_actions, handle_talk_and_ask, handle_relations, handle_sect, handle_skills, handle_explore, handle_world_events, handle_information, handle_notice_board, handle_quest, handle_trading, handle_equipment_and_items, handle_forge, handle_attributes, show_build, handle_factions, handle_faction_conflicts, handle_region_ecology, handle_player_influence, handle_inn_service, handle_security_governance
from command_policy import command_will_be_handled, command_advances_world, preflight_guaranteed_failure


CMD_MAP = {
    # 方向：中文汉字为主，拼音/英文继续兼容
    "北": "n", "南": "s", "东": "e", "西": "w",
    "内": "内", "外": "外", "后": "后", "前": "前",
    "进入": "内", "进去": "内", "出外": "外", "出去": "外",
    "bei": "n", "nan": "s", "dong": "e", "xi": "w",
    "n": "n", "s": "s", "e": "e", "w": "w",
    "north": "n", "south": "s", "east": "e", "west": "w",

    # 系统
    "看": "look", "查看": "look", "观察": "look", "look": "look", "l": "look", "查": "look",
    "背包": "inventory", "行囊": "inventory", "inventory": "inventory", "i": "inventory", "包": "inventory",
    "状态": "status", "status": "status", "st": "status", "状": "status",
    "职业": "profession", "采集熟练": "profession", "profession": "profession",
    "帮助": "help", "指令": "help", "帮助菜单": "help", "help": "help", "h": "help", "帮": "help", "?": "help", "？": "help",
    "百科": "encyclopedia", "江湖百科": "encyclopedia", "知识": "encyclopedia",
    "建议": "advice", "提示": "advice", "下一步": "advice",
    "颜色": "color", "色彩": "color", "color": "color", "colour": "color",
    "保存": "save", "存档": "save", "save": "save", "存": "save",
    "读档": "load", "读取": "load", "载入": "load", "load": "load", "读": "load",
    "退出": "quit", "离开游戏": "quit", "quit": "quit", "exit": "quit", "q": "quit", "退": "quit",
    "重载": "reload", "热重载": "reload", "reload": "reload", "rl": "reload",

    # 角色成长
    "属性": "attributes", "属性点": "attributes", "加点": "attributes",
    "attributes": "attributes", "attribute": "attributes", "attr": "attributes", "addpoint": "attributes",
    "流派": "build", "build": "build", "bd": "build",

    # 人物与信息
    "交谈": "talk", "聊天": "talk", "对话": "talk", "打听": "talk", "问": "talk",
    "talk": "talk", "chat": "talk", "ask": "talk", "t": "talk",
    "关系": "relations", "人物关系": "relations", "relations": "relations", "relation": "relations",
    "记忆": "memory", "回忆": "memory", "memory": "memory", "memories": "memory",
    "信息": "information", "消息": "information", "传闻": "information", "江湖消息": "information",
    "information": "information", "info": "information", "rumors": "information",
    "公告": "notice_board", "公告栏": "notice_board", "榜墙": "notice_board", "江湖榜墙": "notice_board", "notice": "notice_board",
    "商队": "caravan", "商路": "caravan", "商旅": "caravan", "caravan": "caravan",
    "人物行动": "npc_actions", "人物行动记录": "npc_actions", "npc行动": "npc_actions",
    "世界动态": "world_activity", "营生动态": "world_activity", "world_activity": "world_activity",
    "商情": "business_rumor", "营生消息": "business_rumor", "附近营生": "business_rumor", "business_rumor": "business_rumor",
    "npc_actions": "npc_actions", "npcaction": "npc_actions",

    # 任务
    "任务": "quests", "任务列表": "quests", "查看任务": "quests", "任": "quests",
    "quest": "quests", "quests": "quests", "renwu": "quests",
    "接取": "jiequ", "接任务": "jiequ", "接受任务": "jiequ", "jiequ": "jiequ",
    "交付": "jiaofu", "交任务": "jiaofu", "完成任务": "jiaofu", "jiaofu": "jiaofu",
    "放弃": "fangqi", "放弃任务": "fangqi", "fangqi": "fangqi", "abandon": "abandon",
    "选择": "xuanze", "选择分支": "xuanze", "分支": "xuanze", "xuanze": "xuanze", "branch": "xuanze",

    # 探索与事件
    "地图": "map", "地图查看": "map", "map": "map", "m": "map", "ditu": "map", "图": "map",
    "探索": "explore", "探险": "explore", "explore": "explore", "探": "explore",
    "停留": "wait", "停": "wait",
    "搜索": "search", "搜寻": "search", "search": "search", "采集": "collect", "collect": "collect",
    "采矿": "mine", "挖矿": "mine", "mine": "mine",
    "伐木": "chop", "砍树": "chop", "采伐": "chop", "chop": "chop", "logging": "chop",
    "事件": "events", "事件列表": "events", "events": "events", "event": "events", "事": "events",

    # 战斗与恢复
    "攻击": "kill", "战斗": "kill", "击杀": "kill", "kill": "kill", "attack": "kill", "fight": "kill", "k": "kill", "打": "kill",
    "打坐": "heal", "调息": "heal", "恢复": "heal", "疗伤": "heal", "heal": "heal", "dazuo": "heal", "疗": "heal",

    # 客栈服务
    "住店": "inn_stay", "住宿": "inn_stay", "客房": "inn_stay", "休息一晚": "inn_stay", "留宿": "inn_stay", "歇宿": "inn_stay",
    "吃饭": "inn_meal", "用餐": "inn_meal", "打尖": "inn_meal", "饭菜": "inn_meal", "吃东西": "inn_meal",
    "喝茶": "inn_tea", "饮茶": "inn_tea", "听消息": "inn_rumor", "打听消息": "inn_rumor", "风声": "inn_rumor",

    # 交易与打造
    "商店": "shop", "店铺": "shop", "shop": "shop", "商": "shop",
    "货架": "list", "货单": "list", "商品": "list", "list": "list",
    "购买": "buy", "买": "buy", "buy": "buy",
    "出售": "sell", "卖": "sell", "sell": "sell",
    "打造": "forge", "锻造": "forge", "强化": "forge", "forge": "forge", "f": "forge", "铸": "forge",

    # 装备与物品
    "装备": "equipment", "装备栏": "equipment", "equipment": "equipment", "装": "equipment",
    "敲门": "knock", "叩门": "knock", "knock": "knock",
    "比较": "compare", "装备比较": "compare", "compare": "compare",
    "卸下": "unequip", "卸装备": "unequip", "unequip": "unequip",
    "装备武器": "wield", "持剑": "wield", "wield": "wield",
    "穿戴": "wear", "佩戴": "wear", "穿防具": "wear", "wear": "wear",
    "穿戴装备": "equip", "装备物品": "equip", "equip": "equip",
    "使用": "use", "使用物品": "use", "use": "use",

    # 门派 / 武学 / 势力 / 区域
    "门派": "sect", "宗门": "sect", "sect": "sect", "门": "sect", "拜师": "sect_join",
    "武学": "skills", "武功": "skills", "技能": "skills", "skills": "skills", "skill": "skills", "wuxue": "skills", "武": "skills", "技": "skills",
    "势力": "factions", "阵营": "factions", "faction": "factions", "factions": "factions", "势": "factions",
    "冲突": "conflicts", "局势": "conflicts", "势力冲突": "conflicts", "conflicts": "conflicts", "局": "conflicts",
    "旅行": "travel", "行路": "travel", "travel": "travel",
    "区域": "region", "区域局势": "region", "地区": "region", "region": "region", "regions": "region", "区": "region",
    "治安": "security_governance", "治安悬赏": "security_governance", "security_governance": "security_governance",
    "影响": "influence", "势力影响": "influence", "个人影响": "influence", "influence": "influence", "影": "influence",

    # 传统英文/拼音兼容
    "flee": "run", "run": "run",

    # ZMUD 风格输入层
    "别名": "alias", "alias": "alias", "快捷": "alias",
    "删除别名": "unalias", "取消别名": "unalias", "unalias": "unalias",
    "历史": "history", "命令历史": "history", "history": "history",
    "上": "u", "上楼": "u", "up": "u",
    "下": "d", "下楼": "d", "down": "d",
    "上条": "history_up", "上一条": "history_up",
    "下条": "history_down", "下一条": "history_down",
}



MAX_COMMAND_CHAIN = 8
MAX_ALIAS_LENGTH = 120


def _print_resource_route_suggestions(player, manager, action, item):
    """资源点耗尽时，按真实地图出口推荐附近仍有同类资源的地点。"""
    rooms = getattr(engine, "ROOMS", {})
    if not isinstance(rooms, dict) or player.location not in rooms:
        return
    queue = [(player.location, 0)]
    visited = {player.location}
    alternatives = []
    while queue:
        room_id, distance = queue.pop(0)
        room_data = rooms.get(room_id, {})
        cfg = manager.resources.get(room_id, {}) if isinstance(manager.resources, dict) else {}
        if distance > 0 and isinstance(cfg, dict) and cfg.get("action", "mine") == action and str(cfg.get("item", "")) == str(item):
            row = manager.state.resources.get(room_id, {})
            available = row.get("remaining", cfg.get("capacity", 0)) if isinstance(row, dict) else cfg.get("capacity", 0)
            try:
                available = max(0, int(available))
            except (TypeError, ValueError, OverflowError):
                available = 0
            if available > 0:
                alternatives.append((distance, str(room_data.get("name", cfg.get("name", "其他资源点"))), available, int(cfg.get("capacity", 0))))
        if distance >= 2:
            continue
        exits = room_data.get("exits", {}) if isinstance(room_data, dict) else {}
        for next_room in exits.values() if isinstance(exits, dict) else []:
            if next_room in rooms and next_room not in visited:
                visited.add(next_room)
                queue.append((next_room, distance + 1))
    if alternatives:
        alternatives.sort(key=lambda row: (row[0], row[1]))
        names = []
        for _, name, remaining, capacity in alternatives:
            label = f"{name}（{remaining}/{capacity}）"
            if label not in names:
                names.append(label)
            if len(names) >= 3:
                break
        print("附近仍有可用资源的地点：" + "、".join(names) + "。输入“地图”查看路线。")
    else:
        print("附近两步内暂未发现仍有储量的同类资源点；可查看“地图”前往更远地点，或等待本处自然恢复。")


def _command_aliases(player):
    """将快捷命令放入既有 V12 world_state.variables，不增加存档版本。"""
    variables = player.world_state.setdefault("variables", {})
    aliases = variables.setdefault("command_aliases", {})
    if not isinstance(aliases, dict):
        aliases = {}
        variables["command_aliases"] = aliases
    # 防止旧档或手工修改造成危险/异常数据。
    cleaned = {}
    for name, value in aliases.items():
        if isinstance(name, str) and isinstance(value, str) and name.strip() and value.strip():
            if len(name.strip()) <= 20 and len(value.strip()) <= MAX_ALIAS_LENGTH:
                cleaned[name.strip()] = value.strip()
    if cleaned != aliases:
        variables["command_aliases"] = cleaned
    return variables["command_aliases"]


def split_command_chain(raw):
    """拆分 MUD 风格的 ; 连续指令；中文全角“；”也兼容，最多执行 8 条。"""
    normalized = raw.replace("；", ";")
    return [part.strip() for part in normalized.split(";") if part.strip()][:MAX_COMMAND_CHAIN]


def expand_alias(raw, player):
    """只展开首词别名；已知正式命令优先，避免覆盖系统命令。"""
    text = raw.strip()
    if not text:
        return text
    first, *rest = text.split(None, 1)
    aliases = _command_aliases(player)
    if first in aliases and first not in CMD_MAP:
        expansion = aliases[first]
        if rest:
            expansion = f"{expansion} {rest[0]}"
        return expansion
    return text


def resolve_room_exit(player, room, direction):
    """解析普通出口与已发现的隐藏出口；未解锁的隐藏出口返回玩家可读提示。"""
    exits = room.get("exits", {}) if isinstance(room, dict) else {}
    if direction in exits:
        return exits[direction], ""
    hidden = room.get("hidden_exits", {}) if isinstance(room, dict) else {}
    entry = hidden.get(direction) if isinstance(hidden, dict) else None
    if isinstance(entry, dict):
        flag = str(entry.get("flag", ""))
        if flag and player.get_flag(flag):
            target = entry.get("target")
            if target in engine.ROOMS:
                return target, ""
        return None, str(entry.get("blocked_text", "这条隐蔽通路尚未开启。"))
    return None, ""


def movement_block_reason(player, room, cmd):
    """预先判断移动是否会失败；失败移动不推进世界时钟。

    只做只读判断，不消耗邀请、不改变位置；实际移动仍走原分支。
    """
    direction = {
        "n": "北", "s": "南", "e": "东", "w": "西", "u": "上", "d": "下",
        "内": "内", "外": "外", "前": "前", "后": "后",
    }.get(cmd)
    if direction is None:
        return ""
    exits = room.get("exits", {}) if isinstance(room, dict) else {}
    hidden = room.get("hidden_exits", {}) if isinstance(room, dict) else {}
    if direction not in exits and not (isinstance(hidden, dict) and direction in hidden):
        if direction == "下" and room.get("zone") == "inn_upper":
            return "这间客房没有楼梯，请先回到走廊再下楼。"
        if direction == "下":
            return "这里没有往下的出口。"
        if direction == "上":
            return "这里没有往上的出口。"
        return f"这里没有往{direction}的出口。"
    destination, blocked_message = resolve_room_exit(player, room, direction)
    if destination is None:
        return blocked_message or "这条出口暂时无法通过。"
    destination_room = engine.ROOMS.get(destination, {})
    from travel_system import room_access_denial
    denial = room_access_denial(player, destination_room if isinstance(destination_room, dict) else {})
    if denial:
        return denial
    residence = destination_room.get("residence", {}) if isinstance(destination_room, dict) else {}
    if isinstance(residence, dict) and residence.get("private"):
        owner = residence.get("owner")
        variables = getattr(player, "world_state", {}).get("variables", {})
        invites = variables.get("residence_invites", {}) if isinstance(variables, dict) else {}
        invited = invites.get(destination, False) if isinstance(invites, dict) else False
        relation = player.get_relation(owner) if owner and hasattr(player, "get_relation") else 0
        threshold = int(residence.get("trust_required", 20))
        if not invited and relation < threshold:
            return "私人院落尚未邀请你进入。"
    return ""


def command_suggestions(raw, limit=5):
    token = raw.strip().split()[0] if raw.strip() else ""
    if not token:
        return []
    choices = sorted(set(CMD_MAP.keys()))
    return difflib.get_close_matches(token, choices, n=limit, cutoff=0.45)


def handle_alias_command(player, args):
    """管理玩家快捷命令：别名、别名 名称 = 指令链、删除别名 名称。"""
    aliases = _command_aliases(player)
    if not args:
        if not aliases:
            print("当前没有自定义快捷命令。")
            print("用法：别名 回村 = 南;南;西")
            return
        print("\n快捷命令：")
        for name, value in sorted(aliases.items()):
            print(f"  {name} = {value}")
        print("删除：删除别名 <名称>")
        return
    raw = " ".join(args).strip()
    if "=" in raw:
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
    else:
        bits = raw.split(None, 1)
        if len(bits) != 2:
            print("用法：别名 <名称> = <指令>；例如：别名 回村 = 南;南;西")
            return
        name, value = bits[0].strip(), bits[1].strip()
    if not name or not value:
        print("快捷命令名称和内容都不能为空。")
        return
    if name in CMD_MAP or name in {"别名", "删除别名", "历史", "上", "下"}:
        print("这个名称已经是系统命令，不能覆盖。")
        return
    if ";" in name or len(name) > 20 or len(value) > MAX_ALIAS_LENGTH:
        print(f"快捷命令名称最多 20 字，内容最多 {MAX_ALIAS_LENGTH} 字，名称不能含“;”。")
        return
    aliases[name] = value
    print(f"已设置快捷命令：{name} = {value}")
    player.save_to_file()


def handle_unalias_command(player, args):
    aliases = _command_aliases(player)
    name = " ".join(args).strip()
    if not name:
        print("用法：删除别名 <名称>")
        return
    if name in aliases:
        del aliases[name]
        player.save_to_file()
        print(f"已删除快捷命令：{name}")
    else:
        print(f"没有找到快捷命令：{name}")


def show_command_history(history):
    if not history:
        print("暂无命令历史。")
        return
    print("\n最近命令：")
    start = max(0, len(history) - 12)
    for idx, command in enumerate(history[start:], start=start + 1):
        print(f"  {idx:>2}. {command}")


def _render_input_line(prompt, buf, last_width):
    """按终端显示宽度重绘输入行，中文宽字符删除后不会残留半列。"""
    text = prompt + "".join(buf)
    width = engine.get_display_width(text)
    sys.stdout.write("\r" + " " * max(width, last_width) + "\r" + text)
    sys.stdout.flush()
    return width


def read_command(prompt, history):
    """轻量跨平台命令行编辑：支持上下箭头历史；非交互环境退回 input。"""
    if not getattr(sys.stdin, "isatty", lambda: False)():
        return input(prompt)
    try:
        if os.name == "nt":
            import msvcrt
            sys.stdout.write(prompt)
            sys.stdout.flush()
            buf, pos, hist_idx = [], 0, len(history)
            line_width = engine.get_display_width(prompt)
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    return "".join(buf)
                if ch == "\003":
                    raise KeyboardInterrupt
                if ch in ("\x00", "\xe0"):
                    code = msvcrt.getwch()
                    if code == "H" and history:
                        hist_idx = max(0, hist_idx - 1)
                    elif code == "P" and history:
                        hist_idx = min(len(history), hist_idx + 1)
                    else:
                        continue
                    text = history[hist_idx] if hist_idx < len(history) else ""
                    buf, pos = list(text), len(text)
                    line_width = _render_input_line(prompt, buf, line_width)
                    continue
                if ch == "\b":
                    if pos:
                        buf.pop(pos - 1); pos -= 1
                        line_width = _render_input_line(prompt, buf, line_width)
                    continue
                if ch.isprintable():
                    buf.insert(pos, ch); pos += 1
                    line_width = _render_input_line(prompt, buf, line_width)
        else:
            import termios, tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                sys.stdout.write(prompt); sys.stdout.flush()
                buf, pos, hist_idx = [], 0, len(history)
                line_width = engine.get_display_width(prompt)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        sys.stdout.write("\n"); sys.stdout.flush(); return "".join(buf)
                    if ch == "\x03": raise KeyboardInterrupt
                    if ch == "\x7f":
                        if pos:
                            buf.pop(pos - 1); pos -= 1
                            line_width = _render_input_line(prompt, buf, line_width)
                        continue
                    if ch == "\x1b":
                        seq = sys.stdin.read(2)
                        if seq == "[A" and history: hist_idx = max(0, hist_idx - 1)
                        elif seq == "[B" and history: hist_idx = min(len(history), hist_idx + 1)
                        else: continue
                        text = history[hist_idx] if hist_idx < len(history) else ""
                        buf, pos = list(text), len(text)
                        line_width = _render_input_line(prompt, buf, line_width)
                        continue
                    if ch.isprintable():
                        buf.insert(pos, ch); pos += 1
                        line_width = _render_input_line(prompt, buf, line_width)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except (ImportError, OSError, AttributeError):
        return input(prompt)


def resolve_help_menu_input(raw_input, navigation_state):
    """仅在帮助导航上下文中，把单独数字或翻页词转换为帮助路径。"""
    value = str(raw_input).strip()
    if not value or navigation_state in (None, ""):
        return raw_input
    if navigation_state == "top":
        if value in ("0", "返回", "返回上级"):
            return "帮助"
        return f"帮助 {value}" if help_system.is_category_selector(value) else raw_input
    if navigation_state.startswith("category:"):
        parts = navigation_state.split(":")
        category_id = parts[1]
        category_no = help_system.category_number(category_id)
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        number = help_system.to_number(value)
        if number is not None:
            return "帮助" if number == 0 else f"帮助 {category_no} {value}"
        if value in ("上页", "下页"):
            target = page + (1 if value == "下页" else -1)
            return f"帮助 {category_no} 页{max(1, target)}"
        return raw_input
    if navigation_state.startswith("detail:"):
        parts = navigation_state.split(":")
        category_id = parts[1]
        index = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        if value == "0":
            page = help_system.page_for_index(category_id, index)
            return f"帮助 {help_system.category_number(category_id)} 页{page}"
        category = help_system.CATEGORY_BY_ID.get(category_id)
        entries = category["entries"] if category else []
        entry_id = entries[index - 1] if 0 < index <= len(entries) else None
        if help_system.to_number(value) is not None and entry_id:
            # 详情页没有下一层编号：保留当前位置，只给返回提示。
            return f"帮助 {help_system.NAV_DETAIL_HINT} {category_id} {entry_id}"
        return raw_input
    return raw_input


def next_help_navigation_state(cmd, args):
    """根据刚执行的帮助指令记录层级；其他命令退出帮助导航。"""
    if cmd != "help":
        return None
    result = help_system.classify(" ".join(args).strip())
    kind = result["kind"]
    if kind in ("main", "invalid_top"):
        return "top"
    if kind in ("category", "invalid_index", "invalid_entry", "invalid_page"):
        category = result["category"]
        return f"category:{category['id']}:{result.get('page', 1)}"
    if kind in ("detail", "detail_hint"):
        category = result["category"]
        entry_id = result["entry_id"]
        return f"detail:{category['id']}:{help_system.entry_number(entry_id)}"
    return None


def parse_command(user_input):
    parts = user_input.strip().split()
    if not parts:
        return "", []
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    cmd = CMD_MAP.get(cmd, cmd)
    if cmd in ("jiequ", "jiaofu", "relations", "sect", "fangqi", "abandon", "xuanze") and args:
        args = [" ".join(args)]
    elif cmd == "quests" and args:
        # “任务 <多字任务名>”作为详情查询时合并任务名；
        # “任务 接取/交付/放弃/选择 <任务名>”则保留子命令边界供任务处理器解析。
        quest_subcommands = {"接取", "接受", "接任务", "接取任务", "接受任务", "交付", "交任务", "完成", "放弃", "放弃任务", "选择", "分支", "选择分支"}
        if args[0] not in quest_subcommands:
            args = [" ".join(args)]
    return cmd, args


def _is_direct_quest_accept_command(cmd, args):
    """公告/命令不能直接领取任务；正式接取须经对应 NPC 对话。"""
    return cmd in {"jiequ", "接受委托", "领取委托"} or (
        cmd == "quests" and bool(args) and str(args[0]).strip() in {"接取", "接受", "接任务", "接取任务", "接受任务"}
    )


def show_map(player):
    from engine import MAP_ENGINE
    print(MAP_ENGINE.render(player.location, player))
    room = engine.ROOMS.get(player.location, {})
    hidden = room.get("hidden_exits", {}) if isinstance(room, dict) else {}
    discovered = []
    clues = []
    if isinstance(hidden, dict):
        for direction, entry in hidden.items():
            if not isinstance(entry, dict) or not entry.get("flag"):
                continue
            if player.get_flag(entry.get("flag")):
                target_key = entry.get("target")
                if target_key not in engine.ROOMS:
                    target_name = "隐蔽地点"
                else:
                    display_name = getattr(engine.MAP_ENGINE, "display_name", None)
                    target_name = display_name(target_key) if callable(display_name) else engine.ROOMS[target_key].get("name", "隐蔽地点")
                discovered.append(f"{direction} → {target_name}")
            else:
                # 只提示有待调查的线索，不提前暴露隐藏房间名称或把它伪装成普通出口。
                clues.append(f"{direction}侧石壁")
    if clues:
        print("尚未查明的隐蔽线索：" + "、".join(clues) + "；输入“探索”调查。")
    if discovered:
        print("已发现的隐蔽出口：")
        for exit_info in discovered:
            print(f"  - {exit_info}")


def _resource_tool_bonus(player, action, field):
    """读取行囊中对应采集工具的配置加成；同类工具不叠加，避免重复购买刷收益。"""
    bonus = 0.0
    for item_name in getattr(player, "inventory", []) or []:
        info = engine.ITEMS.get(item_name, {})
        effect = info.get("tool_effect", {}) if isinstance(info, dict) else {}
        if isinstance(effect, dict) and effect.get("action") == action:
            try:
                bonus = max(bonus, float(effect.get(field, 0) or 0))
            except (TypeError, ValueError, OverflowError):
                continue
    return bonus


def gather_search_failure_text(exhausted_items):
    """区分资源耗尽与本次随机搜寻未成功，避免误导玩家。"""
    if exhausted_items:
        item_label = "、".join(dict.fromkeys(str(item) for item in exhausted_items))
        return f"这里的{item_label}已经采尽，暂时不会继续产出。可以沿出口前往其他采集地点；各场景储量独立，离开后会按各自周期恢复。"
    return "这次没有找到可采集的资源；这里仍可能有剩余资源，可以再试一次，或查看场景储量提示。"


def _status_text_width(value):
    """计算不含 ANSI 颜色控制符的终端显示宽度。"""
    import re
    import unicodedata
    plain = re.sub(r"\x1b\[[0-9;]*m", "", str(value))
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in plain)


def _status_line(label, value, width=BODY_WIDTH):
    """格式化状态字段；超宽时换行，不截断标签或数值。"""
    label = str(label)
    value = str(value)
    label_width = _status_text_width(label)
    gap = max(1, 14 - label_width)
    first = label + " " * gap + value
    if _status_text_width(first) <= width:
        return [first]
    wrapped = wrap_player_text(value, width=max(12, width - 14))
    rows = wrapped.splitlines() or [""]
    return [label + " " * gap + rows[0]] + [" " * 14 + row for row in rows[1:]]


def show_status(player, panel="main"):
    """显示侠客状态主面板或五个只读子面板。"""
    from engine import draw_bar, format_statuses

    panel_titles = {"sect": "门派", "reputation": "江湖声名", "combat": "战斗属性", "growth": "成长倾向", "endgame": "终局目标"}
    if panel not in panel_titles and panel != "main":
        panel = "main"

    def line(label, value):
        for rendered in _status_line(label, value):
            print(rendered)

    def divider():
        print("------------------------------")

    if panel == "main":
        print(f"\n{Color.CYAN}========== 侠客状态 =========={Color.RESET}")
        # 姓名与门派同一行，宽度不足时安全换行。
        identity = f"姓名：{player.name}    门派：{player.get_sect()}"
        for rendered in wrap_player_text(identity, width=BODY_WIDTH).splitlines():
            print(rendered)
        line("江湖身份：", player.get_jianghu_identity_title())
        line("世界时间：", format_world_clock(player.get_quest_clock()))
        weather_info = weather.snapshot(player)
        line("天时：", f"{weather_info['term']} · {weather_info['label']}")
        line("等级：", f"{player.level} 级（{player.get_character_realm_title()}）")
        line("修为：", draw_bar(player.exp, player.exp_to_level, length=8, fill_color=Color.YELLOW))
        line("气血：", draw_bar(player.hp, player.max_hp, fill_color=Color.RED))
        line("内力：", draw_bar(player.mp, player.max_mp, fill_color=Color.BLUE))
        divider()
        print("输入序号查看详情：")
        print("1 门派    2 江湖声名    3 战斗属性    4 成长倾向    5 终局目标    0 关闭面板")
        print(f"{Color.CYAN}=============================={Color.RESET}")
        return

    print(f"\n{Color.CYAN}========== {panel_titles[panel]} =========={Color.RESET}")
    if panel == "sect":
        line("门派：", player.get_sect())
        sect_label = "门派身份：" if player.get_sect() == "少林" else "门派职位："
        line(sect_label, player.get_sect_official_rank())
        mentorship = player.get_sect_mentorship() if hasattr(player, "get_sect_mentorship") else {}
        mentor_name = mentorship.get("mentor") if isinstance(mentorship, dict) else None
        line("师承：", str(mentor_name) if mentor_name else "暂无师承")
        line("门派声望：", player.get_sect_reputation())
    elif panel == "reputation":
        line("江湖身份：", player.get_jianghu_identity_title())
        profile = player._jianghu_profile()
        honor_label, infamy_label = player.get_jianghu_reputation_labels()
        line("侠名：", f"{profile['honor']}（{honor_label}）")
        line("恶名：", f"{profile['infamy']}（{infamy_label}）")
    elif panel == "combat":
        line("攻击：", f"{player.get_total_atk()}（基础 {player.atk}）")
        line("防御：", f"{player.get_total_defense()}（基础 {player.defense}）")
        line("属性：", f"力量 {player.get_attribute('strength')}  体魄 {player.get_attribute('constitution')}  内息 {player.get_attribute('internal')}")
        line("其他属性：", f"身法 {player.get_attribute('agility')}  洞察 {player.get_attribute('insight')}")
        line("可用属性点：", player.attribute_points)
        line("命中：", f"{player.get_hit_chance()*100:.0f}%  暴击：{player.get_crit_chance()*100:.0f}%  闪避：{player.get_dodge_chance()*100:.0f}%")
        line("身上状态：", format_statuses(engine.p_statuses_global))
    elif panel == "growth":
        path_summary = player.get_jianghu_path_summary()
        line("人生倾向：", path_summary['current'])
        route_text = "  ".join(f"{name} {value}" for name, value in path_summary['paths'].items())
        line("路线倾向：", route_text)
    elif panel == "endgame":
        fort_cleared = player.get_flag("duanhun_ridge:fort_cleared", False)
        line("断魂堡：", "已攻破，岭上残匪仍在" if fort_cleared else "尚未攻破")
        sect_quests = ("少林·伏魔护寺", "武当·夜巡断魂", "华山·绝壁试锋", "铁衣门·断魂护镖")
        completed = sum(1 for name in sect_quests if name in player.completed_quests)
        line("门派终局委托：", f"已完成 {completed}/4（复做冷却 48 刻）")
        inventory = getattr(player, "inventory", None)
        iron = inventory.count("断魂精铁") if isinstance(inventory, list) else 0
        line("断魂精铁：", f"{iron} 块（3 块可在守岭猎户处换大还丹）")
        weapon = player.get_equipment_stats("weapon")
        armor = player.get_equipment_stats("armor")
        line("装备强化：", f"兵刃 +{weapon.get('enhance', 0)} / 防具 +{armor.get('enhance', 0)}")
        line("终局提示：", "L15 为当前内容封顶；可继续巡道、门派委托与断魂崖夜行客。")
    divider()
    print("0 返回状态面板    9 关闭面板")
    print(f"{Color.CYAN}=============================={Color.RESET}")


def handle_status_panel_input(raw_input, player, panel):
    """处理状态面板专用输入；返回新的面板状态，None 表示关闭。"""
    value = str(raw_input or "").strip()
    if panel == "main":
        targets = {"1": "sect", "2": "reputation", "3": "combat", "4": "growth", "5": "endgame"}
        if value in targets:
            panel = targets[value]
            show_status(player, panel)
            return panel
        if value == "0":
            print("已关闭状态面板。")
            return None
        print("请输入有效序号，或输入 0 关闭面板。")
        return panel
    if value == "0":
        show_status(player, "main")
        return "main"
    if value == "9":
        print("已关闭状态面板。")
        return None
    print("请输入有效序号，或输入 0 关闭面板。")
    return panel


def show_professions(player):
    """展示采集、伐木、采矿的持久化熟练度与下一级进度。"""
    from economy import EconomyManager
    manager = EconomyManager(getattr(player, "economy_state", {}))
    manager.real_time_regen = True
    print(f"\n{Color.BRIGHT_CYAN}========== 江湖营生 =========={Color.RESET}")
    print("熟练等级 3 起，采集成果有机会额外增加一份；仍受资源储量与背包空间限制。")
    for row in manager.profession_summary():
        if row["next_threshold"] is None:
            progress = "已达当前最高等级"
        else:
            progress = f"熟练 {row['xp']}/{row['next_threshold']}"
        print(f"【{row['name']}】等级 {row['level']}｜{progress}｜成功次数 {row['actions']}｜累计获得 {row['total_gathered']} 份")
    print("采集、伐木和采矿成功后会积累熟练度；输入“保存”可保存进度。")
    print(f"{Color.BRIGHT_CYAN}=============================={Color.RESET}")


def show_inventory(player):
    """以紧凑的文字 MUD 格式显示背包：物品名、数量、属性和用途清楚分列。"""
    from economy import TradeService
    from collections import Counter
    from engine import ITEMS

    capacity = max(0, int(getattr(player, "inventory_capacity", TradeService.DEFAULT_INVENTORY_CAPACITY)))
    counts = Counter(getattr(player, "inventory", []) or [])
    print(f"\n{Color.CYAN}========== 背包行囊（{sum(counts.values())}/{capacity}） =========={Color.RESET}")
    print(f"银两：{player.gold} 两")
    if not counts:
        print("身无长物。")
        print("提示：可通过采集、伐木、采矿、战斗或交易获得物品。")
        print(f"{Color.CYAN}================================{Color.RESET}")
        return

    def item_group(item_name):
        kind = ITEMS.get(item_name, {}).get("type", "")
        if kind == "weapon":
            return 0
        if kind == "armor":
            return 1
        if kind in ("consumable", "medicine", "food", "potion"):
            return 2
        return 3

    group_names = {0: "【兵刃】", 1: "【防具】", 2: "【药品与消耗品】", 3: "【材料与其他】"}
    previous_group = None
    for item, cnt in sorted(counts.items(), key=lambda row: (item_group(row[0]), str(row[0]))):
        info = ITEMS.get(item, {})
        group = item_group(item)
        if group != previous_group:
            print(group_names[group])
            previous_group = group
        desc = str(info.get("desc", "暂无说明"))
        kind = info.get("type", "")
        print(wrap_player_text(f"  {Color.GREEN}{item}{Color.RESET} ×{cnt}", width=BODY_WIDTH))
        detail_lines = []
        if kind == "weapon":
            detail_lines.append(f"攻击 +{info.get('atk', 0)}")
        elif kind == "armor":
            detail_lines.append(f"防御 +{info.get('defense', 0)}")
        if desc and (kind not in ("weapon", "armor") or desc != detail_lines[0]):
            label = "说明" if kind in ("weapon", "armor") else "用途"
            detail_lines.append(f"{label}：{desc}")
        for detail_line in detail_lines:
            print(wrap_player_text(f"    {detail_line}", width=BODY_WIDTH))
    print(f"{Color.CYAN}================================{Color.RESET}")


def show_help(topic=None, player=None):
    """三层帮助：分类目录 -> 分类页 -> 单条指令详情。"""
    help_system.show(topic)


def show_encyclopedia(topic=None):
    """P2.52：面向玩家的游戏内百科，不暴露内部变量/主题 ID。"""
    entries = {
        "角色": "你是江湖中的一名侠客。力量、体魄、内息、身法、洞察共同影响你的成长与战斗表现。",
        "属性": "力量偏向攻击，体魄偏向生存，内息影响内力，身法影响灵活性，洞察影响暴击等战斗判断。",
        "气血": "气血就是生命值；归零通常意味着战斗失败。安全时可以通过打坐等方式恢复。",
        "内力": "内力用于部分武学。内力不足时，相关武学无法正常施展。",
        "装备": "兵刃主要影响攻击，防具主要影响防御；装备还可能带有额外词条。",
        "武学": "武学是战斗中的主动手段。不同门派和成长路线会影响可学武功。",
        "任务": "任务推动人物故事和世界变化，部分任务会出现分支选择。",
        "门派": "门派决定一部分初始成长和武学方向，也会影响江湖人物关系。",
        "势力": "官府、商会、黑市等势力会彼此影响；冲突会改变地区生态。",
        "区域": "区域局势与危险程度会随势力冲突、世界事件和玩家行动变化；安全、商路和通行等指标由世界模拟在后台计算。",
        "公告": "公告栏是玩家获取公开江湖消息的主要入口。村中广场与天衡广场分别提供公告栏和江湖榜墙。",
        "NPC": "人物拥有关系、记忆和行动记录；与他们交谈可能获得任务、消息或改变关系。",
        "存档": "游戏会保存你的江湖进度。普通游戏操作不会要求你理解存档格式。",
    }
    aliases = {"人物": "NPC", "角色": "角色", "生命": "气血", "血量": "气血", "蓝": "内力", "势力冲突": "势力", "地区": "区域", "榜墙": "公告"}
    key = aliases.get(str(topic).strip(), str(topic).strip()) if topic else None
    if key and key in entries:
        display_key = "人物" if key == "NPC" else key
        print(f"\n{Color.BRIGHT_CYAN}========== 江湖百科：{display_key} =========={Color.RESET}")
        print(wrap_player_text(entries[key], width=BODY_WIDTH))
        return
    print(f"\n{Color.BRIGHT_CYAN}========== 江湖百科 =========={Color.RESET}")
    print("可查询：角色、属性、气血、内力、装备、武学、任务、门派、势力、区域、公告、人物、存档")
    print("用法：百科 <词条>，例如：百科 武学")


def show_context_advice(player):
    """P2.52：根据当前状态给出少量、可执行的下一步建议。"""
    room = engine.ROOMS.get(player.location, {})
    tips = []
    if player.hp < player.max_hp * 0.45 or player.mp < player.max_mp * 0.35:
        tips.append("你目前状态偏弱，可以先输入“打坐”恢复气血与内力。")
    if player.location in ("village_square", "guiyun_central_square"):
        tips.append("这里有公告栏/江湖榜墙，可以输入“公告”看看近期江湖消息。")
    if player.get_npcs_in_room(player.location):
        tips.append("附近有人物，可以输入“查看 <人物>”或“交谈 <人物>”了解他们。")
    if player.active_quests:
        tips.append("你手上有未完成任务，可以输入“任务”查看下一步目标。")
    elif player.location == "village_square":
        tips.append("你刚到村中，建议先“查看”，再与村中人物交谈，看看是否有事情可做。")
    if room.get("enemies") and player.hp >= player.max_hp * 0.45:
        tips.append("附近有潜在威胁；如果准备充分，可以先“查看 <敌人>”再决定是否战斗。")
    if not tips:
        tips.append("先输入“查看”了解当前环境；如果仍不知道做什么，可以“地图”寻找新的方向。")
    print(f"\n{Color.BRIGHT_YELLOW}========== 江湖提示 =========={Color.RESET}")
    for i, tip in enumerate(tips[:4], 1):
        print(f"{i}. {tip}")
    print("你也可以输入“帮助 新手”或“百科”了解系统。")


def create_new_player(name):
    """新角色以江湖散人身份开始；门派身份必须通过实际游戏流程取得。

    新档额外写入首日引导天气（晴 → 阴 → 小雨），让新手在前 20 次行动内
    至少经历一次天气变化；旧存档不会命中该入口。
    """
    player = Player(name or "无名侠客", "散人")
    weather.start_first_day_guide(player)
    return player


def show_first_entry_guide(player):
    """保留旧调用兼容；新手信息改由场景、接引人和公告栏承载，不再强制弹窗。"""
    return


def make_prompt(player, status_panel=None):
    """正常游戏显示简短提示符；状态面板临时显示对应导航层级。"""
    if status_panel == "main":
        return "状态面板> "
    if status_panel in {"sect", "reputation", "combat", "growth", "endgame"}:
        title = {"sect": "门派", "reputation": "江湖声名", "combat": "战斗属性", "growth": "成长倾向", "endgame": "终局目标"}[status_panel]
        return f"状态面板/{title}> "
    return "> "


def handle_color_command(args=None):
    """查看或切换终端颜色；设置只影响本次运行，不写入存档。"""
    raw = " ".join(args or []).strip().lower()
    labels = {"auto": "自动", "on": "开启", "off": "关闭"}
    mapping = {
        "开": "on", "开启": "on", "on": "on",
        "关": "off", "关闭": "off", "off": "off",
        "自动": "auto", "auto": "auto",
    }
    if raw in mapping:
        mode = set_color_mode(mapping[raw])
        if mode == "auto":
            state = "开启" if colors_enabled() else "关闭"
            print(f"颜色已设为自动：当前终端{state}颜色。")
        else:
            print(f"颜色已{labels[mode]}。")
        return
    if raw not in ("", "状态", "status"):
        print("用法：颜色 / 颜色 开 / 颜色 关 / 颜色 自动")
        return
    effective = "开启" if colors_enabled() else "关闭"
    print(f"颜色模式：{labels[get_color_mode()]}（当前输出：{effective}）。")
    print("用法：颜色 开 / 颜色 关 / 颜色 自动；重定向日志与非交互终端会自动关闭颜色。")


def announce_pending_caravan_arrivals(player):
    """统一输出外部世界局势公告与商队到场消息。"""
    variables = getattr(player, "world_state", {}).get("variables", {})
    crisis_news = variables.get("pending_world_crisis_announcements", []) if isinstance(variables, dict) else []
    if isinstance(crisis_news, list) and crisis_news:
        for message in crisis_news:
            if isinstance(message, str) and message.strip():
                print(f"\n{Color.BRIGHT_YELLOW}{message.strip()}{Color.RESET}")
        variables["pending_world_crisis_announcements"] = []
    economy = getattr(player, "economy_state", {})
    if not isinstance(economy, dict):
        return
    events = economy.get("events", {})
    if not isinstance(events, dict):
        return
    pending = events.get("pending_world_announcements", [])
    if not isinstance(pending, list) or not pending:
        return
    # 兼容旧存档：只展示简洁的商旅消息，过滤旧版本重复的世界公告与江湖传闻。
    shown = set()
    for message in pending:
        if not isinstance(message, str) or not message.strip():
            continue
        message = message.strip()
        if not message.startswith("【商旅消息】") or message in shown:
            continue
        shown.add(message)
        print(f"\n{Color.BRIGHT_YELLOW}{message}{Color.RESET}")
    events["pending_world_announcements"] = []


def _advance_world_after_action(player, steps=1, include_traffic=False):
    """动作结算成功后再推进世界，并统一播报人物移动与商队到场。"""
    steps = int(steps)
    try:
        if steps <= 0:
            return []
        player.tick_quest_clock(steps)
        messages = announce_pending_npc_movement(player, include_traffic=include_traffic)
        announce_pending_caravan_arrivals(player)
        return messages
    finally:
        # 延迟动作里的自动存档应在时钟推进后落盘，保存世界状态与时钟一致。
        player.flush_deferred_save()


def announce_pending_npc_movement(player, blocked=False, include_traffic=False):
    """统一输出世界主动动态（NPC 移动、天色变化、场景声响），不重绘场景。"""
    return world_ambience.announce(player, blocked=blocked, include_traffic=include_traffic)


def show_caravan_status(player):
    """展示商队实际到场状态、停留时间与下一次广场日程。"""
    from economy import EconomyManager
    manager = EconomyManager(getattr(player, "economy_state", {}))
    manager.real_time_regen = True
    state = manager.state
    rooms = getattr(engine, "ROOMS", {})
    events = state.events if isinstance(state.events, dict) else {}
    active = events.get("active_caravans", {})
    if not isinstance(active, dict):
        active = {}
    here = []
    for entry in active.values():
        if not isinstance(entry, dict) or entry.get("room") != getattr(player, "location", None):
            continue
        until_tick = _int_for_display(entry.get("until_tick", -1), -1)
        # 与场景人物列表、交易入口使用同一有效期边界：until_tick <= tick 即已离场。
        if until_tick <= state.tick:
            continue
        remaining = until_tick - state.tick
        here.append((str(entry.get("name", "商队")), remaining))
    print("\n【商队与商路动态】")
    if here:
        for name, remaining in here:
            print(f"  {name}正在此地停留，预计还停留 {remaining} 个世界时刻。")
    else:
        print("  当前所在地点没有正在停留的商队。")
    # Alpha103：状态面板读取真实的全局商旅日程，不再把旧版每支商队的独立间隔误报为预计到场时间。
    schedule = events.get("caravan_global_schedule", {})
    if not isinstance(schedule, dict):
        schedule = {}
    next_tick = _int_for_display(schedule.get("next_tick", -1), -1)
    if next_tick >= 0:
        remaining = max(0, next_tick - state.tick)
        if remaining == 0:
            print("  下一支商队已到预定时刻，待世界推进处理到场。")
        else:
            print(f"  下一支商队预计还需 {remaining} 个世界时刻到场。")
        last_room = str(schedule.get("last_room", ""))
        if last_room == "village_square":
            print("  上次停靠：村中广场；下次将优先轮换至另一处广场。")
        elif last_room == "guiyun_central_square":
            print("  上次停靠：天衡广场；下次将优先轮换至另一处广场。")
        else:
            print("  商队统一在村中广场与天衡广场之间安排停靠。")
        last_caravan = str(schedule.get("last_caravan", "")).strip()
        if last_caravan:
            print(f"  最近到场：{last_caravan}。")
    else:
        print("  全局商旅日程尚未建立；世界推进后会先经历一段安静期，再安排商队到场。")
    print("  村中广场与天衡广场共用商旅日程，不会分别独立刷新。")
    print("  提示：世界时刻随游戏指令推进；商队到场时会发布世界公告。")


def _int_for_display(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)



def _residence_invites(player):
    variables = player.world_state.setdefault("variables", {})
    invites = variables.setdefault("residence_invites", {})
    if not isinstance(invites, dict):
        invites = {}
        variables["residence_invites"] = invites
    return invites


def handle_knock(player, args):
    """敲击当前场景相邻的私人住宅；受信任的主人可发出本次访问邀请。"""
    room = engine.ROOMS.get(player.location, {})
    candidates = []
    for direction, target in (room.get("exits", {}) or {}).items():
        dest = engine.ROOMS.get(target, {})
        access = dest.get("residence", {}) if isinstance(dest, dict) else {}
        if access.get("private"):
            owner = access.get("owner")
            if not args or not owner or any(str(a) in (owner, dest.get("name")) for a in args):
                candidates.append((target, dest, access, owner))
    if not candidates:
        print("附近没有需要敲门的私人院落。请站在院门外使用：敲门 或 敲门 <主人姓名>。")
        return
    if len(candidates) > 1 and not args:
        print("附近有多户人家，请指定主人姓名：" + "、".join(x[3] or x[1].get("name", "住户") for x in candidates))
        return
    target, dest, access, owner = candidates[0]
    if not owner:
        print("院内空置，暂时无人应门。")
        return
    relation = player.get_relation(owner) if hasattr(player, "get_relation") else 0
    invites = _residence_invites(player)
    # 住宅主人必须实际在院内才能应门；优先读取日程刷新后的世界位置。
    owner_location = player.get_npc_location(owner) if hasattr(player, "get_npc_location") else None
    if owner_location != target:
        invites.pop(target, None)
        print(f"你敲了敲【{dest.get('name', '院门')}】，院内没有回应。看来{owner}此刻不在家，改日再来吧。")
        return
    if relation >= int(access.get("trust_required", 20)):
        invites[target] = True
        print(f"你敲了敲【{dest.get('name', '院门')}】。{owner}认得你，答应你进院一叙。现在可以输入对应方向进入。")
    elif relation >= 10:
        invites[target] = True
        print(f"你敲门说明来意，{owner}隔着院门与你说了几句话，暂时允许你入内。现在可以输入对应方向进入。")
    else:
        print(f"你敲了敲【{dest.get('name', '院门')}】，院内传来回应：‘若有要事，请先到外面说明来意。’目前你与{owner}还不够熟络。")


def main():
    player = None
    command_history = []
    pending_commands = []
    help_navigation_state = None
    status_panel = None
    try:
        clear_screen()
        print(f"{Color.BRIGHT_YELLOW}==================================================")
        print("                孤 侠 初 入 江 湖                 ")
        print(f"=================================================={Color.RESET}")

        if os.path.exists(SAVE_PATH):
            c = input("检测到已有本地存档，是否载入旧进度？(y/n)：").strip().lower()
            if c in ("y", "yes", ""):
                player = Player.load_from_file()

        if not player:
            name = input("\n敢问少侠尊姓大名：").strip() or "无名侠客"
            player = create_new_player(name)
            clear_statuses()
            player.save_to_file()

        clear_screen()
        player.mark_visited(player.location)
        # 新手说明由场景描述、接引人和公告栏提供，不再强制弹出教学框。
        look(player, show_guidance=False)

        while True:
            curr_room = engine.ROOMS.get(player.location, {})
            # 上一轮若因失败分支未走到延迟存档收尾，在这里清理遗留的存档请求。
            player.flush_deferred_save()
            if pending_commands:
                raw_in = pending_commands.pop(0)
            else:
                raw_in = read_command(make_prompt(player, status_panel), command_history).strip()
            if status_panel is not None:
                # 面板期间输入只由面板导航消费；不解析别名/普通命令、不推进世界时间。
                if not raw_in:
                    print("请输入有效序号，或输入 0 关闭面板。")
                    continue
                status_panel = handle_status_panel_input(raw_in, player, status_panel)
                continue
            if not raw_in:
                continue
            raw_in = resolve_help_menu_input(raw_in, help_navigation_state)
            raw_in = expand_alias(raw_in, player)
            # “别名 名称 = 南;南;西”本身包含分号，不应被拆成执行链。
            first_word = raw_in.split(None, 1)[0] if raw_in.split(None, 1) else ""
            alias_management = first_word in {"别名", "alias", "删除别名", "取消别名", "unalias"}
            chain = [raw_in] if alias_management else split_command_chain(raw_in)
            if len(chain) > 1:
                if len([part for part in raw_in.replace("；", ";").split(";") if part.strip()]) > MAX_COMMAND_CHAIN:
                    print(f"连续指令最多执行 {MAX_COMMAND_CHAIN} 条，超出的部分已忽略。")
                pending_commands[0:0] = chain[1:]
            raw_in = chain[0]
            if raw_in and (not command_history or command_history[-1] != raw_in):
                command_history.append(raw_in)
                if len(command_history) > 50:
                    del command_history[:-50]
            cmd, args = parse_command(raw_in)

            if not cmd: continue
            # 独立“接受委托”不是接取入口；识别后给出唯一正确的 NPC 对话格式，避免误报“没有找到命令”。
            if _is_direct_quest_accept_command(cmd, args):
                print("任务不能通过独立指令领取。请前往发布委托的 NPC 处，使用：交谈 人物名称 接受委托 任务名称。")
                continue
            if not command_will_be_handled(cmd, curr_room):
                # 普通指令不应继续沿用上一页帮助菜单的数字上下文。
                if cmd != "help":
                    help_navigation_state = None
                suggestions = command_suggestions(raw_in)
                print(f"{Color.RED}没有找到命令：{raw_in}{Color.RESET}")
                if suggestions:
                    print("你是不是想输入：" + "、".join(suggestions))
                print("输入“帮助”查看全部指令，输入“帮助 主题”查看专题。")
                continue
            if cmd != "help":
                help_navigation_state = None
            # 交谈先读取当前房间人物并完成对话，再推进时钟；否则 NPC 可能在命令执行前被日程/自主行动移走。
            # 可判定失败的动作延后到处理器返回后再计时；被堵出口先预检，失败移动不耗时。
            deferred_tick = {
                "buy", "sell", "travel", "forge", "attack", "kill",
                "wield", "wear", "equip", "use", "unequip",
                "inn_stay", "inn_meal", "inn_tea", "inn_rumor", "wait",
                # 任务变更须在处理器按行动时的时钟判定后再计时：先 Tick 会让
                # 限时任务提前失败，也可能让委托人在交付前按日程离场。
                "quests", "jiequ", "jiaofu", "xuanze", "fangqi", "abandon",
            }
            blocked_move = bool(movement_block_reason(player, curr_room, cmd))
            if cmd in deferred_tick:
                # 处理器成功时通常自行自动存档；延迟到动作后的 Tick 完成再真正写盘。
                player.begin_deferred_save()
            if command_advances_world(cmd, args) and cmd not in deferred_tick and not blocked_move:
                # 确定性失败不影响世界：预检命中时保留处理器提示，但不推进时钟。
                if not preflight_guaranteed_failure(player, cmd, args, curr_room):
                    player.tick_quest_clock(1)
                    announce_pending_npc_movement(player)
                    announce_pending_caravan_arrivals(player)

            if cmd == "quit":
                player.save_to_file()
                print("少侠保重，后会有期！")
                break
            elif cmd == "save":
                player.save_to_file()
            elif cmd == "load":
                loaded = Player.load_from_file()
                if loaded:
                    player = loaded
                    look(player)
            elif cmd == "color":
                handle_color_command(args)
            elif cmd == "help":
                # 编号路径可能包含两个数字，帮助主题必须完整保留。
                show_help(" ".join(args) if args else None, player)
                help_navigation_state = next_help_navigation_state(cmd, args)
            elif cmd == "encyclopedia":
                show_encyclopedia(args[0] if args else None)
            elif cmd == "advice":
                show_context_advice(player)
            elif cmd == "alias":
                handle_alias_command(player, args)
            elif cmd == "unalias":
                handle_unalias_command(player, args)
            elif cmd == "history":
                show_command_history(command_history)
            elif cmd == "history_up":
                if command_history:
                    print(f"上一条：{command_history[-2] if len(command_history) > 1 else command_history[-1]}")
                else:
                    print("暂无命令历史。")
            elif cmd == "history_down":
                print("下一条：当前没有可预览的命令；可用 ↑/↓ 浏览输入历史。")
            elif cmd == "travel":
                from travel_system import handle_travel
                travel_ok = handle_travel(player, args)
                if command_advances_world(cmd, args) and travel_ok is not False:
                    _advance_world_after_action(player)
            elif cmd == "map":
                show_map(player)
            elif cmd == "reload":
                reload_game_data()
                look(player)
            elif cmd == "look":
                look(player, args)
            elif cmd == "status":
                # 打开状态面板时丢弃同一条分号指令链的剩余部分，避免关闭后延迟执行。
                pending_commands.clear()
                status_panel = "main"
                show_status(player, "main")
            elif cmd == "profession":
                show_professions(player)
            elif cmd == "attributes":
                handle_attributes(player, args)
            elif cmd == "build":
                show_build(player)
            elif cmd == "relations":
                handle_relations(player, args)
            elif cmd == "sect":
                handle_sect(player, args)
            elif cmd == "sect_join":
                handle_sect(player, ["join"] + args)
            elif cmd == "factions":
                handle_factions(player, args)
            elif cmd == "conflicts":
                handle_faction_conflicts(player, args)
            elif cmd == "region":
                handle_region_ecology(player, args)
            elif cmd == "security_governance":
                handle_security_governance(player, args)
            elif cmd == "influence":
                handle_player_influence(player, args)
            elif cmd == "skills":
                handle_skills(player, args)
            elif cmd == "information":
                handle_information(player, args)
            elif cmd == "caravan":
                show_caravan_status(player)
            elif cmd == "notice_board":
                handle_notice_board(player, args)
            elif cmd == "memory":
                handle_information(player, ["memory"] + args)
            elif cmd == "npc_actions":
                handle_npc_actions(player, args)
            elif cmd == "world_activity":
                handle_world_activity(player, args)
            elif cmd == "business_rumor":
                handle_local_business_rumor(player)
            elif cmd == "explore":
                handle_explore(player)
            elif cmd == "wait":
                # 停留只推进一个时辰：先取本轮动态（含车马过客），无动态时再给一句动作反馈。
                announced = _advance_world_after_action(player, include_traffic=True)
                if not announced:
                    print(world_ambience.wait_feedback(player))
            elif cmd == "events":
                handle_world_events(player, args)
            elif cmd == "inventory":
                show_inventory(player)
            elif cmd == "talk":
                # 同场景交谈属于局部交互：只输出 NPC 对话及必要的世界动态，绝不调用 look() 重绘场景。
                # 场景整段描述仅由启动/进入新场景/读档重载/玩家主动查看等明确入口触发。
                # 交谈内可能接受/交付任务并自动存档；同样延迟到交谈后计时完成再落盘。
                player.begin_deferred_save()
                talk_result = handle_talk_and_ask(player, args)
                if talk_result is not False:
                    try:
                        player.tick_quest_clock(1)
                        announce_pending_npc_movement(player)
                        announce_pending_caravan_arrivals(player)
                    finally:
                        player.flush_deferred_save()
                else:
                    player.flush_deferred_save()
            elif cmd == "knock":
                handle_knock(player, args)
            elif cmd in ("quests", "jiequ", "jiaofu", "xuanze", "fangqi", "abandon"):
                quest_ok = handle_quest(player, cmd, args)
                if command_advances_world(cmd, args) and quest_ok is not False:
                    _advance_world_after_action(player)
            elif cmd in ("inn_stay", "inn_meal", "inn_tea", "inn_rumor"):
                service_action = {"inn_stay": "住店", "inn_meal": "吃饭", "inn_tea": "喝茶", "inn_rumor": "听消息"}[cmd]
                service_result = handle_inn_service(player, service_action, args)
                if cmd == "inn_stay":
                    _advance_world_after_action(
                        player, service_result if isinstance(service_result, int) and service_result > 0 else 0
                    )
                elif service_result is not False:
                    _advance_world_after_action(player)
            elif cmd in ("shop", "list", "buy", "sell"):
                trade_ok = handle_trading(player, cmd, args)
                if command_advances_world(cmd, args) and trade_ok is not False:
                    _advance_world_after_action(player)
            elif cmd in ("wield", "wear", "equip", "use", "compare", "unequip", "equipment"):
                item_ok = handle_equipment_and_items(player, cmd, args)
                if command_advances_world(cmd, args) and item_ok is not False:
                    _advance_world_after_action(player)
            elif cmd == "kill":
                attack_ok = handle_attack(player, args)
                if attack_ok is not False:
                    _advance_world_after_action(player)
            elif cmd == "heal":
                is_temple = (player.location == "temple")
                bonus = 2 if is_temple else 1
                rec_hp = 30 * bonus
                rec_mp = 20 * bonus
                hp_before, mp_before = player.hp, player.mp
                player.hp = min(player.max_hp, player.hp + rec_hp)
                player.mp = min(player.max_mp, player.mp + rec_mp)
                gained_hp = player.hp - hp_before
                gained_mp = player.mp - mp_before
                if is_temple:
                    clear_statuses()
                    print(f"{Color.BRIGHT_GREEN}古庙石佛前盘膝打坐，气血恢复 {gained_hp} 点，内力恢复 {gained_mp} 点，一身病邪异状皆被驱散！{Color.RESET}")
                else:
                    print(f"{Color.GREEN}盘膝打坐调息，恢复了 {gained_hp} 点气血与 {gained_mp} 点内力！{Color.RESET}")
            elif cmd == "mine":
                from economy import EconomyManager, TradeService
                manager = EconomyManager(getattr(player, "economy_state", {}))
                manager.real_time_regen = True
                _apply_player_world_resource_effects(manager, player)
                free_slots = TradeService.inventory_slots_free(player)
                if free_slots <= 0:
                    for line in format_action_feedback("采矿", False, "行囊已满，无法继续开采。", next_step="先整理或出售一些物品，再回来采矿。"):
                        print(line)
                else:
                    tool_bonus = int(_resource_tool_bonus(player, "mine", "yield_bonus"))
                    resource_cfg = manager.resources.get(player.location, {})
                    if tool_bonus and isinstance(resource_cfg, dict):
                        resource_cfg["yield_max"] = max(1, int(resource_cfg.get("yield_max", 3))) + tool_bonus
                    ok, result = manager.mine(player.location, min(3 + tool_bonus, free_slots), max_quantity=free_slots)
                    player.economy_state = manager.export_state()
                    if ok:
                        item_name, amount = result
                        growth = manager.record_profession_action("mine", amount)
                        player.economy_state = manager.export_state()
                        add_inventory_items(player, item_name, amount, announce=False)
                        for _ in range(amount):
                            player.update_quest_progress(item_name, event_type="collect")
                        gain_line = format_item_change(item_name, amount, player.inventory.count(item_name), action="获得")
                        for line in format_action_feedback("采矿", True, gain_line):
                            print(line)
                        print(_resource_result_status(manager, player.location))
                        if growth and growth.get("leveled_up"):
                            print(f"【采矿】熟练提升至等级 {growth['level']}！输入“职业”查看成长。")
                        print("进度尚未自动保存；需要保留本次变化时，请输入“保存”存档。")
                    else:
                        print(result)
                        if "耗尽" in str(result):
                            cfg = manager.resources.get(player.location, {})
                            _print_resource_route_suggestions(player, manager, "mine", cfg.get("item", "铁矿石") if isinstance(cfg, dict) else "铁矿石")
            elif cmd == "chop":
                from economy import EconomyManager, TradeService
                manager = EconomyManager(getattr(player, "economy_state", {}))
                manager.real_time_regen = True
                _apply_player_world_resource_effects(manager, player)
                free_slots = TradeService.inventory_slots_free(player)
                if free_slots <= 0:
                    for line in format_action_feedback("伐木", False, "行囊已满，无法继续伐木。", next_step="先整理或出售一些物品，再回来伐木。"):
                        print(line)
                else:
                    tool_bonus = int(_resource_tool_bonus(player, "chop", "yield_bonus"))
                    resource_cfg = manager.resources.get(player.location, {})
                    if tool_bonus and isinstance(resource_cfg, dict):
                        resource_cfg["yield_max"] = max(1, int(resource_cfg.get("yield_max", 3))) + tool_bonus
                    ok, result = manager.chop(player.location, min(3 + tool_bonus, free_slots), max_quantity=free_slots)
                    player.economy_state = manager.export_state()
                    if ok:
                        item_name, amount = result
                        growth = manager.record_profession_action("chop", amount)
                        player.economy_state = manager.export_state()
                        add_inventory_items(player, item_name, amount, announce=False)
                        for _ in range(amount):
                            player.update_quest_progress(item_name, event_type="collect")
                        gain_line = format_item_change(item_name, amount, player.inventory.count(item_name), action="获得")
                        for line in format_action_feedback("伐木", True, gain_line):
                            print(line)
                        print(_resource_result_status(manager, player.location))
                        if growth and growth.get("leveled_up"):
                            print(f"【伐木】熟练提升至等级 {growth['level']}！输入“职业”查看成长。")
                        print("进度尚未自动保存；需要保留本次变化时，请输入“保存”存档。")
                    else:
                        print(result)
                        if "耗尽" in str(result):
                            cfg = manager.resources.get(player.location, {})
                            _print_resource_route_suggestions(player, manager, "chop", cfg.get("item", "木材") if isinstance(cfg, dict) else "木材")
            elif cmd == "search":
                forage = curr_room.get("forage", {})
                resource_cfg = getattr(engine, "ROOMS", {}).get(player.location, {})
                economy_cfg = getattr(player, "economy_state", {})
                from economy import EconomyManager
                resource_manager = EconomyManager(economy_cfg)
                resource_manager.real_time_regen = True
                _apply_player_world_resource_effects(resource_manager, player)
                configured = resource_manager.resources.get(player.location, {})
                if isinstance(forage, dict) and forage and isinstance(configured, dict) and configured.get("action") == "gather":
                    row = resource_manager.state.resources.get(player.location, {})
                    remaining = int(row.get("remaining", configured.get("capacity", 0))) if isinstance(row, dict) else int(configured.get("capacity", 0))
                    if remaining <= 0:
                        print(f"这里的{configured.get('item', '资源')}已经采尽，暂时无法继续采集。")
                    else:
                        player.set_flag(f"resource_discovered:{player.location}", True)
                        print(f"你仔细查看了周围，发现这里可以采集【{configured.get('item', '资源')}】。输入“采集”即可实际获取；搜索本身不会消耗资源。")
                elif "forage" in curr_room:
                    print("你仔细搜索了一番，没有发现可采集的资源。若要调查隐藏线索，请使用“探索”。")
                else:
                    print("此地没有可供搜索发现的采集资源；可以查看场景提示，或使用“探索”调查线索。")
            elif cmd == "collect":
                if "forage" in curr_room:
                    from economy import EconomyManager, TradeService
                    if not player.get_flag(f"resource_discovered:{player.location}", False):
                        print("你还没有确认这里的资源。先输入“搜索”发现资源，再输入“采集”获取。")
                        continue
                    found = False
                    exhausted_items = []
                    manager = EconomyManager(getattr(player, "economy_state", {}))
                    manager.real_time_regen = True
                    _apply_player_world_resource_effects(manager, player)
                    # 先检查当前场景资源储量，再进行随机搜寻；资源耗尽时明确提示换地点，
                    # 避免玩家因为随机失败提示而误以为这里仍有无限资源。
                    for item, chance in curr_room["forage"].items():
                        resource_cfg = manager.resources.get(player.location, {})
                        if not (isinstance(resource_cfg, dict) and resource_cfg.get("action") == "gather" and str(resource_cfg.get("item")) == str(item)):
                            continue
                        resource_row = manager.state.resources.get(player.location, {})
                        if not isinstance(resource_row, dict):
                            resource_row = {"remaining": resource_cfg.get("capacity", 0), "last_tick": manager.state.tick}
                        remaining = max(0, int(resource_row.get("remaining", resource_cfg.get("capacity", 0)) or 0))
                        if remaining <= 0:
                            exhausted_items.append(str(item))
                            continue
                        # 采药小锄提升搜寻成功率；不改变资源储量、掉落物或存档结构。
                        chance_bonus = _resource_tool_bonus(player, "gather", "chance_bonus")
                        if chance_bonus:
                            chance = min(0.95, float(chance) + chance_bonus)
                        if random.random() >= chance:
                            continue
                        if not TradeService.can_receive_items(player, 1):
                            for line in format_action_feedback("采集", False, "行囊已满，无法继续采集。", next_step="先整理或出售一些物品，再回来采集。"):
                                print(line)
                            break
                        ok, result = manager.gather(player.location, 1, max_quantity=TradeService.inventory_slots_free(player))
                        player.economy_state = manager.export_state()
                        if not ok:
                            if "耗尽" in str(result):
                                exhausted_items.append(str(item))
                            else:
                                print(result)
                            continue
                        item_name, amount = result
                        growth = manager.record_profession_action("gather", amount)
                        player.economy_state = manager.export_state()
                        add_inventory_items(player, item_name, amount, announce=False)
                        for _ in range(amount):
                            player.update_quest_progress(item_name, event_type="collect")
                        gain_line = format_item_change(item_name, amount, player.inventory.count(item_name), action="获得")
                        feedback = format_action_feedback("采集", True, gain_line)
                        print(f"{Color.GREEN}{feedback[0]}{Color.RESET}")
                        print(_resource_result_status(manager, player.location))
                        if growth and growth.get("leveled_up"):
                            print(f"【采集】熟练提升至等级 {growth['level']}！输入“职业”查看成长。")
                        found = True
                    if not found and exhausted_items:
                        print(f"{Color.YELLOW}{gather_search_failure_text(exhausted_items)}{Color.RESET}")
                        # 三类资源共用同一套地图路线推荐，避免提示规则不一致。
                        for exhausted_item in dict.fromkeys(exhausted_items):
                            _print_resource_route_suggestions(player, manager, "gather", exhausted_item)
                    elif not found:
                        print(gather_search_failure_text([]))
                else: print("此地没有可采摘搜寻的资源。")
            elif cmd == "forge":
                forge_ok = handle_forge(player, args)
                if command_advances_world(cmd, args) and forge_ok is not False:
                    _advance_world_after_action(player)
            elif cmd == "run":
                print("当前不在战斗中。若战斗中需要逃跑，请选择“4. 尝试逃跑”。")
            else:
                # P2.49：方向别名统一映射到房间实际使用的中文出口键，
                # 修复 n/s/e/w、north/south/east/west、拼音方向在实际移动阶段无法生效的问题。
                direction_exit = {"n": "北", "s": "南", "e": "东", "w": "西", "u": "上", "d": "下"}.get(cmd, cmd)
                destination, blocked_message = resolve_room_exit(player, curr_room, direction_exit)
                if destination is None:
                    if blocked_message:
                        print(blocked_message)
                        continue
                    if cmd in ("u", "d"):
                        print(movement_block_reason(player, curr_room, cmd))
                        continue
                    suggestions = command_suggestions(raw_in)
                    print(f"{Color.RED}没有找到命令：{raw_in}{Color.RESET}")
                    if suggestions:
                        print("你是不是想输入：" + "、".join(suggestions))
                    print("输入“帮助”查看全部指令，输入“帮助 主题”查看专题。")
                    continue
                destination_room = engine.ROOMS.get(destination, {})
                # 门派内院按身份开放；访客可到山门与迎客厅，不会被阻断在整个门派之外。
                from travel_system import room_access_denial
                access_denial = room_access_denial(player, destination_room if isinstance(destination_room, dict) else {})
                if access_denial:
                    print(access_denial)
                    continue
                residence = destination_room.get("residence", {}) if isinstance(destination_room, dict) else {}
                if residence.get("private"):
                    owner = residence.get("owner")
                    invited = _residence_invites(player).get(destination, False)
                    relation = player.get_relation(owner) if owner and hasattr(player, "get_relation") else 0
                    threshold = int(residence.get("trust_required", 20))
                    if not invited and relation < threshold:
                        print(f"【{destination_room.get('name', '私人院落')}】院门紧闭。请先使用‘敲门’说明来意；与主人关系达到{threshold}后也可进入。")
                        continue
                    if invited:
                        _residence_invites(player).pop(destination, None)
                player.location = destination
                player.mark_visited(player.location)
                look(player)
                trigger_entry_events(player, player.location)

                next_room = engine.ROOMS.get(player.location, {})
                zone_id = next_room.get("zone", "main")
                ecology = player.get_region_ecology(zone_id)
                security = max(0, min(100, int(ecology.get("security", 70))))
                travel = max(0, min(100, int(ecology.get("travel", 70))))
                # 安全与通行实际影响危险场景中的遭遇概率；低治安街头才可能出现惯犯。
                e_name = select_random_encounter(player, next_room, zone_id, security, travel)
                if e_name:
                    print(f"\n{Color.RED}跳出个【{e_name}】挡住去路！{Color.RESET}")
                    battle_pause(0.8)
                    combat(player, e_name)

    except KeyboardInterrupt:
        if player:
            player.save_to_file()
            print("\n游戏被手动中断，已自动为你保存当前进度。少侠后会有期！")
        else:
            print("\n游戏已退出。")


if __name__ == "__main__":
    main()
