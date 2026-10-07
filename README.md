# Wuxia · 武侠文字 RPG

## AI 开发与项目接管说明书

> 本文件不是普通的项目介绍，而是本项目的 **AI 开发上下文（AI Development Context）**。
>
> 任何 AI、代码代理或新开发者在继续修改、扩展本项目之前，都应先完整阅读本文件，再阅读对应源码。

---

# 1. 项目定位

这是一个基于 Python 的 **中文武侠文字 RPG 游戏**。

当前游戏采用：

* Python
* 命令行 / 终端交互
* JSON 数据驱动
* 模块化游戏逻辑
* 回合制战斗
* 房间式地图
* Zone 区域系统
* NPC 对话
* 任务系统
* 商店与交易
* 装备系统
* 装备强化
* 资源采集
* 玩家成长
* 存档 / 读档
* 动态 ASCII 地图

项目的核心设计目标不是做一个一次性的 Demo，而是逐渐发展成为：

> **可以持续增加地图、城市、NPC、门派、任务、装备、敌人、剧情和游戏机制的可扩展武侠 RPG 基础框架。**

---

# 2. AI 最重要的项目认知

如果你是 AI，请首先记住以下规则。

## 2.1 当前推荐架构

当前项目已经从早期的单文件结构逐渐演化为：

```text
main.py
   │
   ├── 玩家输入
   ├── 指令解析
   ├── 游戏主循环
   └── 调用各游戏模块
          │
          ├── player.py
          ├── combat.py
          └── actions.py
                    │
                    ▼
                 engine.py
                    │
                    ├── 地图数据
                    ├── NPC 数据
                    ├── 物品数据
                    ├── 敌人数据
                    ├── 武功数据
                    ├── 任务数据
                    └── MapEngine
```

因此：

> **未来新增功能，默认应该基于 `main.py + player.py + combat.py + actions.py + engine.py` 的模块化架构继续开发。**

不要默认回到 `wuxia.py` 中继续堆代码。

---

# 3. 当前仓库结构

当前主要结构：

```text
wuxia/
│
├── README.md
│
├── main.py
├── engine.py
├── player.py
├── combat.py
├── actions.py
│
├── wuxia.py
│
└── data/
    ├── rooms.json
    ├── npcs.json
    ├── items.json
    ├── enemies.json
    ├── skills.json
    └── quests.json
```

运行游戏后还可能产生运行时存档等文件。

---

# 4. 文件职责

## 4.1 engine.py

这是整个项目最重要的基础层。

主要职责：

```text
engine.py
│
├── 默认游戏数据
│   ├── DEFAULT_ROOMS
│   ├── DEFAULT_NPCS
│   ├── DEFAULT_ITEMS
│   ├── DEFAULT_ENEMIES
│   ├── DEFAULT_SKILLS
│   └── DEFAULT_QUESTS
│
├── DataLoader
│
├── 全局游戏数据
│   ├── ROOMS
│   ├── NPCS
│   ├── ITEMS
│   ├── ENEMIES
│   ├── SKILLS
│   └── QUESTS
│
├── MapEngine
│
├── 状态效果
├── 战斗辅助函数
├── UI / Color
├── 存档相关常量
└── 地图相关辅助逻辑
```

### AI 修改规则

如果要增加：

* 房间
* NPC
* 道具
* 敌人
* 武功
* 任务

优先考虑：

```text
data/*.json
```

而不是直接修改：

```text
engine.py
```

只有在：

> **游戏机制本身发生变化**

时才应该修改 `engine.py`。

---

# 5. DataLoader 数据机制

`engine.py` 中存在 `DataLoader`。

其核心思想是：

```text
engine.py 默认数据
        +
data/*.json
        ↓
deep merge
        ↓
GAME_DATA
        ↓
ROOMS
NPCS
ITEMS
ENEMIES
SKILLS
QUESTS
```

加载的六类数据：

```text
rooms
npcs
items
enemies
skills
quests
```

对应：

```text
data/rooms.json
data/npcs.json
data/items.json
data/enemies.json
data/skills.json
data/quests.json
```

如果 JSON 不存在：

```text
DataLoader
    ↓
自动创建
    ↓
使用 DEFAULT_* 数据
```

如果 JSON 存在：

```text
DEFAULT_*
    +
JSON
    ↓
deep_merge
```

如果 JSON 解析失败：

```text
打印错误
    ↓
回退到默认数据
```

---

# 6. 数据扩展原则

以后扩展游戏世界时，优先使用：

```text
data/
```

而不是：

```text
engine.py
```

例如新增城市：

```text
data/rooms.json
```

新增城市 NPC：

```text
data/npcs.json
```

新增装备：

```text
data/items.json
```

新增敌人：

```text
data/enemies.json
```

新增技能：

```text
data/skills.json
```

新增任务：

```text
data/quests.json
```

---

# 7. rooms.json —— 世界地图核心

`rooms.json` 是整个游戏世界的核心数据之一。

