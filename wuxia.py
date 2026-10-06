# -*- coding: utf-8 -*-
"""
孤侠初入江湖 - NPC/目标观察与地图出口全量精修版
纯命令行武侠文字冒险游戏

本次更新重点：
1. 【观察功能升级 (look <目标>)】：支持 `look <NPC/怪物/物品>`，可详细查看 NPC 外貌、怪物属性及背包物品说明。
2. 【地图与出口修复】：彻底清除黑风山道多余出口，完善副本与主世界隔离。
3. 【系统机制完备】：包含 Zone 坐标隔离、旧档平滑迁移、状态残留清理及 Ctrl+C 安全防护。
"""

import json
import os
import random
import time
import logging
import unicodedata
from copy import deepcopy
from collections import Counter, deque

if os.name == "nt":
    os.system("")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# ==================== 全局路径与版本常量 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAVE_PATH = os.path.join(DATA_DIR, "save.json")
SAVE_VERSION = 10

p_statuses_global = {}

# 旧存档房间 Key 别名映射字典
LEGACY_LOCATION_MAP = {
    "cave": "cave_entrance",
    "bandit_camp": "bandit_courtyard",
}


# ==================== ANSI 颜色代码 ====================
class Color:
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
    BRIGHT_CYAN = "\033[96m"


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


BATTLE_SPEED = 0.6


def battle_pause(seconds):
    time.sleep(seconds * BATTLE_SPEED)


# ==================== 字符显示宽度与补全函数 ====================
def get_display_width(s):
    """计算包含中文的全角字符及 Emoji(如 🚪)在终端中的真实显示宽度"""
    width = 0
    for ch in s:
        if ch == "🚪" or unicodedata.east_asian_width(ch) in ('F', 'W'):
            width += 2
        else:
            width += 1
    return width


def pad_to_width(s, target_width, align="center"):
    """按真实显示宽度精准补齐空格"""
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


