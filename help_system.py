# -*- coding: utf-8 -*-
"""三层帮助：分类目录 -> 分类页 -> 单条指令详情。

注册表是唯一数据源：分类页只显示名称与一句话用途，详情页才展开
用途、用法、别名、示例和相关指令。开发者指令不进入注册表。
"""
import unicodedata

from engine import Color
from ui_output import BODY_WIDTH, _ANSI_RE, safe_print as print, wrap_player_text

PAGE_SIZE = 12
NAV_DETAIL_HINT = "__help_detail_hint__"

CN_NUMBERS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
    "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13,
    "十四": 14,
}

CATEGORIES = [
    {
        "id": "view_move",
        "name": "查看与移动",
        "entries": ["look", "map", "move", "travel", "knock", "explore", "wait"],
    },
    {
        "id": "talk_people",
        "name": "交谈与人物",
        "entries": ["talk", "relations", "memory", "npc_actions", "world_activity", "business_rumor"],
    },
    {
        "id": "quest",
        "name": "任务与委托",
        "entries": ["quests", "quest_accept", "quest_deliver", "quest_abandon", "quest_branch"],
    },
    {
        "id": "sect",
        "name": "门派与师承",
        "entries": [
            "sect", "sect_join", "sect_view", "sect_promote", "sect_study",
            "sect_reputation", "sect_relations", "sect_mentor", "sect_ordain", "sect_leave",
        ],
    },
    {
        "id": "skills",
        "name": "武学与招式",
        "entries": ["skills", "skills_view", "skills_learn", "skills_forget"],
    },
    {
        "id": "growth",
        "name": "状态与成长",
        "entries": ["status", "attributes", "build", "weather"],
    },
    {
        "id": "bag_gear",
        "name": "背包与装备",
        "entries": ["inventory", "equipment", "wield", "wear", "equip", "unequip", "compare", "use"],
    },
    {
        "id": "gather",
        "name": "采集与生产",
        "entries": ["profession", "search", "collect", "chop", "mine", "forge", "forge_preview"],
    },
    {
        "id": "combat",
        "name": "战斗与恢复",
        "entries": ["kill", "heal", "run"],
    },
    {
        "id": "shop_trade",
        "name": "商店与交易",
        "entries": ["shop", "list", "buy", "sell"],
    },
    {
        "id": "inn",
        "name": "客栈与休息",
        "entries": ["inn_stay", "inn_meal", "inn_tea", "inn_rumor"],
    },
    {
        "id": "jianghu",
        "name": "江湖与消息",
        "entries": [
            "notice_board", "information", "caravan", "factions", "conflicts",
            "region", "influence", "security_governance", "events",
        ],
    },
    {
        "id": "system",
        "name": "系统与帮助",
        "entries": [
            "help", "encyclopedia", "advice", "color", "save", "load", "quit",
            "alias", "unalias", "history", "history_up", "history_down", "newbie",
        ],
    },
    {
        "id": "world_rules",
        "name": "世界规则",
        "entries": ["rule_sect", "rule_choice", "rule_endgame"],
    },
]

CATEGORY_ALIASES = {
    "人物": "talk_people",
    "社交": "talk_people",
    "npc": "talk_people",
    "物品": "bag_gear",
    "交易": "shop_trade",
    "系统": "system",
    "江湖": "jianghu",
    "成长": "growth",
    "移动": "view_move",
    "规则": "world_rules",
}