一个房间本质上是：

```json
{
  "room_id": {
    "name": "地点名称",
    "zone": "main",
    "desc": "地点描述",
    "exits": {
      "北": "target_room",
      "南": "another_room"
    },
    "npcs": [],
    "enemies": [],
    "safe": true,
    "coord": [0, 0]
  }
}
```

常见字段：

| 字段        | 作用        |
| --------- | --------- |
| `name`    | 玩家看到的地点名称 |
| `zone`    | 所属区域      |
| `desc`    | 地点描述      |
| `exits`   | 出口        |
| `npcs`    | 当前地点 NPC  |
| `enemies` | 当前地点敌人    |
| `safe`    | 是否安全区域    |
| `coord`   | 地图坐标      |
| `forage`  | 可采集资源及概率  |

---

# 8. 地图系统最重要规则

地图不是简单的文字列表。

当前地图系统存在：

```text
room_id
    ↓
zone
    ↓
coord
    ↓
exits
```

例如：

```json
{
  "village_square": {
    "name": "村中广场",
    "zone": "main",
    "coord": [2, 3],
    "exits": {
      "北": "village_north_street",
      "南": "village_south_street",
      "西": "medicine_shop",
      "东": "blacksmith"
    }
  }
}
```

这里有三套必须同时成立的关系：

### 1. 逻辑出口

```text
village_square
    东
    ↓
blacksmith
```

### 2. 物理坐标

如果：

```text
village_square = [2, 3]
```

那么：

```text
东 = [3, 3]
```

### 3. 反向出口

应该存在：

```text
blacksmith
    西
    ↓
village_square
```

---

# 9. 地图扩展绝对注意事项

新增房间时不要只写：

```json
"exits": {
    "东": "new_room"
}
```

还要检查：

```text
new_room
    西
    ↓
原房间
```

并检查坐标：

```text
原房间 [x,y]

东 → [x+1,y]
西 → [x-1,y]
北 → [x,y+1]
南 → [x,y-1]
```

MapEngine 会检查：

* 坐标是否冲突
* 方向与坐标是否一致
* 出口是否互逆
* Zone 内部地图关系

---

# 10. Zone 区域系统

地图已经支持 Zone。

当前代码中至少存在：

```text
main
bandit_zone
```

例如：

```text
main
├── 青石村
├── 黄土官道
├── 村后荒野
├── 黑风山道
└── 山贼寨门

bandit_zone
├── 寨内演武场
├── 哨塔
├── 水牢
├── 聚义厅
├── 宝库
└── 黑风后山
```

Zone 的意义不是单纯分类。

它用于：

* 地图渲染
* 坐标系统隔离
* 区域地图
* 跨区域出口
* 未来扩展大型世界地图

---

# 11. Zone 扩展原则

如果未来增加：

```text
归云城
```

推荐：

```text
zone = "guiyun_city"
```

而不是把所有房间继续塞入：

```text
main
```

推荐结构：

```text
main
    ↓
黄土官道
    ↓
归云城城门
    ↓
guiyun_city
    ├── 城门
    ├── 城内主街
    ├── 东市
    ├── 西市
    ├── 县衙
    ├── 客栈
    ├── 武馆
    └── ...
```

---

# 12. NPC 系统

NPC 数据位于：

```text
data/npcs.json
```

典型 NPC 数据：

```json
{
  "村长": {
    "title": "青石村老村长",
    "desc": "NPC 描述",
    "type": "master",
    "dialogue": [
      "对话内容"
    ],
    "info": {
      "山贼": "相关情报"
    },
    "quests": [
      "清剿黑风山"
    ]
  }
}
```

常用字段：

```text
title
desc
type
dialogue
info
shop
quests
```

---

# 13. NPC 与地点必须双向关联

NPC 数据存在：

```text
data/npcs.json
```

并不意味着玩家能看到 NPC。

NPC 还必须出现在：

```text
rooms.json
```

例如：

```json
"village_head_house": {
    "npcs": ["村长"]
}
```

因此新增 NPC 时必须同时检查：

```text
NPC 数据
    +
房间中的 npcs
    +
任务
    +
商店
```

---

# 14. 物品系统

物品数据位于：

```text
data/items.json
```

主要类型：

```text
consumable
weapon
armor
material
```

例如：

```json
"铁剑": {
  "type": "weapon",
  "desc": "刃口薄利，尚堪一用。",
  "atk": 12,
  "price": 50
}
```

装备属性：

```text
weapon → atk
armor  → defense
```

消耗品可以：

```text
恢复 HP
恢复 MP
添加状态
```

---

# 15. 玩家属性系统

玩家核心状态由：

```text
player.py
```

管理。

当前主要属性包括：

```text
name
sect
level
exp
exp_to_level
hp
max_hp
mp
max_mp
atk
defense
gold
inventory
equipment
equip_enhance
location
active_quests
completed_quests
```

---

# 16. 门派初始属性

