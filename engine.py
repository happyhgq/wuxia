# -*- coding: utf-8 -*-
"""
engine.py - 动态地图引擎、状态机制与 DataLoader
"""

import json
import os
import random
import time
import unicodedata
from copy import deepcopy
from collections import deque

if os.name == "nt":
    os.system("")

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
    width = 0
    for ch in s:
        if ch == "🚪" or unicodedata.east_asian_width(ch) in ('F', 'W'):
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

    ZONE_NAMES = {
        "main": "主世界",
        "bandit_zone": "黑风寨"
    }

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
            zone_rooms = {k: v for k, v in self.rooms.items() if v.get("zone", "main") == z}
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

    def render(self, player_loc):
        curr_room = self.rooms.get(player_loc, {})
        curr_zone = curr_room.get("zone", "main")
        zone_title = self.ZONE_NAMES.get(curr_zone, curr_zone)

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

        target_raw_node = None
        for r_key, (x, y) in zone_room_coords.items():
            row = (max_y - y) * 2
            col = (x - min_x) * cell_w
            r_name = self.rooms.get(r_key, {}).get("name", r_key)

            has_portal = False
            for t_key in self.rooms.get(r_key, {}).get("exits", {}).values():
                if self.rooms.get(t_key, {}).get("zone", "main") != curr_zone:
                    has_portal = True
                    break

            display_label = f"{r_name}🚪" if has_portal else r_name
            raw_node = f"[{pad_to_width(display_label, 8, align='center')}]"

            if r_key == player_loc:
                target_raw_node = raw_node

            put_text(row, col, raw_node)

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