ENTRIES = {
    # 查看与移动
    "look": {
        "name": "看",
        "purpose": "查看当前场景、人物、自己或物品的信息。",
        "usage": "看 [对象名称]",
        "aliases": ["查看", "观察", "l"],
        "examples": ["看", "看 自己"],
        "related": ["map", "talk"],
    },
    "map": {
        "name": "地图",
        "purpose": "查看周边道路、出口与可前往的地点。",
        "usage": "地图",
        "aliases": ["图"],
        "examples": ["地图"],
        "related": ["move", "travel"],
    },
    "move": {
        "name": "方向移动",
        "purpose": "沿出口前进，或上楼、下楼、进出室内。",
        "usage": "北 / 南 / 东 / 西",
        "aliases": ["上楼", "下楼", "进入", "出外"],
        "examples": ["北", "上楼", "进入"],
        "related": ["map", "travel"],
    },
    "travel": {
        "name": "旅行",
        "purpose": "在已探索的交通节点之间快速往返。",
        "usage": "旅行 [目的地]",
        "aliases": ["行路"],
        "examples": ["旅行", "旅行 归云城"],
        "related": ["map", "move"],
    },
    "knock": {
        "name": "敲门",
        "purpose": "敲响当前场景的门或叩门求见。",
        "usage": "敲门",
        "aliases": ["叩门"],
        "examples": ["敲门"],
        "related": ["move", "talk"],
    },
    "explore": {
        "name": "探索",
        "purpose": "调查当前场景的隐藏线索与特殊地点。",
        "usage": "探索",
        "aliases": ["探险"],
        "examples": ["探索"],
        "related": ["search", "wait"],
        "extra": ["探索不会代替采集；发现资源后仍需输入“采集”获取。"],
    },
    "wait": {
        "name": "停留",
        "purpose": "停下脚步，等过一个时辰并留意四周动静。",
        "usage": "停留",
        "aliases": ["停"],
        "examples": ["停留"],
        "related": ["explore", "weather"],
        "extra": ["停留只推进一个时辰；不输入指令时世界不会自行流逝。"],
    },

    # 交谈与人物
    "talk": {
        "name": "交谈",
        "purpose": "与当前场景的人物交谈、打听话题或委托。",
        "usage": "交谈 人物名称 [话题]",
        "aliases": ["聊天", "对话", "打听", "问", "ask"],
        "examples": ["交谈 村长", "交谈 药铺老板 委托"],
        "related": ["relations", "quests"],
        "extra": ["接取委托使用：交谈 人物名称 接受委托 任务名称。"],
    },
    "relations": {
        "name": "关系",
        "purpose": "查看人物的身份、势力、关系与印象。",
        "usage": "关系 [人物名称]",
        "aliases": ["人物关系"],
        "examples": ["关系", "关系 村长"],
        "related": ["talk", "memory"],
    },
    "memory": {
        "name": "记忆",
        "purpose": "查看人物相关记忆与印象。",
        "usage": "记忆 [人物名称]",
        "aliases": ["回忆"],
        "examples": ["记忆", "记忆 柳三娘"],
        "related": ["relations", "npc_actions"],
    },
    "npc_actions": {
        "name": "人物行动",
        "purpose": "查看人物近期行动记录。",
        "usage": "人物行动",
        "aliases": ["人物行动记录"],
        "examples": ["人物行动"],
        "related": ["world_activity", "memory"],
    },
    "world_activity": {
        "name": "世界动态",
        "purpose": "查看人物近期真实采集、制作和交易记录。",
        "usage": "世界动态 [条数]",
        "aliases": ["营生动态"],
        "examples": ["世界动态"],
        "related": ["npc_actions", "business_rumor"],
    },
    "business_rumor": {
        "name": "商情",
        "purpose": "主动打听当前场景附近的营生消息。",
        "usage": "商情",
        "aliases": ["营生消息", "附近营生"],
        "examples": ["商情"],
        "related": ["information", "world_activity"],
        "extra": ["也可输入“查看 商情”或“打听 营生”。"],
    },

    # 任务与委托
    "quests": {
        "name": "任务",
        "purpose": "查看任务列表、进度与交付状态。",
        "usage": "任务",
        "aliases": ["任务列表", "查看任务"],
        "examples": ["任务"],
        "related": ["quest_accept", "quest_deliver"],
        "extra": [
            "先了解委托，再与人物交谈并选择“接受委托”；公告栏只提供线索。",
            "状态：未领取、已领取未完成、可交付、已交付；条件不足时会列出缺项与进度。",
            "目标完成后回到原委托人处交付；找错人物或进度不足会明确提示。",
            "选择分支：任务 选择 任务名称 分支名称（任务名与分支名之间用空格，不需要竖线）。",
            "交谈与 ask 是同一指令，ask 为英文别名。",
        ],
    },
    "quest_accept": {
        "name": "任务·接取",
        "purpose": "在发布委托的人物处接受任务。",
        "usage": "交谈 人物名称 接受委托 任务名称",
        "aliases": [],
        "examples": ["交谈 村长 接受委托 初入江湖·野外除害"],
        "related": ["quests", "talk"],
        "extra": ["独立输入“接取”不会领取任务，必须通过人物对话接受。"],
    },
    "quest_deliver": {
        "name": "任务·交付",
        "purpose": "回到原委托人处交付已完成的任务。",
        "usage": "任务 交付 任务名称",
        "aliases": ["交任务", "完成任务"],
        "examples": ["任务 交付 初入江湖·野外除害"],
        "related": ["quests", "talk"],
    },
    "quest_abandon": {
        "name": "任务·放弃",
        "purpose": "放弃已接取的任务。",
        "usage": "任务 放弃 任务名称",
        "aliases": ["放弃任务"],
        "examples": ["任务 放弃 初入江湖·野外除害"],
        "related": ["quests"],
    },
    "quest_branch": {
        "name": "任务·选择",
        "purpose": "为带分支的任务选择后续路线。",
        "usage": "任务 选择 任务名称 分支名称",
        "aliases": ["选择分支", "分支"],
        "examples": ["任务 选择 城内失踪案 2"],
        "related": ["quests"],
    },

    # 门派与师承
    "sect": {
        "name": "门派",
        "purpose": "查看当前门派、身份、职位与声望。",
        "usage": "门派",
        "aliases": ["宗门"],
        "examples": ["门派"],
        "related": ["sect_view", "sect_promote"],
        "extra": ["门派 查看 / 晋升 / 修习 / 声望 / 关系 / 师徒 / 受戒 / 退出 分别查看对应功能。"],
    },
    "sect_join": {
        "name": "拜师",
        "purpose": "申请加入门派。",
        "usage": "拜师 门派名称",
        "aliases": [],
        "examples": ["拜师 华山派"],
        "related": ["sect", "sect_view"],
    },
    "sect_view": {
        "name": "门派·查看",
        "purpose": "查看指定门派的资料与加入条件。",
        "usage": "门派 查看 [门派名称]",
        "aliases": [],
        "examples": ["门派 查看", "门派 查看 华山派"],
        "related": ["sect", "sect_join"],
    },
    "sect_promote": {
        "name": "门派·晋升",
        "purpose": "申请晋升门派职位。",
        "usage": "门派 晋升",
        "aliases": [],
        "examples": ["门派 晋升"],
        "related": ["sect", "sect_reputation"],
    },
    "sect_study": {
        "name": "门派·修习",
        "purpose": "在门派中修习本门武学。",
        "usage": "门派 修习",
        "aliases": [],
        "examples": ["门派 修习"],
        "related": ["skills", "sect"],
    },
    "sect_reputation": {
        "name": "门派·声望",
        "purpose": "查看门派声望与贡献。",
        "usage": "门派 声望",
        "aliases": [],
        "examples": ["门派 声望"],
        "related": ["sect", "sect_promote"],
    },
    "sect_relations": {
        "name": "门派·关系",
        "purpose": "查看门派与其他势力的关系。",
        "usage": "门派 关系",
        "aliases": [],
        "examples": ["门派 关系"],
        "related": ["sect", "factions"],
    },
    "sect_mentor": {
        "name": "门派·师徒",
        "purpose": "拜师或向师父请教。",
        "usage": "门派 师徒 拜师 / 门派 师徒 请教",
        "aliases": [],
        "examples": ["门派 师徒 拜师", "门派 师徒 请教"],
        "related": ["sect", "skills"],
    },
    "sect_ordain": {
        "name": "门派·受戒",
        "purpose": "少林弟子受戒；其他门派不适用。",
        "usage": "门派 受戒",
        "aliases": [],
        "examples": ["门派 受戒"],
        "related": ["sect"],
    },
    "sect_leave": {
        "name": "门派·退出",
        "purpose": "退出当前门派。",
        "usage": "门派 退出",
        "aliases": [],
        "examples": ["门派 退出"],
        "related": ["sect"],
    },

    # 武学与招式
    "skills": {
        "name": "武学",
        "purpose": "查看已掌握的武学、等级与熟练度。",
        "usage": "武学",
        "aliases": ["武功", "技能"],
        "examples": ["武学"],
        "related": ["skills_learn", "kill"],
        "extra": ["不同门派拥有不同路线；散人也能通过江湖经历成长。"],
    },
    "skills_view": {
        "name": "武学·查看",
        "purpose": "查看武学详情与修习进度。",
        "usage": "武学 查看 [武学名称]",
        "aliases": [],
        "examples": ["武学 查看"],
        "related": ["skills"],
    },
    "skills_learn": {
        "name": "武学·学习",
        "purpose": "学习满足条件的武学。",
        "usage": "武学 学习 武学名称",
        "aliases": [],
        "examples": ["武学 学习 基础剑法"],
        "related": ["skills", "sect"],
    },
    "skills_forget": {
        "name": "武学·遗忘",
        "purpose": "遗忘已学武学。",
        "usage": "武学 遗忘 武学名称",
        "aliases": [],
        "examples": ["武学 遗忘 基础剑法"],
        "related": ["skills"],
    },

    # 状态与成长
    "status": {
        "name": "状态",
        "purpose": "查看气血、内力、修为与当前状态。",
        "usage": "状态",
        "aliases": ["状"],
        "examples": ["状态"],
        "related": ["attributes", "equipment"],
        "extra": ["状态面板支持 1–5 与 0 导航；主面板的“天时”一行显示天气。"],
    },
    "attributes": {
        "name": "属性",
        "purpose": "查看属性与可用属性点，并进行加点。",
        "usage": "属性 / 加点 属性名称 [点数]",
        "aliases": ["属性点"],
        "examples": ["属性", "加点 力量 2"],
        "related": ["status", "build"],
    },
    "build": {
        "name": "流派",
        "purpose": "查看当前成长路线倾向。",
        "usage": "流派",
        "aliases": [],
        "examples": ["流派"],
        "related": ["attributes", "skills"],
    },
    "weather": {
        "name": "天气",
        "purpose": "查看当前季节、节气与天气。",
        "usage": "状态",
        "aliases": ["天时", "节气"],
        "examples": ["状态"],
        "related": ["wait", "status"],
        "extra": [
            "季节、节气与天气只影响场景与天色文案，不改变战斗、任务、经济或等级数值。",
            "每 15 天进入一个节气；天气每 1~3 天在黎明变化一次。",
        ],
    },

    # 背包与装备
    "inventory": {
        "name": "背包",
        "purpose": "查看随身携带的物品与数量。",
        "usage": "背包",
        "aliases": ["行囊", "包"],
        "examples": ["背包"],
        "related": ["equipment", "use"],
    },
    "equipment": {
        "name": "装备",
        "purpose": "查看当前装备栏与装备情况。",
        "usage": "装备",
        "aliases": ["装备栏"],
        "examples": ["装备"],
        "related": ["wield", "wear"],
        "extra": ["兼容用法：装备武器 武器名称；穿戴装备 装备名称；卸下 部位；比较 装备名称。"],
    },
    "wield": {
        "name": "装备武器",
        "purpose": "更换当前兵刃。",
        "usage": "装备武器 武器名称",
        "aliases": ["持剑"],
        "examples": ["装备武器 铁剑"],
        "related": ["equipment", "unequip"],
    },
    "wear": {
        "name": "穿戴",
        "purpose": "穿戴防具或其他装备。",
        "usage": "穿戴 物品名称",
        "aliases": ["佩戴", "穿防具"],
        "examples": ["穿戴 皮甲"],
        "related": ["equipment", "unequip"],
    },
    "equip": {
        "name": "穿戴装备",
        "purpose": "通用穿戴入口，自动判断装备部位。",
        "usage": "穿戴装备 物品名称",
        "aliases": ["装备物品"],
        "examples": ["穿戴装备 皮甲"],
        "related": ["wear", "equipment"],
    },
    "unequip": {
        "name": "卸下",
        "purpose": "卸下指定部位的装备。",
        "usage": "卸下 部位名称",
        "aliases": ["卸装备"],
        "examples": ["卸下 兵刃"],
        "related": ["equipment", "wield"],
    },
    "compare": {
        "name": "比较",
        "purpose": "比较候选物品与当前装备的属性差异。",
        "usage": "比较 物品名称",
        "aliases": ["装备比较"],
        "examples": ["比较 铁剑"],
        "related": ["equipment", "inventory"],
    },
    "use": {
        "name": "使用",
        "purpose": "使用背包中的药品或消耗品。",
        "usage": "使用 物品名称",
        "aliases": ["使用物品"],
        "examples": ["使用 疗伤药"],
        "related": ["inventory", "heal"],
    },

    # 采集与生产
    "profession": {
        "name": "职业",
        "purpose": "查看采集、伐木、采矿的熟练等级与进度。",
        "usage": "职业",
        "aliases": ["采集熟练"],
        "examples": ["职业"],
        "related": ["collect", "chop"],
        "extra": ["成功获取资源会积累熟练度；等级 3 起，采集成果有机会额外增加一份。"],
    },
    "search": {
        "name": "搜索",
        "purpose": "发现当前场景可采集的资源，不消耗储量。",
        "usage": "搜索",
        "aliases": ["搜寻"],
        "examples": ["搜索"],
        "related": ["collect", "explore"],
    },
    "collect": {
        "name": "采集",
        "purpose": "获取已发现的草药等有限资源。",
        "usage": "采集",
        "aliases": [],
        "examples": ["采集"],
        "related": ["search", "profession"],
        "extra": [
            "草药地点：采药溪谷、药香浅滩、碎石药坡；伐木地点：雾隐林道、竹影幽谷、荒废柴场；采矿地点：废弃铁矿、铁脉长廊、坍塌采石坑。",
            "隐藏资源点：先在地下暗渠输入“探索”，发现暗门后可前往沉河暗库。",
        ],
    },
    "chop": {
        "name": "伐木",
        "purpose": "采伐林木，获得木材。",
        "usage": "伐木",
        "aliases": ["砍树", "采伐"],
        "examples": ["伐木"],
        "related": ["profession"],
    },
    "mine": {
        "name": "采矿",
        "purpose": "开采矿脉，获得矿石。",
        "usage": "采矿",
        "aliases": ["挖矿"],
        "examples": ["采矿"],
        "related": ["profession", "forge"],
    },
    "forge": {
        "name": "打造",
        "purpose": "在打铁铺强化兵刃或防具。",
        "usage": "打造",
        "aliases": ["锻造", "强化"],
        "examples": ["打造", "打造 预览"],
        "related": ["forge_preview", "mine"],
        "extra": ["打铁铺可强化兵刃、强化防具；输入“打造 预览”查看铁矿石等材料与银两成本。"],
    },
    "forge_preview": {
        "name": "打造·预览",
        "purpose": "查看下一等级属性、材料与银两成本。",
        "usage": "打造 预览",
        "aliases": [],
        "examples": ["打造 预览"],
        "related": ["forge"],
    },

    # 战斗与恢复
    "kill": {
        "name": "攻击",
        "purpose": "攻击当前场景中的目标并进入战斗。",
        "usage": "攻击 目标名称",
        "aliases": ["战斗", "击杀", "打"],
        "examples": ["攻击 山贼"],
        "related": ["heal", "skills"],
        "extra": ["战斗中按提示选择 1 普通攻击 / 2 武学招式 / 3 使用物品 / 4 尝试逃跑。"],
    },
    "heal": {
        "name": "打坐",
        "purpose": "在安全地点恢复气血与内力。",
        "usage": "打坐",
        "aliases": ["调息", "疗伤"],
        "examples": ["打坐"],
        "related": ["kill", "use"],
    },
    "run": {
        "name": "逃跑",
        "purpose": "非战斗时提示无法逃跑；战斗中请选择行动 4。",
        "usage": "flee / run",
        "aliases": [],
        "examples": ["flee"],
        "related": ["kill"],
    },

    # 商店与交易
    "shop": {
        "name": "商店",
        "purpose": "查看商人或商队的货单。",
        "usage": "商店 [商人或商队名称]",
        "aliases": ["店铺"],
        "examples": ["商店", "商店 商队"],
        "related": ["list", "buy"],
    },
    "list": {
        "name": "货架",
        "purpose": "查看当前可购买的商品。",
        "usage": "货架 [商人或商队名称]",
        "aliases": ["货单", "商品"],
        "examples": ["货架"],
        "related": ["shop", "buy"],
    },
    "buy": {
        "name": "购买",
        "purpose": "购买指定交易对象的物品。",
        "usage": "购买 物品名称 [数量] [给 交易对象]",
        "aliases": ["买"],
        "examples": ["购买 疗伤药", "购买 铁矿石 2 给 铁匠"],
        "related": ["sell", "shop"],
    },
    "sell": {
        "name": "出售",
        "purpose": "出售背包中的物品，可指定收购方。",
        "usage": "出售 物品名称 [数量] [给 交易对象]",
        "aliases": ["卖"],
        "examples": ["出售 木材", "出售 矿石 3 给 商队"],
        "related": ["buy", "inventory"],
    },

    # 客栈与休息
    "inn_stay": {
        "name": "住店",
        "purpose": "在客栈付费住宿，睡到次日天亮并恢复气血与内力。",
        "usage": "住店",
        "aliases": ["住宿", "客房", "留宿"],
        "examples": ["住店"],
        "related": ["inn_meal", "inn_tea"],
        "extra": ["住店 12 两，推进到次日卯时。"],
    },
    "inn_meal": {
        "name": "吃饭",
        "purpose": "在客栈用餐，小幅恢复气血与内力。",
        "usage": "吃饭",
        "aliases": ["用餐", "打尖"],
        "examples": ["吃饭"],
        "related": ["inn_tea", "inn_stay"],
        "extra": ["吃饭 4 两。"],
    },
    "inn_tea": {
        "name": "喝茶",
        "purpose": "饮茶休息，恢复少量内力。",
        "usage": "喝茶",
        "aliases": ["饮茶"],
        "examples": ["喝茶"],
        "related": ["inn_meal"],
        "extra": ["喝茶 2 两。"],
    },
    "inn_rumor": {
        "name": "听消息",
        "purpose": "花费银两听取一条客栈风声。",
        "usage": "听消息",
        "aliases": ["打听消息", "风声"],
        "examples": ["听消息"],
        "related": ["information", "business_rumor"],
        "extra": ["听消息 3 两，可在“信息”中回看。"],
    },

    # 江湖与消息
    "notice_board": {
        "name": "公告",
        "purpose": "查看近期公开江湖消息与榜墙。",
        "usage": "公告",
        "aliases": ["公告栏", "榜墙"],
        "examples": ["公告"],
        "related": ["information", "events"],
    },
    "information": {
        "name": "信息",
        "purpose": "查询或向人物打听指定话题。",
        "usage": "信息 话题",
        "aliases": ["消息", "传闻"],
        "examples": ["信息 江湖", "信息 门派"],
        "related": ["talk", "notice_board"],
    },
    "caravan": {
        "name": "商队",
        "purpose": "查看商队的位置、货物与行程。",
        "usage": "商队",
        "aliases": ["商路", "商旅"],
        "examples": ["商队"],
        "related": ["shop", "region"],
    },
    "factions": {
        "name": "势力",
        "purpose": "查看主要势力及其关系。",
        "usage": "势力",
        "aliases": ["阵营"],
        "examples": ["势力"],
        "related": ["conflicts", "influence"],
    },
    "conflicts": {
        "name": "冲突",
        "purpose": "查看势力冲突与局势变化。",
        "usage": "冲突",
        "aliases": ["局势", "势力冲突"],
        "examples": ["冲突"],
        "related": ["factions", "region"],
    },
    "region": {
        "name": "区域",
        "purpose": "查看当前区域局势与危险程度（含安全程度）。",
        "usage": "区域",
        "aliases": ["区域局势", "地区"],
        "examples": ["区域"],
        "related": ["security_governance", "events"],
    },
    "influence": {
        "name": "影响",
        "purpose": "查看你对江湖局势与势力的实际影响。",
        "usage": "影响",
        "aliases": ["势力影响"],
        "examples": ["影响"],
        "related": ["factions", "region"],
    },
    "security_governance": {
        "name": "治安",
        "purpose": "查看治安悬赏与治理情况。",
        "usage": "治安",
        "aliases": ["治安悬赏"],
        "examples": ["治安"],
        "related": ["region", "conflicts"],
    },
    "events": {
        "name": "事件",
        "purpose": "查看当前世界事件与进行中的变化。",
        "usage": "事件",
        "aliases": ["事件列表"],
        "examples": ["事件"],
        "related": ["region", "notice_board"],
    },

    # 系统与帮助
    "help": {
        "name": "帮助",
        "purpose": "查看分类目录、分类指令或单条指令详情。",
        "usage": "帮助 [分类序号] / 帮助 指令名",
        "aliases": ["帮", "?", "？"],
        "examples": ["帮助", "帮助 看"],
        "related": ["newbie", "advice"],
    },
    "encyclopedia": {
        "name": "百科",
        "purpose": "查询江湖世界相关词条。",
        "usage": "百科 [词条名称]",
        "aliases": ["江湖百科", "知识"],
        "examples": ["百科 武学"],
        "related": ["help", "information"],
    },
    "advice": {
        "name": "建议",
        "purpose": "根据当前场景与状态给出下一步建议。",
        "usage": "建议",
        "aliases": ["提示", "下一步"],
        "examples": ["建议"],
        "related": ["help", "newbie"],
    },
    "color": {
        "name": "颜色",
        "purpose": "查看或切换终端颜色显示。",
        "usage": "颜色 [auto/on/off]",
        "aliases": ["色彩"],
        "examples": ["颜色", "颜色 off"],
        "related": ["help"],
    },
    "save": {
        "name": "保存",
        "purpose": "保存当前游戏进度。",
        "usage": "保存",
        "aliases": ["存档", "存"],
        "examples": ["保存"],
        "related": ["load", "quit"],
    },
    "load": {
        "name": "读档",
        "purpose": "读取已有存档。",
        "usage": "读档",
        "aliases": ["读取", "载入", "读"],
        "examples": ["读档"],
        "related": ["save"],
    },
    "quit": {
        "name": "退出",
        "purpose": "保存并离开游戏。",
        "usage": "退出",
        "aliases": ["离开游戏", "退"],
        "examples": ["退出"],
        "related": ["save"],
    },
    "alias": {
        "name": "别名",
        "purpose": "设置常用指令的快捷写法。",
        "usage": "别名 名称 = 指令",
        "aliases": ["快捷"],
        "examples": ["别名 回村 = 南;南;西"],
        "related": ["unalias", "history"],
    },
    "unalias": {
        "name": "删除别名",
        "purpose": "删除已设置的快捷指令。",
        "usage": "删除别名 名称",
        "aliases": ["取消别名"],
        "examples": ["删除别名 回村"],
        "related": ["alias"],
    },
    "history": {
        "name": "历史",
        "purpose": "查看近期输入的指令记录。",
        "usage": "历史",
        "aliases": ["命令历史"],
        "examples": ["历史"],
        "related": ["history_up", "history_down"],
    },
    "history_up": {
        "name": "上条",
        "purpose": "回看历史中的上一条指令。",
        "usage": "上条",
        "aliases": ["上一条"],
        "examples": ["上条"],
        "related": ["history"],
    },
    "history_down": {
        "name": "下条",
        "purpose": "查看历史中的下一条提示。",
        "usage": "下条",
        "aliases": ["下一条"],
        "examples": ["下条"],
        "related": ["history"],
    },
    "newbie": {
        "name": "新手引导",
        "purpose": "分步了解查看、交谈、任务与成长。",
        "usage": "帮助 新手",
        "aliases": ["新手", "入门", "新手指引"],
        "examples": ["帮助 新手"],
        "related": ["advice", "help"],
        "extra": [
            "第一步：输入“查看”认识场景，再用“状态”和“背包”检查自己。",
            "移动：输入“北、南、东、西”；输入“地图”查看路线。",
            "人物：先用“查看 人物名”了解对方，再“交谈 人物名”。",
            "任务：输入“任务”查看进度；与人物交谈接受委托。",
            "消息：输入“公告”查看村口消息，输入“建议”获得下一步提示。",
            "成长：输入“武学”“装备”；受伤后在安全地点“打坐”。",
            "世界时间随你的行动推进；不输入指令时世界不会自行推进，可用“停留”等过一个时辰。",
            "可自由探索，不强制按固定路线游玩；采集、交易、交友、探索和习武都可以成为自己的江湖路。",
            "门派声望、选择后果与终局目标见“帮助 世界规则”。",
        ],
    },
    # 世界规则：讲机制而不是指令，供玩家在做出长期选择前查阅。
    "rule_sect": {
        "name": "门派声望",
        "purpose": "理解门派声望如何增减，以及转投别派时旧立场的影响。",
        "usage": "门派 声望",
        "aliases": ["声望规则", "门派立场", "门派声望与立场"],
        "examples": ["门派 声望"],
        "related": ["sect_reputation", "sect_join", "sect_leave"],
        "extra": [
            "声望范围 -1000 到 1000；新入门的门派从 0 起算，做本门任务、受戒与晋升等门派事务会逐步积累。",
            "四门 L15 委托（少林·伏魔护寺、武当·夜巡断魂、华山·绝壁试锋、铁衣门·断魂护镖）首次完成时：本门 +8，其余三门各 -2。",
            "同类委托复做不再改变任何门派声望，只结经验、银两与断魂精铁；负声望不会被反复刷取。",
            "退门不会清零声望，也不会抹掉替别派出手的记录；带着负声望拜入他门时，门中会先翻出这段旧账。",
            "查看：门派 声望；退门提示会列出其余各门对你的当前声望。",
        ],
    },
    "rule_choice": {
        "name": "选择与后果",
        "purpose": "了解任务分支与结局如何改变地区、势力与后续剧情。",
        "usage": "任务 选择 任务名称 分支名称",
        "aliases": ["分支规则", "后果"],
        "examples": ["任务 选择 城内失踪案 2"],
        "related": ["quest_branch", "quests", "region"],
        "extra": [
            "分支在任务中途选择：任务 选择 任务名称 分支名称；条件不足的路线不会出现，选定后推进到下一阶段，不能反悔。",
            "部分委托在交付时先定结局：交付 任务名称|序号，例如 交付 少林收束·戒律与慈悲|2；未解锁的结局会列出缺少的条件。",
            "后果以“区域变化：地名 安全度 +6、商路 -2、通行 -3”的形式当场提示；三项按地区累积，并各有上下限。",
            "分支与结局还会改变势力关系、人物关系、侠义或恶名、门派声望，并写入后续任务与人物台词所需的条件。",
            "四门派收束与归云三方·定局都提供三选一结局：一段剧情只落定一个结局，其余不再可选；收束任务始终保留至少两条满足条件即可选的路线。",
        ],
    },
    "rule_endgame": {
        "name": "终局目标",
        "purpose": "了解 L15 之后还能做什么，以及终局面板各项的含义。",
        "usage": "状态",
        "aliases": ["终局", "设计上限"],
        "examples": ["状态"],
        "related": ["status", "quests", "sect"],
        "extra": [
            "打开方式：输入“状态”后在主面板按 5 进入“终局目标”子面板，按 0 关闭面板。",
            "L15 是当前内容的设计上限，不是硬上限：经验满 3500 后仍可升到 L16 及以上，继续积累不会卡住。",
            "终局面板提示随等级变化：未满 L15 时提示设计上限，L15 及以上则提示可继续积累经验。",
            "面板列出断魂堡、门派终局委托、断魂精铁与装备强化四项进度，方便判断还差什么。",
            "L15 之后的可重复供给：巡道除匪、本门 L15 委托、断魂崖夜行客与精铁换药；复做按世界时刻计算冷却。",
            "四门派收束与归云三方·定局会把你此前的选择落成结局；结局之后仍可留在江湖巡道、接委托与继续成长。",
        ],
    },
}