当前创建角色时可以选择：

```text
少林
武当
华山
散人
```

当前初始倾向：

```text
少林
→ HP / 防御

武当
→ MP / 攻击

华山
→ 攻击

散人
→ 基础均衡
```

未来增加门派时，应同时考虑：

```text
Player 初始化
+
SKILLS
+
门派设定
+
任务
+
NPC
+
世界关系
```

不要只增加一个下拉选项。

---

# 17. 玩家攻击力计算

当前总体攻击力：

```text
基础攻击
+
武器攻击
+
武器强化
```

其中：

```text
武器强化等级 × 3
```

会产生强化攻击加成。

即：

```text
total_atk =
    player.atk
    + weapon.atk
    + weapon_enhance * 3
```

---

# 18. 玩家防御力计算

总体防御：

```text
基础防御
+
防具防御
+
防具强化
```

其中：

```text
防具强化等级 × 2
```

即：

```text
total_defense =
    player.defense
    + armor.defense
    + armor_enhance * 2
```

---

# 19. 战斗系统

战斗核心：

```text
combat.py
```

调用：

```text
ENEMIES
SKILLS
ITEMS
Player
状态效果
```

基本流程：

```text
进入战斗
    ↓
读取敌人数据
    ↓
初始化敌人 HP
    ↓
玩家回合
    ↓
选择普通攻击 / 武功 / 道具
    ↓
计算伤害
    ↓
敌人行动
    ↓
敌人技能判定
    ↓
状态效果处理
    ↓
继续循环
    ↓
胜负结算
```

---

# 20. 敌人数据结构

典型：

```json
{
  "山贼二当家": {
    "hp": 160,
    "atk": 22,
    "defense": 11,
    "exp": 130,
    "gold": 90,
    "skills": [
      {
        "name": "夺命三刀",
        "chance": 0.35,
        "power": 1.8
      }
    ],
    "drops": [
      {
        "item": "精铁剑",
        "chance": 0.35
      }
    ]
  }
}
```

主要字段：

```text
hp
atk
defense
exp
gold
skills
drops
```

---

# 21. 敌人技能

敌人技能通常：

```text
name
chance
power
effect
turns
value
```

例如：

```json
{
  "name": "毒牙",
  "chance": 0.45,
  "power": 1.2,
  "effect": "poison",
  "turns": 4,
  "value": 5
}
```

可扩展状态包括：

```text
poison
bleed
stun
shield
```

未来新增状态时，必须同时检查：

```text
状态创建
+
状态持续
+
状态每回合处理
+
状态结束
+
UI 显示
```

不能只在 JSON 里增加一个字符串。

---

# 22. 玩家武功系统

技能数据：

```text
data/skills.json
```

当前按门派组织。

例如：

```json
{
  "少林": [
    {
      "name": "罗汉拳",
      "mp_cost": 15,
      "power": 1.8,
      "level": 1
    }
  ]
}
```

主要字段：

```text
name
mp_cost
power
level
```

伤害核心形式目前是：

```text
玩家总攻击 × 武功倍率 - 敌人防御
```

并保证最低伤害至少为：

```text
1
```

---

# 23. 任务系统

任务数据：

```text
data/quests.json
```

当前任务模型比较简单。

典型：

```json
{
  "清剿黑风山": {
    "title": "除暴安良·清剿黑风山",
    "npc": "村长",
    "target_type": "kill",
    "target_name": "山贼二当家",
    "required_cnt": 1,
    "reward": {
      "exp": 150,
      "gold": 100,
      "item": "玄铁重剑"
    },
    "desc": "任务描述"
  }
}
```

任务状态保存在：

```text
player.active_quests
player.completed_quests
```

---

# 24. 任务生命周期

基本流程：

```text
NPC
 ↓
提供任务
 ↓
jiequ
 ↓
active_quests
 ↓
完成目标
 ↓
progress
 ↓
满足 required_cnt
 ↓
jiaofu
 ↓
奖励
 ↓
completed_quests
```

扩展任务系统时必须保持这个生命周期完整。

---

# 25. 行为系统 actions.py

`actions.py` 负责玩家在世界中的大部分非核心战斗行为。

包括：

```text
look
talk
ask
quests
jiequ
jiaofu
shop
list
buy
sell
wield
wear
use
forge
```

可以理解为：

```text
玩家想做一件事
    ↓
main.py 判断指令
    ↓
actions.py 执行具体行为
    ↓
engine.py 提供世界数据
    ↓
player.py 修改玩家状态
```

---

# 26. main.py

`main.py` 是当前推荐的游戏启动入口。

基本流程：

```text
启动
 ↓
检查存档
 ↓
读档 / 创建角色
 ↓
选择门派
 ↓
保存
 ↓
显示当前地点
 ↓
进入游戏主循环
```

主循环：

```text
读取输入
 ↓
parse_command()
 ↓
CMD_MAP
 ↓
判断指令
 ↓
调用对应系统
```