def _apply_shield(statuses, raw_damage):
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
    # ------------------ 主世界 Zone: main ------------------
    "village_gate": {
        "name": "青石村口", "zone": "main",
        "desc": "一座破旧的木牌楼立在道旁，匾额上“青石村”三字被风雨侵蚀得斑驳。牌楼下靠着个打盹的守卫。往北进入村南大街，往南则是黄土官道。",
        "exits": {"北": "village_south_street", "南": "official_road"},
        "npcs": ["守卫"], "safe": True, "coord": [2, 1]
    },
    "village_south_street": {
        "name": "村南大街", "zone": "main",
        "desc": "青石板路两侧排列着矮小的民居。西侧挂着“悦来客栈”的招牌，东侧则是一家杂货铺。北边直通村中广场，南边是村口。",
        "exits": {"北": "village_square", "南": "village_gate", "西": "inn", "东": "general_shop"},
        "safe": True, "coord": [2, 2]
    },
    "inn": {
        "name": "悦来客栈", "zone": "main",
        "desc": "堂中灯油昏黄，掌柜支颐倚在柜台后拨弄算盘，小二在收拾桌椅。东边大门通往村南大街。",
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
        "desc": "这里是青石村最宽阔的集散地，中央耸立着一棵百年老榕树。西边是百草堂，东边是打铁铺，南通村南大街，北接村北街。",
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
        "desc": "炉火通红，热浪扑面。铁匠赤膊抡锤，火星四溅。（输入 forge 可强化兵刃或防具）西边通往村中广场。",
        "exits": {"西": "village_square"}, "npcs": ["铁匠"], "safe": True, "coord": [3, 3]
    },
    "village_north_street": {
        "name": "村北街", "zone": "main",
        "desc": "村北比较清静，石板路顺着坡度缓缓向上。西侧是村长住宅，正北方向是一座古庙。",
        "exits": {"北": "temple", "南": "village_square", "西": "village_head_house"}, "safe": True, "coord": [2, 4]
    },
    "village_head_house": {
        "name": "村长宅院", "zone": "main",
        "desc": "一座朴素的四合小院，青苔爬满石阶。正房里白发村长负手而立，眉宇间带着几分愁容。",
        "exits": {"东": "village_north_street"}, "npcs": ["村长"], "safe": True, "coord": [1, 4]
    },
    "temple": {
        "name": "古庙", "zone": "main",
        "desc": "古庙颓败，朱漆剥落。室内清幽无人，只有半截石佛立于堂中。这里是打坐恢复绝佳之地，可驱散病邪。（输入 dazuo 或 heal 打坐）",
        "exits": {"南": "village_north_street"}, "safe": True, "coord": [2, 5]
    },
    "official_road": {
        "name": "黄土官道", "zone": "main",
        "desc": "黄土官道上车辙深深，两侧野草没膝。北边回青石村，西边有一条荒僻小径通往村后荒野。（输入 search 可采集资源）",
        "exits": {"北": "village_gate", "西": "wild_fields"},
        "enemies": ["野猪"], "forage": {"草药": 0.4, "铁矿石": 0.3}, "coord": [2, 0]
    },
    "wild_fields": {
        "name": "村后荒野", "zone": "main",
        "desc": "杂草丛生，偶有野兽低吼。东边接官道，西边是一条蜿蜒入山的黑风山道。",
        "exits": {"东": "official_road", "西": "mountain_path"},
        "enemies": ["野狼", "野猪"], "forage": {"草药": 0.5, "野猪肉": 0.3}, "coord": [1, 0]
    },
    "mountain_path": {
        "name": "黑风山道", "zone": "main",
        "desc": "山道狭窄，两侧崖壁嶙峋，山风穿谷而过。东边回村后荒野，北边直抵山贼寨门。",
        "exits": {"东": "wild_fields", "北": "cave_entrance"},
        "enemies": ["毒蛇", "山贼"], "forage": {"蛇胆": 0.3}, "coord": [0, 0]
    },
    "cave_entrance": {
        "name": "山贼寨门", "zone": "main",
        "desc": "一座用粗木和兽骨扎成的寨门矗立在前，守备森严。南下为黑风山道，往北跨过寨门即踏入黑风寨内部。",
        "exits": {"南": "mountain_path", "北": "bandit_courtyard"}, "enemies": ["山贼"], "coord": [0, 1]
    },

    # ------------------ 副本 Zone: bandit_zone (黑风寨) ------------------
    "bandit_courtyard": {
        "name": "寨内演武场", "zone": "bandit_zone",
        "desc": "黑风寨前院演武场，地面夯得极实，摆放着不少兵器架和木人桩。南边通往山贼寨门，北边直通聚义厅，东边有高耸的哨塔，西边是一条幽暗的水牢狭道。",
        "exits": {"南": "cave_entrance", "北": "bandit_camp", "东": "bandit_watchtower", "西": "bandit_water_dungeon"},
        "enemies": ["山贼", "山贼头目"], "coord": [0, 0]
    },
    "bandit_watchtower": {
        "name": "山贼哨塔", "zone": "bandit_zone",
        "desc": "用圆木搭建的数丈高台，站在塔顶可俯瞰整个山寨。弓箭手居高临下戒备着。西边通往演武场。（输入 search 可搜寻守卫遗落的物资）",
        "exits": {"西": "bandit_courtyard"},
        "enemies": ["山贼弓手"], "forage": {"铁矿石": 0.5, "金创药": 0.3}, "coord": [1, 0]
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
        "desc": "黑风寨积攒多年不义之财的密室，箱笼堆叠。宝库大总管正带着精锐在此亲自把守。西边通往聚义厅。",
        "exits": {"西": "bandit_camp"},
        "enemies": ["宝库大总管", "山贼精英"], "forage": {"大还丹": 0.2, "金创药": 0.4}, "coord": [1, 1]
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
        "dialogue": ["只要你有铁矿石和银子，我就能帮你的兵刃与防具精炼加固！（输入 forge 选 1 或 2 强化）"],
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
            "quests": DEFAULT_QUESTS
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
            print(f"{Color.RED}[读取错误] {name}.json 解析失败，已采用默认数据。{Color.RESET}")
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


# ==================== 动态地图引擎 (MapEngine - Zone 坐标隔离) ====================
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

    ZONE_NAMES = {
        "main": "主世界",
        "bandit_zone": "黑风寨"
    }

    def __init__(self, rooms):
        self.rooms = rooms
        self.room_coords = {}    # room_key -> (x, y)
        self.coord_to_room = {}  # (zone, x, y) -> room_key  (带 Zone 前缀隔离)
        self.build_layout()
        self.validate()

    def build_layout(self):
        self.room_coords.clear()
        self.coord_to_room.clear()

        zones = set(r.get("zone", "main") for r in self.rooms.values())

        for z in zones:
            zone_rooms = {k: v for k, v in self.rooms.items() if v.get("zone", "main") == z}
            unpositioned = []

            for r_key, r_info in zone_rooms.items():
                if "coord" in r_info and isinstance(r_info["coord"], list) and len(r_info["coord"]) == 2:
                    coord = (r_info["coord"][0], r_info["coord"][1])
                    zone_coord = (z, coord[0], coord[1])
                    if zone_coord in self.coord_to_room:
                        logging.warning(f"[MapEngine] Zone '{z}' 坐标碰撞！【{r_key}】与【{self.coord_to_room[zone_coord]}】位于 {coord}")
                        unpositioned.append(r_key)
                    else:
                        self.room_coords[r_key] = coord
                        self.coord_to_room[zone_coord] = r_key
                else:
                    unpositioned.append(r_key)

            if unpositioned:
                self._multi_source_bfs_place(z, zone_rooms, unpositioned)

    def _find_nearest_empty(self, zone, start_coord):
        """用 BFS 寻找指定 Zone 内部最近的空闲坐标"""
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
        """Zone 隔离的多源 BFS 自动扩散布局算法"""
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

    def validate(self):
        issues = []
        for r_key, (gx, gy) in self.room_coords.items():
            r_zone = self.rooms.get(r_key, {}).get("zone", "main")
            exits = self.rooms.get(r_key, {}).get("exits", {})

            for d_name, target in exits.items():
                if target not in self.rooms: continue
                t_zone = self.rooms.get(target, {}).get("zone", "main")

                # 只校验同 Zone 内部房间的物理相对几何关系
                if r_zone == t_zone and target in self.room_coords:
                    tx, ty = self.room_coords[target]
                    dx, dy = tx - gx, ty - gy
                    v = self.DIR_VECTORS.get(d_name, (0, 0))

                    if (dx, dy) != v:
                        issues.append(
                            f"【{r_key}】--{d_name}-->【{target}】物理向量与逻辑方向不一致！"
                            f"(实际 dx={dx}, dy={dy}, 期待 {v})"
                        )

                # 互逆语义检查
                target_exits = self.rooms.get(target, {}).get("exits", {})
                opp_dir = self.OPPOSITE_DIRS.get(d_name)
                if opp_dir and target_exits.get(opp_dir) != r_key:
                    issues.append(
                        f"【{r_key}】--{d_name}-->【{target}】，但【{target}】的 {opp_dir} 出口未指向【{r_key}】"
                    )

        for i in issues:
            logging.warning(f"[MapEngine 校验] {i}")
        return issues

    def render(self, player_loc):
        """仅渲染玩家当前所在 Zone 的子地图，并为跨区域出口绘制 🚪 传送门标识"""
        curr_room = self.rooms.get(player_loc, {})
        curr_zone = curr_room.get("zone", "main")
        zone_title = self.ZONE_NAMES.get(curr_zone, curr_zone)

        # 筛选同 Zone 房间
        zone_room_coords = {
            k: v for k, v in self.room_coords.items()
            if self.rooms.get(k, {}).get("zone", "main") == curr_zone
        }

        if not zone_room_coords:
            return f"{Color.RED}当前区域 [{zone_title}] 地图数据为空！{Color.RESET}"

        xs = [c[0] for c in zone_room_coords.values()]
        ys = [c[1] for c in zone_room_coords.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        grid_width = max_x - min_x + 1
        grid_height = max_y - min_y + 1

        cell_w = 12
        canvas_rows = grid_height * 2 - 1
        canvas_cols = grid_width * cell_w

        canvas = [[" "] * canvas_cols for _ in range(canvas_rows)]

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

        # 1. 纯文本排版与跨区域传送门 (🚪) 标识识别
        target_raw_node = None
        for r_key, (x, y) in zone_room_coords.items():
            row = (max_y - y) * 2
            col = (x - min_x) * cell_w

            r_name = self.rooms.get(r_key, {}).get("name", r_key)

            # 检查是否有跨区域出口
            has_portal = False
            for t_key in self.rooms.get(r_key, {}).get("exits", {}).values():
                if self.rooms.get(t_key, {}).get("zone", "main") != curr_zone:
                    has_portal = True
                    break

            if has_portal:
                display_label = f"{r_name}🚪"
            else:
                display_label = r_name

            raw_node = f"[{pad_to_width(display_label, 8, align='center')}]"

            if r_key == player_loc:
                target_raw_node = raw_node

            put_text(row, col, raw_node)

        # 2. 绘制 Zone 内部通道连线
        for r_key, (x, y) in zone_room_coords.items():
            r_row = (max_y - y) * 2
            r_col = (x - min_x) * cell_w
            exits = self.rooms.get(r_key, {}).get("exits", {})

            for d_name, target_key in exits.items():
                if target_key not in zone_room_coords: continue
                tx, ty = zone_room_coords[target_key]

                dx = tx - x
                dy = ty - y

                if dx == 0 and abs(dy) == 1:
                    mid_row = int((max_y - (y + ty) / 2) * 2)
                    line_col = r_col + 5
                    put_text(mid_row, line_col, "│")
                elif dy == 0 and abs(dx) == 1:
                    mid_col = (min(x, tx) - min_x) * cell_w + 10
                    put_text(r_row, mid_col, "──")

        # 3. 拼接输出并在最后施加高亮
        lines = []
        lines.append(f"\n{Color.BRIGHT_CYAN}======================== 动态江湖地图 [{zone_title}] ========================{Color.RESET}")

        for r in canvas:
            line_str = "".join(r).rstrip()
            if target_raw_node and target_raw_node in line_str:
                highlighted = f"{Color.BRIGHT_RED}{Color.BOLD}{target_raw_node}{Color.RESET}"
                line_str = line_str.replace(target_raw_node, highlighted)
            lines.append(line_str)

        exits_info = []
        for dir_key, tgt_key in curr_room.get("exits", {}).items():
            t_info = self.rooms.get(tgt_key, {})
            t_name = t_info.get("name", tgt_key)
            t_zone = t_info.get("zone", "main")
            if t_zone != curr_zone:
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
    global GAME_DATA, ROOMS, NPCS, ITEMS, ENEMIES, SKILLS, QUESTS, MAP_ENGINE
    GAME_DATA = loader.load_all()
    ROOMS = GAME_DATA["rooms"]
    NPCS = GAME_DATA["npcs"]
    ITEMS = GAME_DATA["items"]
    ENEMIES = GAME_DATA["enemies"]
    SKILLS = GAME_DATA["skills"]
    QUESTS = GAME_DATA["quests"]

    MAP_ENGINE = MapEngine(ROOMS)
    print(f"{Color.BRIGHT_GREEN}[热重载完成] 游戏配置数据与动态地图引擎已同步刷新！{Color.RESET}\n")


# ==================== 玩家类与存档 ====================
class Player:
    def __init__(self, name="无名侠客", sect="散人"):
        self.name = name
        self.sect = sect
        self.level = 1
        self.exp = 0
        self.exp_to_level = 50
        self.hp = 100
        self.max_hp = 100
        self.mp = 50
        self.max_mp = 50
        self.atk = 10
        self.defense = 5
        self.gold = 50
        self.inventory = ["疗伤药", "铁矿石", "草药"]
        self.equipment = {"weapon": "木剑", "armor": "布衣"}
        self.equip_enhance = {"weapon": 0, "armor": 0}
        self.location = "village_gate"

        self.active_quests = {}
        self.completed_quests = []

        if sect == "少林":
            self.max_hp += 20; self.hp += 20; self.defense += 3
        elif sect == "武当":
            self.max_mp += 20; self.mp += 20; self.atk += 2
        elif sect == "华山":
            self.atk += 5

    def get_total_atk(self):
        w_name = self.equipment.get("weapon")
        base = ITEMS.get(w_name, {}).get("atk", 0) if w_name else 0
        enhance_bonus = self.equip_enhance.get("weapon", 0) * 3
        return self.atk + base + enhance_bonus

    def get_total_defense(self):
        a_name = self.equipment.get("armor")
        base = ITEMS.get(a_name, {}).get("defense", 0) if a_name else 0
        enhance_bonus = self.equip_enhance.get("armor", 0) * 2
        return self.defense + base + enhance_bonus

    def gain_exp(self, amount):
        self.exp += amount
        print(f"{Color.GREEN}获得了 {amount} 点经验。{Color.RESET}")
        while self.exp >= self.exp_to_level:
            self.exp -= self.exp_to_level
            self.level += 1
            self.max_hp += 15; self.hp = self.max_hp
            self.max_mp += 10; self.mp = self.max_mp
            self.atk += 3; self.defense += 2
            self.exp_to_level = int(self.exp_to_level * 1.5)
            print(f"\n{Color.BRIGHT_YELLOW}【功力大进！】等级提升到了 {self.level} 级！{Color.RESET}")

    def update_quest_progress(self, target_name):
        for q_name in list(self.active_quests.keys()):
            q_info = QUESTS.get(q_name, {})
            if q_info.get("target_name") == target_name:
                self.active_quests[q_name] += 1
                req = q_info.get("required_cnt", 1)
                curr = self.active_quests[q_name]
                print(f"{Color.BRIGHT_YELLOW}[任务更新] 【{q_name}】进度：({curr}/{req}){Color.RESET}")

    def save_to_file(self, filename=SAVE_PATH):
        save_data = {
            "version": SAVE_VERSION,
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
            "completed_quests": self.completed_quests
        }
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            print(f"{Color.BRIGHT_GREEN}[存档成功] 游戏进度已保存到 {filename}{Color.RESET}")
            return True
        except Exception as e:
            print(f"{Color.RED}[存档失败] 保存失败: {e}{Color.RESET}")
            return False

    @classmethod
    def load_from_file(cls, filename=SAVE_PATH):
        if not os.path.exists(filename):
            print(f"{Color.YELLOW}未找到存档文件 {filename}。{Color.RESET}")
            return None
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            p = cls(data.get("name", "无名侠客"), data.get("sect", "散人"))
            p.level = data.get("level", 1)
            p.exp = data.get("exp", 0)
            p.exp_to_level = data.get("exp_to_level", 50)
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

            raw_loc = data.get("location", "village_gate")
            mapped_loc = LEGACY_LOCATION_MAP.get(raw_loc, raw_loc)
            if mapped_loc not in ROOMS:
                mapped_loc = "village_gate"
            p.location = mapped_loc

            p.active_quests = data.get("active_quests", {})
            p.completed_quests = data.get("completed_quests", [])

            clear_statuses()
            print(f"{Color.BRIGHT_GREEN}[读档成功] 欢迎回来，{p.name}少侠！（存档版本 v{data.get('version', 1)}）{Color.RESET}")
            return p
        except Exception as e:
            print(f"{Color.RED}[读档失败] 文件损毁: {e}{Color.RESET}")
            return None


# ==================== 指令映射 ====================
CMD_MAP = {
    "n": "北", "s": "南", "e": "东", "w": "西",
    "north": "北", "south": "南", "east": "东", "west": "西",
    "l": "look", "i": "inventory", "st": "status",
    "h": "help", "help": "help",
    "dazuo": "heal", "heal": "heal",
    "f": "forge", "q": "quit", "rl": "reload",
    "talk": "talk", "chat": "talk", "ask": "talk", "问": "talk", "交谈": "talk", "t": "talk",
    "k": "kill", "attack": "kill", "fight": "kill",
    "flee": "run",
    "quest": "quests", "quests": "quests", "renwu": "quests",
    "jiequ": "jiequ", "jiaofu": "jiaofu",
    "buy": "buy", "sell": "sell", "wield": "wield", "wear": "wear", "use": "use",
    "m": "map", "map": "map", "ditu": "map", "地图": "map"
}


def parse_command(user_input):
    parts = user_input.strip().split()
    if not parts:
        return "", []
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    cmd = CMD_MAP.get(cmd, cmd)
    return cmd, args


def show_map(player):
    print(MAP_ENGINE.render(player.location))


# ==================== 观察环境与观察特定目标 (look / look <目标>) ====================
def look(player, args=None):
    room = ROOMS.get(player.location, ROOMS["village_gate"])

    # 1. 无参数：观察当前房间全貌
    if not args:
        print(f"\n{Color.BRIGHT_CYAN}【{room['name']}】{Color.RESET}")
        print(room["desc"])
        if room.get("exits"):
            print(f"{Color.YELLOW}出口：{', '.join(room['exits'].keys())}{Color.RESET}")
        if room.get("npcs"):
            print(f"人物：{Color.CYAN}{', '.join(room['npcs'])}{Color.RESET}")
        if room.get("enemies"):
            print(f"{Color.RED}出没的威胁：{', '.join(room['enemies'])}{Color.RESET}")
        return

    # 2. 有参数：精确查找并观察特定目标 (NPC -> 怪物 -> 物品)
    target = args[0]

    # (A) 在当前房间查找匹配的 NPC
    for npc_name in room.get("npcs", []):
        if target in npc_name or npc_name in target:
            npc_data = NPCS.get(npc_name, {})
            title = npc_data.get("title", npc_name)
            desc = npc_data.get("desc", "看起来普普通通，没什么特别的。")
            print(f"\n{Color.BRIGHT_YELLOW}【{title}】{Color.RESET}")
            print(f"{Color.CYAN}{desc}{Color.RESET}")

            # 显示该 NPC 是否出售商品或提供任务
            if "shop" in npc_data:
                print(f"{Color.GREEN}提示：可以向其购买物品（输入 shop 查看货架）。{Color.RESET}")
            if npc_data.get("quests"):
                print(f"{Color.BRIGHT_YELLOW}提示：似乎有任务相托（输入 talk {npc_name} 交谈）。{Color.RESET}")
            return

    # (B) 在当前房间查找匹配的 怪物/敌人
    for enemy_name in room.get("enemies", []):
        if target in enemy_name or enemy_name in target:
            e_data = ENEMIES.get(enemy_name, {})
            hp = e_data.get("hp", 0)
            atk = e_data.get("atk", 0)
            defense = e_data.get("defense", 0)
            print(f"\n{Color.BRIGHT_RED}【{enemy_name}】{Color.RESET}")
            print(f"眼神不善，充满敌意！属性评估：气血 {hp} | 攻击 {atk} | 防御 {defense}")
            print(f"{Color.RED}提示：输入 kill {enemy_name} 即可对其发起攻击。{Color.RESET}")
            return

    # (C) 在玩家行囊或装备中查找匹配的 物品
    all_items = player.inventory + list(player.equipment.values())
    for item_name in set(all_items):
        if item_name and (target in item_name or item_name in target):
            i_data = ITEMS.get(item_name, {})
            i_type = i_data.get("type", "普通物品")
            type_cn = {"weapon": "兵刃", "armor": "防具", "consumable": "消耗药剂", "material": "材料"}.get(i_type, i_type)
            desc = i_data.get("desc", "暂无说明。")
            price = i_data.get("price", 0)

            print(f"\n{Color.BRIGHT_GREEN}【{item_name}】({type_cn}){Color.RESET}")
            print(f"描述：{desc}")
            print(f"价值：{price} 两银子")
            return

    print(f"周围和行囊里并没有找到与【{target}】相关的目标。")


# ==================== 对话与打听 ====================
def handle_talk_and_ask(player, args):
    room = ROOMS.get(player.location, {})
    npcs_in_room = room.get("npcs", [])

    if not npcs_in_room:
        print("此地空无一人，并无可以交谈的对象。")
        return

    target_npc = npcs_in_room[0]
    topic = None

    if args:
        matched = False
        for name in npcs_in_room:
            if args[0] in name:
                target_npc = name
                matched = True
                break

        if matched and len(args) > 1:
            topic = args[1]
        elif not matched:
            topic = args[0]

    npc_data = NPCS.get(target_npc, {})
    print(f"\n{Color.BRIGHT_YELLOW}【{npc_data.get('title', target_npc)}】{Color.RESET}")

    if topic:
        info_dict = npc_data.get("info", {})
        matched_info = None
        for key_phrase, val_text in info_dict.items():
            if topic in key_phrase or key_phrase in topic:
                matched_info = val_text
                break

        if matched_info:
            print(f"{target_npc} 压低声音回答说：“{Color.YELLOW}{matched_info}{Color.RESET}”")
        else:
            print(f"{target_npc} 摇了摇头：“关于‘{topic}’，老夫并不知道什么信息。”")
        return

    print(f"{Color.CYAN}{npc_data.get('desc', '一言不发。')}{Color.RESET}")
    dialogues = npc_data.get("dialogue", ["……"])
    line = random.choice(dialogues) if isinstance(dialogues, list) else dialogues
    print(f"\n{target_npc} 说道：“{Color.GREEN}{line}{Color.RESET}”")

    available_q = npc_data.get("quests", [])
    for q_name in available_q:
        if q_name in player.completed_quests:
            continue
        q_info = QUESTS.get(q_name, {})
        if q_name not in player.active_quests:
            print(f"\n{Color.BRIGHT_YELLOW}提示：{target_npc} 似乎有任务相托！输入 jiequ {q_name} 即可接取。{Color.RESET}")
        else:
            curr = player.active_quests[q_name]
            req = q_info.get("required_cnt", 1)
            if curr >= req:
                print(f"\n{Color.BRIGHT_GREEN}提示：你已完成【{q_name}】！输入 jiaofu {q_name} 交付任务。{Color.RESET}")


# ==================== 任务系统 ====================
def handle_quest(player, cmd, args):
    if cmd in ("quests", "renwu"):
        print(f"\n{Color.CYAN}========== 当前任务列表 =========={Color.RESET}")
        if not player.active_quests:
            print("目前没有正在进行中的任务。")
        for q_name, progress in player.active_quests.items():
            q_info = QUESTS.get(q_name, {})
            req = q_info.get("required_cnt", 1)
            print(f"- {Color.YELLOW}{q_name}{Color.RESET}：({progress}/{req}) - {q_info.get('desc', '')}")
        print(f"{Color.CYAN}----------------------------------{Color.RESET}")

    elif cmd == "jiequ":
        if not args:
            print("请输入要接取的任务名称（格式：jiequ <任务名>）。")
            return
        q_name = args[0]
        if q_name not in QUESTS:
            print(f"不存在名为【{q_name}】的任务。")
            return
        if q_name in player.active_quests:
            print("你已经接取了该任务！")
            return
        if q_name in player.completed_quests:
            print("该任务你已经完成过了！")
            return
        player.active_quests[q_name] = 0
        print(f"{Color.BRIGHT_GREEN}成功接取任务：【{q_name}】！{Color.RESET}")

    elif cmd == "jiaofu":
        if not args:
            print("请输入要交付的任务名称（格式：jiaofu <任务名>）。")
            return
        q_name = args[0]
        if q_name not in player.active_quests:
            print("你未接取该任务！")
            return
        q_info = QUESTS.get(q_name, {})
        req = q_info.get("required_cnt", 1)
        if player.active_quests[q_name] < req:
            print(f"{Color.RED}任务目标未达成，无法交付！{Color.RESET}")
            return

        del player.active_quests[q_name]
        player.completed_quests.append(q_name)
        reward = q_info.get("reward", {})
        print(f"\n{Color.BRIGHT_YELLOW}🎉 恭喜完成任务【{q_name}】！获得奖励：{Color.RESET}")
        if "exp" in reward: player.gain_exp(reward["exp"])
        if "gold" in reward:
            player.gold += reward["gold"]
            print(f"银两 +{reward['gold']}")
        if "item" in reward:
            player.inventory.append(reward["item"])
            print(f"获得了物品：【{reward['item']}】！")
        player.save_to_file()


# ==================== 消耗品应用 ====================
def apply_consumable(player, item_name):
    info = ITEMS.get(item_name, {})
    if info.get("type") != "consumable":
        print(f"【{item_name}】并非可直接使用的消耗道具。")
        return False

    player.inventory.remove(item_name)
    eff = info.get("effect", {})

    if "hp" in eff:
        actual_gain = min(player.max_hp, player.hp + eff["hp"]) - player.hp
        player.hp += actual_gain
        print(f"{Color.GREEN}服下了【{item_name}】，实际恢复了 {actual_gain} 点气血！{Color.RESET}")
    if "mp" in eff:
        actual_gain = min(player.max_mp, player.mp + eff["mp"]) - player.mp
        player.mp += actual_gain
        print(f"{Color.BLUE}服下了【{item_name}】，实际恢复了 {actual_gain} 点内力！{Color.RESET}")
    if "status" in eff:
        st = eff["status"]
        st_name = st.get("name")
        if st_name:
            cn_name = STATUS_EFFECTS.get(st_name, {}).get("name", st_name)
            add_status(p_statuses_global, st_name, st.get("turns", 1), st.get("value", 0))
            print(f"{Color.CYAN}服下了【{item_name}】，凝聚起了【{cn_name}】效果！{Color.RESET}")
    return True


# ==================== 交易与装备管理 ====================
def handle_trading(player, cmd, args):
    room = ROOMS.get(player.location, {})
    npcs_in_room = room.get("npcs", [])

    trader_npc = None
    for n in npcs_in_room:
        if NPCS.get(n, {}).get("type") == "trader" or "shop" in NPCS.get(n, {}):
            trader_npc = n
            break

    if not trader_npc:
        print("此处没有可以交易的商贾或店家。")
        return

    shop_items = NPCS[trader_npc].get("shop", [])

    if cmd in ("shop", "list"):
        print(f"\n{Color.YELLOW}======== {trader_npc} 的店铺货架 ========{Color.RESET}")
        for idx, item in enumerate(shop_items, 1):
            info = ITEMS.get(item, {})
            print(f"  {idx}. {item} - {info.get('price', 0)} 两银子 ({info.get('desc', '')})")
        print(f"手头银两：{player.gold} 两")
    elif cmd == "buy":
        if not args:
            print("请指定要购买的物品名称（如 buy 金创药）。")
            return
        item_name = args[0]
        matching = [i for i in shop_items if item_name in i]
        if not matching:
            print(f"店家表示这里并不出售【{item_name}】。")
            return
        target = matching[0]
        price = ITEMS.get(target, {}).get("price", 0)
        if player.gold >= price:
            player.gold -= price
            player.inventory.append(target)
            print(f"{Color.GREEN}花费 {price} 两银子，购买了【{target}】！{Color.RESET}")
        else:
            print(f"{Color.RED}银两不足，无法购买！{Color.RESET}")
    elif cmd == "sell":
        if not args:
            print("请指定要出售的物品名称（如 sell 野猪肉）。")
            return
        item_name = args[0]
        matching = [i for i in player.inventory if item_input in i]
        if not matching:
            print(f"你的行囊中没有【{item_name}】。")
            return
        target = matching[0]
        price = max(1, int(ITEMS.get(target, {}).get("price", 10) * 0.5))
        player.inventory.remove(target)
        player.gold += price
        print(f"{Color.GREEN}将【{target}】卖给了商家，换得 {price} 两银子！{Color.RESET}")


def handle_equipment_and_items(player, cmd, args):
    if not args:
        print(f"请指定物品名称（如 {cmd} 精铁剑）。")
        return
    item_input = args[0]

    if cmd in ("wield", "wear"):
        matching = [i for i in player.inventory if item_input in i]
        if not matching:
            print(f"你的背包里没有【{item_input}】。")
            return
        item_name = matching[0]
        item_type = ITEMS.get(item_name, {}).get("type")

        if cmd == "wield" and item_type == "weapon":
            old = player.equipment.get("weapon")
            if old: player.inventory.append(old)
            player.equipment["weapon"] = item_name
            player.inventory.remove(item_name)
            player.equip_enhance["weapon"] = 0
            print(f"{Color.GREEN}装备了武器：【{item_name}】！{Color.RESET}")
        elif cmd == "wear" and item_type == "armor":
            old = player.equipment.get("armor")
            if old: player.inventory.append(old)
            player.equipment["armor"] = item_name
            player.inventory.remove(item_name)
            player.equip_enhance["armor"] = 0
            print(f"{Color.GREEN}穿上了防具：【{item_name}】！{Color.RESET}")
        else:
            print(f"{Color.RED}【{item_name}】无法进行此类装备！{Color.RESET}")

    elif cmd == "use":
        matching = [i for i in player.inventory if item_input in i]
        if not matching:
            print(f"行囊里没有【{item_input}】。")
            return
        apply_consumable(player, matching[0])


# ==================== 打铁铺强化 ====================
def handle_forge(player, args):
    if player.location != "blacksmith":
        print("只有在打铁铺才可以强化装备！")
        return

    print(f"\n{Color.BRIGHT_YELLOW}================ 铁匠打造炉 ================{Color.RESET}")
    w_name = player.equipment.get("weapon") or "无"
    a_name = player.equipment.get("armor") or "无"
    w_lv = player.equip_enhance.get("weapon", 0)
    a_lv = player.equip_enhance.get("armor", 0)
    ore_cnt = player.inventory.count("铁矿石")

    print(f"当前兵刃：{Color.GREEN}{w_name} (+{w_lv}){Color.RESET}")
    print(f"当前防具：{Color.GREEN}{a_name} (+{a_lv}){Color.RESET}")
    print(f"拥有铁矿石：{Color.YELLOW}{ore_cnt} 块{Color.RESET}  银两：{Color.YELLOW}{player.gold} 两{Color.RESET}")
    print("--------------------------------------------")
    print("1. 强化兵刃（消耗 1 块铁矿石 + 30 银两）")
    print("2. 强化防具（消耗 1 块铁矿石 + 30 银两）")
    print("0. 离开打造炉")

    choice = input("请选择打造项目 (0-2)：").strip()
    if choice == "1":
        slot_key, target_name = "weapon", w_name
    elif choice == "2":
        slot_key, target_name = "armor", a_name
    else:
        return

    if target_name == "无":
        print(f"{Color.RED}你身上并未装备对应的{'兵刃' if slot_key=='weapon' else '防具'}！{Color.RESET}")
        return

    if player.equip_enhance.get(slot_key, 0) >= 5:
        print(f"{Color.RED}该装备已经强化至最高等级 (+5)！{Color.RESET}")
        return

    if ore_cnt < 1 or player.gold < 30:
        print(f"{Color.RED}强化材料不足！需要 1 块铁矿石及 30 银两。{Color.RESET}")
        return

    player.inventory.remove("铁矿石")
    player.gold -= 30
    player.equip_enhance[slot_key] += 1
    new_lv = player.equip_enhance[slot_key]
    print(f"\n{Color.BRIGHT_GREEN}锤打叮当，火花四溅！你的【{target_name}】成功强化至 +{new_lv}！{Color.RESET}")
    player.save_to_file()


# ==================== 战斗系统 ====================
def pick_enemy_skill(enemy_data):
    skills = enemy_data.get("skills", [])
    if not skills:
        return None
    for sk in skills:
        if random.random() < sk.get("chance", 0.3):
            return sk
    return None


def combat(player, enemy_name):
    e_data = deepcopy(ENEMIES.get(enemy_name, {}))
    if not e_data:
        print(f"找不到关于【{enemy_name}】的战斗数据！")
        return

    e_hp, e_max_hp = e_data["hp"], e_data["hp"]
    e_atk, e_def = e_data["atk"], e_data["defense"]

    p_statuses = p_statuses_global
    e_statuses = {}

    print(f"\n{Color.BRIGHT_RED}========== 战斗开始：{enemy_name} =========={Color.RESET}")

    while player.hp > 0 and e_hp > 0:
        print("\n--------------------------------------------")
        print(f"{player.name}: 气血 {draw_bar(player.hp, player.max_hp, fill_color=Color.RED)} "
              f"内力 {draw_bar(player.mp, player.max_mp, fill_color=Color.BLUE)}")
        print(f"{enemy_name}: 气血 {draw_bar(e_hp, e_max_hp, fill_color=Color.BRIGHT_RED)}")
        print(f"玩家状态: {format_statuses(p_statuses)} | 敌人状态: {format_statuses(e_statuses)}")

        p_dmg, p_stun, p_msgs = process_status_effects(p_statuses)
        e_dmg, e_stun, e_msgs = process_status_effects(e_statuses)
        player.hp = max(0, player.hp + p_dmg)
        e_hp = max(0, e_hp + e_dmg)

        for m in p_msgs: print(f"你: {m}")
        for m in e_msgs: print(f"{enemy_name}: {m}")

        if player.hp <= 0 or e_hp <= 0: break

        # 玩家回合
        if not p_stun:
            print("\n行动选项: [1] 普通攻击  [2] 武学招式  [3] 使用物品  [4] 尝试逃跑")
            act = input("请选择行动：").strip()

            if act == "4":
                if random.random() < 0.55:
                    print(f"{Color.GREEN}你拔腿施展轻功，成功摆脱敌人！{Color.RESET}")
                    p_statuses.pop("shield", None)
                    player.save_to_file()
                    return
                else:
                    print(f"{Color.RED}逃跑失败，被对方一把拦住去路！{Color.RESET}")
            elif act == "3":
                consumables = [i for i in list(dict.fromkeys(player.inventory)) if ITEMS.get(i, {}).get("type") == "consumable"]
                if not consumables:
                    print("行囊中无可用消耗品。")
                else:
                    for idx, item in enumerate(consumables, 1):
                        print(f"  {idx}. {item}")
                    use_c = input("使用物品序号 (0取消)：").strip()
                    if use_c.isdigit() and 0 < int(use_c) <= len(consumables):
                        apply_consumable(player, consumables[int(use_c) - 1])
            elif act == "2":
                avail = [s for s in SKILLS.get(player.sect, SKILLS["散人"]) if player.level >= s["level"]]
                for idx, sk in enumerate(avail, 1):
                    print(f"  {idx}. {sk['name']} (耗内 {sk['mp_cost']} / 威力 {int(sk['power']*100)}%)")
                sk_c = input("选择招式序号 (0取消)：").strip()
                if sk_c.isdigit() and 0 < int(sk_c) <= len(avail):
                    sk = avail[int(sk_c) - 1]
                    if player.mp >= sk["mp_cost"]:
                        player.mp -= sk["mp_cost"]
                        dmg = max(1, int(player.get_total_atk() * sk["power"] - e_def))
                        e_hp = max(0, e_hp - dmg)
                        print(f"{Color.YELLOW}你一式【{sk['name']}】轰出，造成 {dmg} 点伤害！{Color.RESET}")
                    else:
                        dmg = max(1, int(player.get_total_atk() - e_def))
                        e_hp = max(0, e_hp - dmg)
                        print(f"内力不足，改为普通攻击，造成 {dmg} 点伤害！")
            else:
                dmg = max(1, int(player.get_total_atk() - e_def))
                e_hp = max(0, e_hp - dmg)
                print(f"你挥舞兵刃发起攻击，造成 {dmg} 点伤害！")

        if e_hp <= 0:
            print(f"\n{Color.BRIGHT_GREEN}你击败了【{enemy_name}】！{Color.RESET}")
            p_statuses.pop("shield", None)
            player.gain_exp(e_data.get("exp", 10))
            player.gold += e_data.get("gold", 5)
            player.update_quest_progress(enemy_name)
            for drop in e_data.get("drops", []):
                if random.random() < drop["chance"]:
                    player.inventory.append(drop["item"])
                    print(f"{Color.GREEN}搜刮战利品，获得了【{drop['item']}】！{Color.RESET}")
            player.save_to_file()
            return

        # 敌人回合
        if not e_stun:
            e_skill = pick_enemy_skill(e_data)
            if e_skill:
                p_pwr = e_skill.get("power", 1.2)
                raw_dmg = max(1, int(e_atk * p_pwr - player.get_total_defense()))
                print(f"{Color.RED}{enemy_name} 施展出技能【{e_skill['name']}】！{Color.RESET}")

                dmg = _apply_shield(p_statuses, raw_dmg)

                if dmg > 0:
                    player.hp = max(0, player.hp - dmg)
                    print(f"技能对你造成了 {Color.RED}{dmg}{Color.RESET} 点伤害！")

                if "effect" in e_skill:
                    add_status(p_statuses, e_skill["effect"], e_skill.get("turns", 2), e_skill.get("value", 3))
            else:
                raw_dmg = max(1, int(e_atk - player.get_total_defense()))
                dmg = _apply_shield(p_statuses, raw_dmg)

                if dmg > 0:
                    player.hp = max(0, player.hp - dmg)
                    print(f"{enemy_name} 发起攻击，对你造成 {dmg} 点伤害！")

        battle_pause(0.5)

    if player.hp <= 0:
        print(f"\n{Color.BRIGHT_RED}你重伤倒地，晕厥过去……（已被热心村民抬回古庙养伤）{Color.RESET}")
        player.hp = int(player.max_hp * 0.5)
        player.location = "temple"
        clear_statuses()
        player.save_to_file()


def handle_attack(player, args):
    room = ROOMS.get(player.location, {})
    enemies = room.get("enemies", [])
    npcs = room.get("npcs", [])

    if not args:
        if enemies:
            combat(player, enemies[0])
        else:
            print("这里没有可以攻击的敌对目标。")
        return

    target = args[0]
    for e in enemies:
        if target in e:
            combat(player, e)
            return

    for n in npcs:
        if target in n:
            print(f"{Color.YELLOW}【{n}】并非可战之敌，不可胡乱出手！{Color.RESET}")
            return

    print(f"未在此处找到目标【{target}】。")


# ==================== 面板展示 ====================
def show_status(player):
    print(f"\n{Color.CYAN}---------- 侠客面板 ----------{Color.RESET}")
    print(f"姓名：{Color.BOLD}{player.name}{Color.RESET}  门派：{Color.MAGENTA}{player.sect}{Color.RESET}")
    print(f"等级：{player.level}  修为：{draw_bar(player.exp, player.exp_to_level, length=8, fill_color=Color.YELLOW)}")
    print(f"气血：{draw_bar(player.hp, player.max_hp, fill_color=Color.RED)}")
    print(f"内力：{draw_bar(player.mp, player.max_mp, fill_color=Color.BLUE)}")
    print(f"攻击：{player.get_total_atk()} (基础{player.atk})  防御：{player.get_total_defense()} (基础{player.defense})")
    print(f"银两：{Color.YELLOW}{player.gold} 两{Color.RESET}")
    w_name = player.equipment.get('weapon') or '无'
    w_lv = player.equip_enhance.get('weapon', 0)
    a_name = player.equipment.get('armor') or '无'
    a_lv = player.equip_enhance.get('armor', 0)
    print(f"兵刃：{Color.GREEN}{w_name} (+{w_lv}){Color.RESET}  防具：{Color.GREEN}{a_name} (+{a_lv}){Color.RESET}")
    print(f"身中状态：{format_statuses(p_statuses_global)}")
    print(f"{Color.CYAN}------------------------------{Color.RESET}")


def show_inventory(player):
    print(f"\n{Color.CYAN}---------- 背包行囊 ----------{Color.RESET}")
    if not player.inventory:
        print("身无长物。")
    else:
        counts = Counter(player.inventory)
        for item, cnt in counts.items():
            desc = ITEMS.get(item, {}).get("desc", "未知")
            print(f"- {Color.GREEN}{item}{Color.RESET} x{cnt}：{desc}")
    print(f"{Color.CYAN}------------------------------{Color.RESET}")


def show_help():
    print(f"\n{Color.BRIGHT_YELLOW}========== 江湖指令大全 =========={Color.RESET}")
    print(" 🚶 移动探索：n/s/e/w (移动), look/l [目标] (观察环境或观察NPC/怪物), map/m (地图), search (采集)")
    print(" 🎒 物品装备：i (背包), wield <武器> (装备), wear <防具> (穿戴), use <药剂>")
    print(" ⚔️ 战斗互动：kill <目标> (攻击), talk <NPC> [话题] (交谈/打听信息)")
    print(" 📜 任务系统：renwu (查看任务), jiequ <任务名> (接取), jiaofu <任务名> (交付)")
    print(" 💆 调息打坐：dazuo / heal (打坐调息恢复气血与内力，古庙打坐可驱散病邪)")
    print(" 💰 交易打造：shop / list (货架), buy <物品>, sell <物品>, forge (打铁)")
    print(" 💾 系统功能：save (手动存档), load (读档), status/st (属性面板), h (帮助), rl (热重载)")
    print(f"{Color.BRIGHT_YELLOW}=================================={Color.RESET}\n")


# ==================== 主流程 ====================
def main():
    player = None
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
            print("\n请选择门派：\n1. 少林  2. 武当  3. 华山  4. 散人")
            choice = input("请选择 (1-4)：").strip()
            sect_map = {"1": "少林", "2": "武当", "3": "华山", "4": "散人"}
            player = Player(name, sect_map.get(choice, "散人"))
            clear_statuses()
            player.save_to_file()

        clear_screen()
        look(player)

        while True:
            curr_room = ROOMS.get(player.location, {})
            r_name = curr_room.get("name", "未知区域")
            raw_in = input(f"\n<{r_name}> 指令 > ").strip()
            cmd, args = parse_command(raw_in)

            if not cmd: continue

            if cmd in ("quit", "exit"):
                player.save_to_file()
                print("少侠保重，后会有期！")
                break
            elif cmd == "save":
                player.save_to_file()
            elif cmd == "load":
                loaded = Player.load_from_file()
                if loaded: player = loaded; look(player)
            elif cmd == "help":
                show_help()
            elif cmd == "map":
                show_map(player)
            elif cmd in ("reload", "热重载"):
                reload_game_data(); look(player)
            elif cmd in ("look", "看"):
                look(player, args)
            elif cmd in ("status", "状态"):
                show_status(player)
            elif cmd in ("inventory", "背包"):
                show_inventory(player)
            elif cmd == "talk":
                handle_talk_and_ask(player, args)
            elif cmd in ("quests", "jiequ", "jiaofu"):
                handle_quest(player, cmd, args)
            elif cmd in ("shop", "list", "buy", "sell"):
                handle_trading(player, cmd, args)
            elif cmd in ("wield", "wear", "use"):
                handle_equipment_and_items(player, cmd, args)
            elif cmd in ("kill", "attack"):
                handle_attack(player, args)
            elif cmd == "heal":
                is_temple = (player.location == "temple")
                bonus = 2 if is_temple else 1
                rec_hp = 30 * bonus
                rec_mp = 20 * bonus
                player.hp = min(player.max_hp, player.hp + rec_hp)
                player.mp = min(player.max_mp, player.mp + rec_mp)
                if is_temple:
                    clear_statuses()
                    print(f"{Color.BRIGHT_GREEN}古庙石佛前盘膝打坐，气血恢复 {rec_hp} 点，内力恢复 {rec_mp} 点，一身病邪异状皆被驱散！{Color.RESET}")
                else:
                    print(f"{Color.GREEN}盘膝打坐调息，恢复了 {rec_hp} 点气血与 {rec_mp} 点内力！{Color.RESET}")
            elif cmd == "search":
                if "forage" in curr_room:
                    found = False
                    for item, chance in curr_room["forage"].items():
                        if random.random() < chance:
                            player.inventory.append(item)
                            print(f"{Color.GREEN}一番仔细搜寻，找到了【{item}】！{Color.RESET}")
                            found = True
                    if not found: print("仔细搜寻了一圈，一无所获。")
                else: print("此地没有可采摘搜寻的资源。")
            elif cmd == "forge":
                handle_forge(player, args)
            elif cmd in curr_room.get("exits", {}):
                player.location = curr_room["exits"][cmd]
                clear_screen()
                look(player)

                next_room = ROOMS.get(player.location, {})
                if not next_room.get("safe", False) and next_room.get("enemies") and random.random() < 0.45:
                    e_name = random.choice(next_room["enemies"])
                    print(f"\n{Color.RED}跳出个【{e_name}】挡住去路！{Color.RESET}")
                    battle_pause(0.8)
                    combat(player, e_name)
            else:
                print(f"{Color.RED}未知指令。输入 h 或 help 可查看全部命令大全。{Color.RESET}")

    except KeyboardInterrupt:
        if player:
            player.save_to_file()
            print("\n游戏被手动中断，已自动为你保存当前进度。少侠后会有期！")
        else:
            print("\n游戏已退出。")


if __name__ == "__main__":
    main()