CATEGORY_BY_ID = {category["id"]: category for category in CATEGORIES}

# 一个帮助条目对应多条真实指令：方向键与上下楼都归入“方向移动”。
MULTI_COMMAND_ENTRIES = {
    "move": {"n", "s", "e", "w", "内", "外", "前", "后", "u", "d"},
    "quest_abandon": {"fangqi", "abandon"},
}


def _command_map():
    from main import CMD_MAP

    return CMD_MAP


def _normalize(text):
    return str(text or "").strip().lower()


def to_number(value):
    """把阿拉伯数字或中文序号转成整数；其他输入返回 None。"""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in CN_NUMBERS:
        return CN_NUMBERS[raw]
    if raw.isdigit():
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def is_number(value):
    return to_number(value) is not None


def is_category_selector(value):
    number = to_number(value)
    return number is not None and 1 <= number <= len(CATEGORIES)


def category_number(category_id):
    for index, category in enumerate(CATEGORIES, 1):
        if category["id"] == category_id:
            return index
    return 0


def total_pages(category):
    return max(1, (len(category["entries"]) + PAGE_SIZE - 1) // PAGE_SIZE)


def page_for_index(category_id, index):
    category = CATEGORY_BY_ID.get(category_id)
    if not category:
        return 1
    try:
        position = max(1, int(index))
    except (TypeError, ValueError):
        position = 1
    return min(total_pages(category), (position - 1) // PAGE_SIZE + 1)


def entry_number(entry_id):
    for category in CATEGORIES:
        if entry_id in category["entries"]:
            return category["entries"].index(entry_id) + 1
    return 0


def entry_category(entry_id):
    for category in CATEGORIES:
        if entry_id in category["entries"]:
            return category
    return None


def _entry_command_tokens(entry_id):
    command = ENTRIES[entry_id].get("command")
    if not command:
        return []
    return [token for token, canonical in _command_map().items() if canonical == command]


_BASE_ENTRY_COMMANDS = {
    "look": "look", "map": "map", "travel": "travel", "knock": "knock",
    "explore": "explore", "wait": "wait", "talk": "talk", "relations": "relations",
    "memory": "memory", "npc_actions": "npc_actions", "world_activity": "world_activity",
    "business_rumor": "business_rumor", "quests": "quests", "quest_accept": "jiequ",
    "quest_deliver": "jiaofu", "quest_abandon": "fangqi", "quest_branch": "xuanze",
    "sect": "sect", "sect_join": "sect_join", "skills": "skills", "status": "status",
    "attributes": "attributes", "build": "build", "inventory": "inventory",
    "equipment": "equipment", "wield": "wield", "wear": "wear", "equip": "equip",
    "unequip": "unequip", "compare": "compare", "use": "use", "profession": "profession",
    "search": "search", "collect": "collect", "chop": "chop", "mine": "mine",
    "forge": "forge", "kill": "kill", "heal": "heal", "run": "run", "shop": "shop",
    "list": "list", "buy": "buy", "sell": "sell", "inn_stay": "inn_stay",
    "inn_meal": "inn_meal", "inn_tea": "inn_tea", "inn_rumor": "inn_rumor",
    "notice_board": "notice_board", "information": "information", "caravan": "caravan",
    "factions": "factions", "conflicts": "conflicts", "region": "region",
    "influence": "influence", "security_governance": "security_governance",
    "events": "events", "help": "help", "encyclopedia": "encyclopedia",
    "advice": "advice", "color": "color", "save": "save", "load": "load",
    "quit": "quit", "alias": "alias", "unalias": "unalias", "history": "history",
    "history_up": "history_up", "history_down": "history_down",
}

for _entry_id, _command in _BASE_ENTRY_COMMANDS.items():
    ENTRIES[_entry_id]["command"] = _command


def command_entry_ids():
    """公开指令到帮助条目的映射；开发者指令不在其中。"""
    return dict(_BASE_ENTRY_COMMANDS)


_LOOKUP = None


def _short_subcommand(name):
    return name.split("·", 1)[1] if "·" in name else None


def _lookup():
    global _LOOKUP
    if _LOOKUP is not None:
        return _LOOKUP
    lookup = {}
    # 1. 完整子命令路径最优先：门派 晋升、武学 学习、任务 选择。
    for entry_id, entry in ENTRIES.items():
        if "·" in entry["name"]:
            lookup[_normalize(entry["name"].replace("·", " "))] = entry_id
    # 2. 真实指令及其全部别名（含未公开的兼容别名 look / st / north）。
    for entry_id in _BASE_ENTRY_COMMANDS:
        for token in _entry_command_tokens(entry_id):
            lookup.setdefault(_normalize(token), entry_id)
    for entry_id, commands in MULTI_COMMAND_ENTRIES.items():
        for token, canonical in _command_map().items():
            if canonical in commands:
                lookup.setdefault(_normalize(token), entry_id)
    # 3. 条目名与公开别名；指令名优先于子命令短名。
    for entry_id, entry in ENTRIES.items():
        lookup.setdefault(_normalize(entry["name"]), entry_id)
        for alias in entry.get("aliases", ()):
            lookup.setdefault(_normalize(alias), entry_id)
    # 4. 唯一的子命令短名：晋升、学习、受戒、预览等。
    short_counts = {}
    for entry in ENTRIES.values():
        short = _short_subcommand(entry["name"])
        if short:
            short_counts[short] = short_counts.get(short, 0) + 1
    for entry_id, entry in ENTRIES.items():
        short = _short_subcommand(entry["name"])
        if short and short_counts[short] == 1:
            lookup.setdefault(_normalize(short), entry_id)
    _LOOKUP = lookup
    return lookup


def _entry_in_category(category, token):
    normalized = _normalize(token)
    if not normalized:
        return None
    for entry_id in category["entries"]:
        entry = ENTRIES[entry_id]
        if _normalize(entry["name"]) == normalized:
            return entry_id
        if _normalize(entry["name"].replace("·", " ")) == normalized:
            return entry_id
        if any(_normalize(alias) == normalized for alias in entry.get("aliases", ())):
            return entry_id
        command = entry.get("command")
        commands = MULTI_COMMAND_ENTRIES.get(entry_id)
        if command or commands:
            for cmd_token, canonical in _command_map().items():
                if _normalize(cmd_token) != normalized:
                    continue
                if canonical == command or (commands and canonical in commands):
                    return entry_id
    return None


def resolve_category(token):
    normalized = _normalize(token)
    if not normalized:
        return None
    for category in CATEGORIES:
        if _normalize(category["name"]) == normalized:
            return category
    category_id = CATEGORY_ALIASES.get(normalized)
    return CATEGORY_BY_ID.get(category_id)


def _category_result(category, page):
    page = max(1, min(int(page or 1), total_pages(category)))
    return {"kind": "category", "category": category, "page": page}


def _detail_result(entry_id):
    category = entry_category(entry_id)
    return {"kind": "detail", "category": category, "entry_id": entry_id}


def _classify_in_category(category, rest):
    if not rest:
        return _category_result(category, 1)
    token = rest[0]
    if token == "0":
        return _category_result(category, 1)
    if token in ("上页", "下页"):
        return _category_result(category, 2 if token == "下页" else 1)
    if token.startswith("页") and is_number(token[1:]):
        page = to_number(token[1:])
        if 1 <= page <= total_pages(category):
            return _category_result(category, page)
        return {
            "kind": "invalid_page",
            "category": category,
            "page": max(1, min(page, total_pages(category))),
            "value": page,
        }
    number = to_number(token)
    if number is not None:
        if 1 <= number <= len(category["entries"]):
            return _detail_result(category["entries"][number - 1])
        return {
            "kind": "invalid_index",
            "category": category,
            "page": 1,
            "value": number,
        }
    entry_id = _entry_in_category(category, " ".join(rest))
    if not entry_id:
        entry_id = _entry_in_category(category, token)
    if entry_id:
        return _detail_result(entry_id)
    return {
        "kind": "invalid_entry",
        "category": category,
        "page": 1,
        "value": " ".join(rest),
    }


def classify(topic):
    """把玩家输入解析成主页、分类页或详情页。"""
    text = " ".join(str(topic or "").split())
    if not text or text in ("0", "返回", "返回上级"):
        return {"kind": "main"}
    parts = text.split()
    if parts[0] == NAV_DETAIL_HINT:
        category = CATEGORY_BY_ID.get(parts[1]) if len(parts) > 1 else None
        entry_id = parts[2] if len(parts) > 2 else None
        if category and entry_id in category["entries"]:
            return {
                "kind": "detail_hint",
                "category": category,
                "entry_id": entry_id,
            }
        return {"kind": "not_found", "topic": text}
    number = to_number(parts[0])
    if number is not None:
        if not 1 <= number <= len(CATEGORIES):
            return {"kind": "invalid_top", "value": number}
        return _classify_in_category(CATEGORIES[number - 1], parts[1:])
    category = resolve_category(parts[0])
    if category:
        return _classify_in_category(category, parts[1:])
    lookup = _lookup()
    candidates = [" ".join(parts)]
    if len(parts) >= 2:
        candidates.append(" ".join(parts[:2]))
    candidates.append(parts[0])
    for candidate in candidates:
        entry_id = lookup.get(_normalize(candidate))
        if entry_id:
            return _detail_result(entry_id)
    return {"kind": "not_found", "topic": text}


def visible_width(text):
    """终端显示宽度：ANSI 不计，东亚宽字符计 2 列。"""
    plain = _ANSI_RE.sub("", str(text or ""))
    total = 0
    for char in plain:
        if char == "\t":
            total += 4
        elif unicodedata.combining(char):
            continue
        else:
            total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def _pad(text, width):
    text = str(text or "")
    missing = width - visible_width(text)
    return text + " " * missing if missing > 0 else text


def _fit(text, width):
    text = str(text or "")
    if visible_width(text) <= width:
        return text
    result = ""
    for char in text:
        if visible_width(result + char) > width - 1:
            break
        result += char
    return result + "…"


def _category_label(index):
    numeral = next(
        (label for label, number in CN_NUMBERS.items() if number == index), str(index)
    )
    return f"【{numeral}】{CATEGORIES[index - 1]['name']}"


def _render_main():
    print(f"\n{Color.BRIGHT_YELLOW}【江湖帮助】{Color.RESET}")
    print("按用途分为十四类，每类只列标题与一句话说明。")
    for position in range(0, len(CATEGORIES), 2):
        left = _category_label(position + 1)
        right = _category_label(position + 2) if position + 2 <= len(CATEGORIES) else ""
        print(("  " + _pad(left, 37) + "  " + right).rstrip())
    print()
    print("用法：帮助 分类序号 / 帮助 分类名 / 帮助 指令名")
    print("示例：帮助 1　　帮助 门派与师承")


def _render_category(category, page):
    number = category_number(category["id"])
    pages = total_pages(category)
    title = f"【{CN_NUMBERS_REVERSE[number]} {category['name']}】"
    if pages > 1:
        title += f" 第 {page}/{pages} 页"
    print(f"\n{Color.BRIGHT_YELLOW}{title}{Color.RESET}")
    start = (page - 1) * PAGE_SIZE
    for offset, entry_id in enumerate(category["entries"][start:start + PAGE_SIZE], 1):
        index = start + offset
        entry = ENTRIES[entry_id]
        label = f"{index:>2}【{entry['name']}】"
        print(" " + _pad(label, 17) + _fit(entry["purpose"], BODY_WIDTH - 18))
    if pages > 1:
        hints = " / ".join(
            word for word, available in (("上页", page > 1), ("下页", page < pages)) if available
        )
        print(f"第 {page}/{pages} 页　输入“{hints}”翻页，或“帮助 {number} {hints}”。")
    print(f"0 或“帮助”返回主目录　输入“帮助 指令名”查看详情。")


def _render_detail(entry_id):
    entry = ENTRIES[entry_id]
    print(f"\n{Color.BRIGHT_YELLOW}【{entry['name']}】{Color.RESET}")
    print(wrap_player_text(f"用途：{entry['purpose']}", width=BODY_WIDTH))
    print(wrap_player_text(f"用法：{entry['usage']}", width=BODY_WIDTH))
    aliases = "、".join(entry.get("aliases", ())) or "无"
    print(wrap_player_text(f"别名：{aliases}", width=BODY_WIDTH))
    examples = list(entry.get("examples", ()))[:2]
    if examples:
        print(wrap_player_text(f"示例：{examples[0]}", width=BODY_WIDTH))
        for example in examples[1:]:
            print(wrap_player_text("      " + example, width=BODY_WIDTH))
    related = [ENTRIES[item]["name"] for item in entry.get("related", ()) if item in ENTRIES][:3]
    if related:
        print(wrap_player_text(f"相关：{'、'.join(related)}", width=BODY_WIDTH))
    for line in entry.get("extra", ()):
        print(wrap_player_text(line, width=BODY_WIDTH))
    print("0 返回分类　帮助 返回主目录")


CN_NUMBERS_REVERSE = {number: label for label, number in CN_NUMBERS.items()}


def show(topic=None):
    """渲染帮助页面；topic 为空时显示分类目录。"""
    result = classify(topic)
    kind = result["kind"]
    if kind == "main":
        _render_main()
        return
    if kind == "category":
        _render_category(result["category"], result["page"])
        return
    if kind == "detail":
        _render_detail(result["entry_id"])
        return
    if kind == "detail_hint":
        print(wrap_player_text(
            f"{Color.YELLOW}当前是详情页：输入“0”返回分类，或使用“帮助 分类 序号”打开其他指令。{Color.RESET}",
            width=BODY_WIDTH,
        ))
        _render_detail(result["entry_id"])
        return
    if kind == "invalid_top":
        print(wrap_player_text(
            f"{Color.YELLOW}没有第 {result['value']} 个分类，请输入 1–{len(CATEGORIES)}。{Color.RESET}",
            width=BODY_WIDTH,
        ))
        _render_main()
        return
    if kind == "invalid_index":
        category = result["category"]
        print(wrap_player_text(
            f"{Color.YELLOW}帮助菜单编号无效：第 {category_number(category['id'])} 类“{category['name']}”"
            f"没有第 {result['value']} 个条目（共 {len(category['entries'])} 条）。{Color.RESET}",
            width=BODY_WIDTH,
        ))
        _render_category(category, 1)
        return
    if kind == "invalid_entry":
        category = result["category"]
        print(wrap_player_text(
            f"{Color.YELLOW}帮助菜单编号无效：第 {category_number(category['id'])} 类“{category['name']}”"
            f"没有“{result['value']}”这个条目。{Color.RESET}",
            width=BODY_WIDTH,
        ))
        _render_category(category, 1)
        return
    if kind == "invalid_page":
        category = result["category"]
        print(wrap_player_text(
            f"{Color.YELLOW}这一页不存在，已回到第 {result['page']} 页。{Color.RESET}",
            width=BODY_WIDTH,
        ))
        _render_category(category, result["page"])
        return
    print(wrap_player_text(
        f"{Color.YELLOW}没有找到“{result['topic']}”这个帮助主题。"
        f"输入“帮助”查看分类目录，或“帮助 指令名”查询具体指令。{Color.RESET}",
        width=BODY_WIDTH,
    ))