---

# 27. 当前主要指令

### 移动

```text
n
s
e
w
```

或者：

```text
north
south
east
west
```

### 观察

```text
look
look <目标>
```

### 地图

```text
map
m
```

### 背包

```text
inventory
i
```

### 状态

```text
status
st
```

### 对话

```text
talk
talk <NPC>
talk <NPC> <话题>
```

### 战斗

```text
kill <目标>
attack <目标>
```

### 任务

```text
quests
jiequ <任务>
jiaofu <任务>
```

### 装备

```text
wield <武器>
wear <防具>
use <药品>
```

### 商店

```text
shop
buy <物品>
sell <物品>
```

### 打铁

```text
forge
```

### 恢复

```text
heal
dazuo
```

### 系统

```text
save
load
reload
help
quit
```

---

# 28. 指令别名系统

指令通过：

```text
CMD_MAP
```

进行标准化。

例如：

```text
n → 北
s → 南
e → 东
w → 西

l → look
i → inventory
st → status

k → kill
attack → kill
fight → kill

quest → quests
renwu → quests

m → map
ditu → map
```

新增命令时，应优先考虑：

```text
正式命令
+
英文别名
+
中文别名
+
单字快捷键
```

---

# 29. 地图渲染系统 MapEngine

MapEngine 负责把房间数据转换成终端地图。

核心结构：

```text
ROOMS
 ↓
MapEngine
 ↓
room_coords
 ↓
coord_to_room
 ↓
ASCII 地图
```

它支持：

```text
Zone
坐标
方向
房间
跨区域出口
```

地图渲染时只显示玩家当前 Zone。

---

# 30. 动态坐标布局

不是所有房间都必须手动填写坐标。

MapEngine 支持：

```text
已有坐标
    +
出口关系
    ↓
BFS 自动布局
```

但是：

> **重要城市、道路、关键建筑最好手动指定 coord。**

因为自动布局只保证基本连通和避免冲突，不等于它一定符合设计者心目中的城市空间结构。

---

# 31. 跨 Zone 地图

如果：

```text
A 房间 zone = main
B 房间 zone = gui yun
```

二者之间仍然可以：

```text
A --东--> B
```

此类出口应该理解为：

> **区域传送 / Zone 边界出口**

而不是普通的同 Zone 邻接关系。

---

# 32. 重要：wuxia.py 的特殊地位

仓库中存在：

```text
wuxia.py
```

这个文件非常大，并且包含大量与当前模块化架构重复的代码。

其中包括：

```text
Player
MapEngine
CMD_MAP
parse_command
look
存档
游戏逻辑
```

因此它与：

```text
main.py
engine.py
player.py
combat.py
actions.py
```

存在明显重复。

---

# 33. AI 修改 wuxia.py 的规则

默认情况下：

> **不要继续向 `wuxia.py` 添加新游戏功能。**

除非用户明确要求：

```text
修改旧版单文件实现
```

或者：

```text
兼容旧版启动方式
```

否则：

```text
新功能
    ↓
main.py
player.py
combat.py
actions.py
engine.py
data/*.json
```

优先级高于：

```text
wuxia.py
```

---

# 34. 当前项目的一个重要技术债务

未来如果项目继续发展，应该考虑最终处理：

```text
wuxia.py
```

与：

```text
模块化架构
```

的重复问题。

可能方案：

### 方案 A

保留作为：

```text
legacy / backup
```

不再修改。

### 方案 B

最终删除。

### 方案 C

把它彻底改造成兼容启动入口。

但在没有明确迁移计划之前：

> **不要贸然删除。**

因为它可能承担历史代码、兼容逻辑或旧存档行为参考作用。

---

# 35. 存档系统

存档主要由：

```text
player.py
```

负责。

保存的核心信息包括：

```text
name
sect
level
exp
exp_to_level
hp
max_hp
mp
max_mp
atk
defense
gold
inventory
equipment
equip_enhance
location
active_quests
completed_quests
```

读档时还会处理：

```text
LEGACY_LOCATION_MAP
```

因此：

> **修改房间 ID 时必须考虑旧存档兼容。**

---

# 36. 修改 room_id 的危险

例如：

```text
village_gate
```

改成：

```text
qing_shi_village_gate
```

表面上只是改名字。

实际上会影响：

```text
存档
NPC
出口
任务
地图
事件
代码中的 location
```

因此：

> **不要随意修改已有 room_id。**

如果必须改：

```text
旧 ID
 ↓
LEGACY_LOCATION_MAP
 ↓
新 ID
```

---

# 37. 扩建地图的推荐流程

以后增加一个城市，推荐严格按照以下顺序。

## 第一步：设计 Zone

例如：

```text
guiyun_city
```

## 第二步：设计城市房间

例如：

```text
guiyun_gate
guiyun_main_street
guiyun_east_market
guiyun_west_market
guiyun_inn
guiyun_yamen
guiyun_blacksmith
guiyun_martial_hall
```

## 第三步：设计坐标

例如：

```text
城门        [0,0]
主街        [1,0]
东市        [2,0]
西市        [0,1]
客栈        [1,1]
县衙        [2,1]
```

## 第四步：设计出口

确保：

```text
东 ↔ 西
北 ↔ 南
```

## 第五步：加入 NPC

## 第六步：加入敌人

## 第七步：加入商店

## 第八步：加入任务

## 第九步：加入城市剧情

## 第十步：运行地图验证

---

# 38. 新增房间的最小检查清单

每增加一个房间，检查：

```text
[ ] room_id 唯一
[ ] name 存在
[ ] zone 正确
[ ] desc 存在
[ ] coord 不冲突
[ ] exits 中目标存在
[ ] 对向出口正确
[ ] 坐标与方向一致
[ ] NPC 名称存在
[ ] enemy 名称存在
[ ] forage 物品存在
```

---

# 39. 新增 NPC 的最小检查清单

```text
[ ] NPC ID 唯一
[ ] title
[ ] desc
[ ] type
[ ] dialogue
[ ] info
[ ] 所在 room 已加入 npcs
[ ] shop 中的物品存在
[ ] quests 中的任务存在
```

---

# 40. 新增物品的最小检查清单

```text
[ ] item ID 唯一
[ ] type 正确
[ ] desc
[ ] price
[ ] weapon → atk
[ ] armor → defense
[ ] consumable → effect
[ ] material → 用途明确
```

---

# 41. 新增敌人的最小检查清单

```text
[ ] enemy ID 唯一
[ ] hp
[ ] atk
[ ] defense
[ ] exp
[ ] gold
[ ] skills
[ ] drops
[ ] 所有 drop item 存在
[ ] 所有 skill 字段合法
[ ] 房间 enemies 已引用
```

---

# 42. 新增任务的最小检查清单

```text
[ ] quest ID 唯一
[ ] title
[ ] npc
[ ] target_type
[ ] target_name
[ ] required_cnt
[ ] reward
[ ] desc
[ ] NPC quests 已引用
```

---

# 43. 当前游戏世界

当前基础世界以：

```text
青石村
```

为起点。

主要区域关系大致为：

```text
青石村
 │
 ├── 村中广场
 │   ├── 百草堂
 │   ├── 打铁铺
 │   ├── 村南街
 │   └── 村北街
 │
 ├── 客栈
 │
 ├── 杂货铺
 │
 ├── 古庙
 │
 └── 黄土官道
        │
        └── 村后荒野
              │
              └── 黑风山道
                    │
                    └── 山贼寨门
                          │
                          └── 黑风寨 Zone
```

黑风寨内部：

```text
寨内演武场
├── 哨塔
├── 水牢
└── 聚义厅
      ├── 宝库
      └── 黑风后山
```

---

# 44. 当前示例主线

当前已有一个完整的基础任务：

```text
清剿黑风山
```

基本关系：

```text
村长
 ↓
发布任务
 ↓
前往黑风山
 ↓
击败山贼二当家
 ↓
回村交付
 ↓
获得奖励
```

奖励包括：

```text
经验
银两
玄铁重剑
```

因此这个任务可以作为未来任务设计的最小参考模板。

---

# 45. 当前经济系统

游戏存在：

```text
gold
```

即银两。

经济来源：

```text
击杀敌人
出售物品
任务奖励
```

经济消耗：

```text
购买物品
装备强化
```

未来扩展经济系统时，不应只增加一个货币字段。

可以逐渐形成：

```text
铜钱
银两
金锭
门派贡献
声望
特殊货币
```

但必须在 `Player`、交易、任务、存档和 UI 中统一设计。

---

# 46. 当前打造 / 强化系统

铁匠可以强化：

```text
weapon
armor
```

强化消耗：

```text
铁矿石
+
银两
```

强化效果：

```text
武器：
每级增加攻击

防具：
每级增加防御
```

以后增加：

```text
武器等级
品质
耐久
附魔
锻造材料
特殊词条
```

时，应避免把所有逻辑塞入 `actions.py`。

最好逐步抽出：

```text
forge.py
equipment.py
```

---

# 47. 当前恢复系统

玩家可以：

```text
heal
dazuo
```

恢复：

```text
HP
MP
```

在：

```text
古庙
```

中恢复效果更强，并且能够清除状态。

这说明：

> 地点数据已经可以影响游戏机制。

未来可以继续扩展：

```text
客栈 → 恢复 + 时间推进
医馆 → 状态治疗
温泉 → 特殊 Buff
门派驻地 → 门派修炼
```

---

# 48. AI 新功能开发原则

如果用户要求：

> “增加一个功能”

AI 不应该立即修改文件。

应该先判断它属于哪一层。

---

## 数据层

如果只是：

```text
新地图
新 NPC
新装备
新敌人
新任务
新技能
```

优先：

```text
data/*.json
```

---

## 玩家层

如果涉及：

```text
属性
成长
经验
装备计算
存档
```

修改：

```text
player.py
```

---

## 战斗层

如果涉及：

```text
伤害
回合
敌人 AI
状态
技能
战斗奖励
```

修改：

```text
combat.py
```

---

## 行为层

如果涉及：

```text
talk
shop
quest
use
forge
look
```

修改：

```text
actions.py
```

---

## 核心引擎层

如果涉及：

```text
数据加载
地图引擎
状态系统
核心全局机制
```

修改：

```text
engine.py
```

---

## 输入 / 主循环

如果涉及：

```text
新命令
快捷键
游戏流程
启动
退出
```

修改：

```text
main.py
```

---

# 49. AI 禁止做的事情

默认情况下禁止：

### 1. 把所有代码重新合并到一个文件

不要重新制造：

```text
wuxia.py
```

式的大型单文件。

---

### 2. 不经过检查直接改 room_id

这会破坏：

```text
地图
存档
任务
出口
```

---

### 3. 修改核心机制却只改 JSON

例如：

```text
新增 poison
```

不能只写：

```json
"effect": "poison"
```

还必须确认战斗引擎真的实现了 poison。

---

### 4. 创建不存在的引用

不要让：

```text
NPC → 不存在任务
任务 → 不存在 NPC
房间 → 不存在 NPC
敌人 → 不存在物品
掉落 → 不存在物品
技能 → 不存在机制
```

---

### 5. 未检查就重写整个 engine.py

`engine.py` 是核心基础设施。

对它的大规模修改风险非常高。

---

# 50. AI 推荐修改策略

推荐采用：

```text
阅读
 ↓
定位
 ↓
小范围修改
 ↓
验证
 ↓
运行
 ↓
再扩展
```

而不是：

```text
理解一半
 ↓
重写整个项目
```

---

# 51. 新功能实施标准

一个功能至少要检查：

```text
数据
+
逻辑
+
入口
+
UI
+
存档
+
兼容性
```

例如：

> 增加“声望系统”

不能只加：

```text
player.reputation
```

还应该考虑：

```text
Player
 ↓
save/load
 ↓
NPC
 ↓
任务
 ↓
商店
 ↓
剧情
 ↓
UI
```

---

# 52. 项目未来推荐架构

随着游戏扩大，可以逐步演化为：

```text
wuxia/
│
├── main.py
│
├── engine.py
│
├── player.py
│
├── combat.py
│
├── actions.py
│
├── map_engine.py
├── quest_engine.py
├── npc_engine.py
├── item_engine.py
├── equipment.py
├── dialogue.py
├── reputation.py
├── faction.py
├── event_engine.py
│
└── data/
    ├── rooms.json
    ├── npcs.json
    ├── items.json
    ├── enemies.json
    ├── skills.json
    ├── quests.json
    ├── factions.json
    ├── events.json
    └── ...
```

但：

> **不要为了架构漂亮而提前拆分。**

只有当某个模块真正变得复杂，才应该拆。

---

# 53. 世界扩展推荐路线

未来世界可以从：

```text
青石村
```

逐渐扩大为：

```text
青石村
 ↓
归云城
 ↓
州府
 ↓
江南
 ↓
中原
 ↓
北境
 ↓
西域
 ↓
海外
```

每一个大型城市建议成为独立 Zone。

例如：

```text
guiyun_city
linan_city
jiangbei_city
beiyuan
xiyu
```

---

# 54. 城市设计原则

一个城市最好至少拥有：

```text
城门
主街
市场
客栈
药铺
铁匠铺
官府
民居
特殊地点
```

大型城市可以继续增加：

```text
码头
赌坊
青楼
镖局
武馆
书院
寺庙
道观
地下黑市
帮派驻地
牢狱
城墙
贫民区
富人区
```

---

# 55. 城市 Zone 的推荐结构

例如：

```text
guiyun_city
│
├── gui_yun_gate
├── gui_yun_main_street
├── gui_yun_east_market
├── gui_yun_west_market
├── gui_yun_inn
├── gui_yun_medicine_shop
├── gui_yun_blacksmith
├── gui_yun_yamen
├── gui_yun_dock
├── gui_yun_martial_hall
└── gui_yun_back_alley
```

所有 room_id 必须唯一。

---

# 56. 世界观扩展原则

本项目目前属于轻量武侠 RPG。

未来如果加入更复杂世界观，应逐步建立：

```text
世界
 ↓
国家
 ↓
州府
 ↓
城市
 ↓
乡镇
 ↓
村庄
 ↓
地点
```

以及：

```text
门派
帮派
官府
商会
镖局
世家
宗族
地下势力
```

最终形成：

```text
地理系统
+
势力系统
+
人物系统
+
经济系统
+
任务系统
+
剧情系统
+
战斗系统
```

---

# 57. AI 接手项目时的阅读顺序

如果新的 AI 第一次接手本项目：

## 第一遍

先读：

```text
README.md
main.py
engine.py
```

理解：

```text
项目怎么启动
数据从哪里来
游戏循环怎么运行
```

## 第二遍

阅读：

```text
player.py
combat.py
actions.py
```

理解：

```text
玩家
战斗
行为
```

## 第三遍

阅读：

```text
data/*.json
```

理解：

```text
当前世界
```

## 最后

再阅读：

```text
wuxia.py
```

把它当作：

```text
旧架构 / 历史实现 / 兼容参考
```

而不是默认的当前主架构。

---

# 58. AI 接到新需求后的标准思维过程

例如用户说：

> “给归云城增加 30 个房间。”

AI 应该：

```text
1. 读取 README
2. 检查 engine.py 的 DataLoader
3. 检查 rooms.json
4. 检查 MapEngine Zone 机制
5. 规划 gui yun zone
6. 设计坐标
7. 设计出口
8. 检查双向关系
9. 增加 NPC
10. 增加必要的敌人
11. 增加任务
12. 验证引用
13. 再修改
```

而不是：

```text
直接把 30 个房间塞进 engine.py
```

---

# 59. AI 输出代码时的原则

如果用户要求：

> “给我完整代码。”

必须：

```text
给完整文件
```

不要只给：

```text
“把这里替换一下”
```

因为用户可能不是程序员。

如果用户要求：

> “给我完整 JSON。”

必须输出：

```text
完整 JSON
```

并保证：

```text
合法 JSON
```

而不是伪 JSON。

---

# 60. JSON 修改原则

所有 JSON 必须：

```text
UTF-8
ensure_ascii=False 风格
双引号
无尾逗号
结构完整
```

不要加入：

```text
// 注释
```

因为标准 JSON 不支持注释。

---

# 61. 扩展大型地图时的推荐方式

不要一次性凭空生成数百个房间。

推荐：

```text
Zone 设计
 ↓
主干道路
 ↓
关键建筑
 ↓
支路
 ↓
隐藏地点
 ↓
NPC
 ↓
任务
 ↓
敌人
 ↓
经济
 ↓
剧情
```

地图应该首先满足：

```text
空间合理
```

然后再增加：

```text
内容密度
```

---

# 62. 地图质量标准

一个成熟 Zone 至少应检查：

```text
空间连续
方向正确
出口互逆
坐标合理
无孤立房间
无死循环问题
无重复 room_id
跨 Zone 出口明确
关键地点可到达
玩家出生点可正常进入
```

---

# 63. 游戏内容质量标准

新增内容不应该只是：

```text
名字
+
一句描述
```

至少应该包含：

```text
身份
功能
关系
位置
行为
奖励
风险
剧情用途
```

例如一个 NPC：

```text
名字
身份
所属势力
所在地点
对白
情报
商店
任务
好感
敌对关系
剧情作用
```

随着系统成熟逐步增加。

---

# 64. 未来推荐增加的系统

优先级建议：

## P0

```text
地图验证器
数据引用验证器
更完整任务系统
```

## P1

```text
NPC 好感
声望
门派
势力关系
剧情事件
```

## P2

```text
时间系统
天气
昼夜
随机事件
城市状态
```

## P3

```text
世界事件
动态 NPC
经济波动
势力战争
```

---

# 65. 最值得优先补强的技术能力

目前项目继续扩大以后，最容易出现的问题不是“没有内容”，而是：

```text
数据越来越多
 ↓
引用越来越复杂
 ↓
人工维护越来越困难
```

因此未来非常推荐增加：

```text
validate_data.py
```

自动检查：

```text
room 引用
NPC 引用
item 引用
enemy 引用
quest 引用
skill 引用
Zone
坐标
出口
存档兼容
```

---

# 66. 推荐的数据验证报告

未来可以让：

```text
python validate_data.py
```

输出：

```text
=== WUXIA DATA VALIDATOR ===

Rooms:
  OK: 126
  Broken: 0

NPC:
  OK: 48
  Broken: 0

Items:
  OK: 97
  Broken: 0

Enemies:
  OK: 42
  Broken: 0

Quests:
  OK: 36
  Broken: 0

Map:
  Broken exits: 0
  Coordinate conflicts: 0
  One-way exits: 0

Save compatibility:
  Legacy locations: OK

RESULT: PASS
```

---

# 67. 当前项目开发哲学

本项目不应该变成：

> “不断堆功能的 Python Demo”。

而应该逐渐变成：

> **一个数据驱动、模块化、可以不断扩建武侠世界的文字 RPG 引擎。**

核心思想：

```text
代码负责规则
数据负责世界
玩家负责状态
地图负责空间
任务负责目标
NPC 负责关系
战斗负责冲突
剧情负责意义
```

---

# 68. AI 最终记忆版

如果只能记住 10 条，请记住：

```text
1. main.py 是当前推荐入口。

2. engine.py 是核心数据与地图引擎。

3. player.py 管玩家状态、成长、装备和存档。

4. combat.py 管战斗。

5. actions.py 管观察、NPC、任务、交易、装备等行为。

6. data/*.json 是主要世界内容扩展入口。

7. room_id 不要随意修改，否则会影响存档和引用。

8. 新地图必须同时考虑 zone、coord、exits 和反向出口。

9. wuxia.py 默认视为旧的/重复的单文件实现，不要继续往里面堆新功能。

10. 修改前先理解架构，修改后检查引用、地图、存档和运行流程。
```

---

# 69. AI 新会话接管提示

当一个新的 AI 第一次接手本项目时，可以把下面这段作为最高优先级项目上下文：

```text
你正在维护一个 Python 中文武侠文字 RPG 项目。

请先阅读仓库根目录 README.md。

当前项目采用模块化架构：

main.py
    游戏入口、主循环、命令解析

engine.py
    核心数据加载、默认数据、ROOMS/NPCS/ITEMS/ENEMIES/SKILLS/QUESTS、MapEngine、状态与基础引擎

player.py
    Player、属性、成长、装备计算、存档与读档

combat.py
    回合制战斗、技能、敌人 AI、状态效果、战斗奖励

actions.py
    look、talk、quest、shop、buy、sell、equip、use、forge 等玩家行为

data/
    rooms.json
    npcs.json
    items.json
    enemies.json
    skills.json
    quests.json

wuxia.py 是旧的/重复的单文件实现。
除非明确要求，否则不要基于 wuxia.py 添加新功能。

扩展世界内容时优先修改 data/*.json。
扩展游戏机制时再修改对应 Python 模块。

任何地图修改必须检查：
1. room_id 唯一
2. zone 正确
3. coord 合理
4. exits 目标存在
5. 出口双向一致
6. 方向与坐标一致
7. NPC / enemy / item / quest 引用存在
8. 旧存档兼容

不要为了增加一个功能而重写整个项目。
优先小范围修改。
不要破坏已有功能。
```

---

# 70. 项目长期目标

最终希望形成：

```text
                 ┌──────────────┐
                 │   武侠世界   │
                 └──────┬───────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
      地图             人物             势力
        │               │               │
      Zone             NPC             门派
        │               │               │
      房间             对话             声望
        │               │               │
      地点             任务             关系
        └───────────────┼───────────────┘
                        │
                    游戏规则
                        │
          ┌─────────────┼─────────────┐
          │             │             │
         战斗          经济          成长
          │             │             │
         武功          商店          等级
         状态          打造          属性
          │             │             │
          └─────────────┼─────────────┘
                        │
                      玩家
                        │
                      存档
```

最终目标不是让代码越来越大。

而是让：

> **世界可以无限扩展，而核心规则保持稳定。**

---

# 71. 文档维护规则

以后每次完成重大架构变化，都应该同步更新本 README。

至少更新：

```text
[ ] 文件结构
[ ] 模块职责
[ ] 数据结构
[ ] 地图规则
[ ] 新增系统
[ ] 存档结构
[ ] AI 开发规则
```

README 本身应该被视为：

```text
项目知识库
+
AI 上下文
+
架构说明书
+
开发规范
```

而不仅仅是 GitHub 首页介绍。

---

# 72. 当前版本状态

当前项目属于：

```text
早期可运行武侠 RPG
+
模块化重构阶段
+
数据驱动扩展阶段
```

已经具备：

```text
✓ 玩家
✓ 门派
✓ 等级
✓ HP / MP
✓ 攻击 / 防御
✓ 装备
✓ 装备强化
✓ 背包
✓ 物品
✓ 商店
✓ 交易
✓ NPC
✓ NPC 对话
✓ 情报查询
✓ 任务
✓ 战斗
✓ 武功
✓ 状态效果
✓ 敌人技能
✓ 掉落
✓ 资源采集
✓ 地图
✓ Zone
✓ 坐标
✓ 动态地图渲染
✓ 存档
✓ 旧位置兼容
✓ JSON 数据加载
✓ 热重载
```

下一阶段重点不是简单增加更多 Python 代码，而是：

```text
提高数据规模
+
提高系统之间的关联
+
提高地图规模
+
提高剧情深度
+
提高数据验证能力
+
逐步解决旧架构重复
```

---

# 73. 结语

这是一个可以继续成长的武侠 RPG 基础项目。

未来所有 AI 修改都应该遵循：

> **先理解世界，再修改规则；先保护现有系统，再增加新内容；先保持数据一致，再追求功能数量。**

如果未来项目继续扩展到大型城市、多个 Zone、几十个 NPC、数百个房间、复杂任务链和势力系统，本 README 应继续作为 AI 的第一份项目上下文。

**README 是项目记忆。**

**`data/` 是世界。**

**`engine.py` 是规则基础。**

**`main.py` 是入口。**

**模块化代码是骨架。**

**玩家、NPC、任务、地图和剧情共同组成真正的江湖。**
