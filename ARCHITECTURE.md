# Wuxia — ARCHITECTURE.md

> 项目技术架构与数据流说明。
>
> 本文件回答：**“这个游戏内部是怎样工作的？”**

---

# 1. 总体架构

当前项目可以理解为五层：

```text
┌─────────────────────────────┐
│          用户输入            │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│          main.py            │
│  启动 / 主循环 / 指令分发     │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│       actions / combat      │
│   世界行为 / 战斗行为         │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│          player.py          │
│ 玩家状态 / 成长 / 装备 / 存档 │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│          engine.py          │
│ 数据加载 / 地图 / 公共机制     │
└──────────────┬──────────────┘
               ↓
┌─────────────────────────────┐
│          data/*.json        │
│ 世界内容                     │
└─────────────────────────────┘
```

注意：

这不是严格意义上的纯 MVC，而是一个逐步模块化形成的文字 RPG 架构。

---

# 2. 模块关系

## `main.py`

职责：

```text
程序入口
游戏初始化
主循环
输入
命令解析
命令分发
退出
```

它应该尽量负责：

> “什么时候做什么”

而不是负责：

> “所有事情具体怎么做”。

---

# 3. `actions.py`

职责：

```text
look
talk
ask
quest
jiequ
jiaofu
shop
buy
sell
wield
wear
use
forge
```

可以把它理解为：

> 玩家在世界里“做什么”。

典型调用：

```text
main.py
  ↓
action
  ↓
读取 engine 数据
  ↓
修改 Player
  ↓
输出结果
```

---

# 4. `combat.py`

职责：

```text
进入战斗
敌人初始化
玩家行动
普通攻击
技能攻击
敌人 AI
状态效果
胜负
经验
金钱
掉落
```

战斗数据主要来自：

```text
ENEMIES
SKILLS
ITEMS
Player
```

推荐的数据流：

```text
enemy_id
   ↓
ENEMIES[enemy_id]
   ↓
Combat
   ↓
battle state
   ↓
Player / enemy HP
   ↓
reward
```

---

# 5. `player.py`

Player 是运行时玩家状态容器。

典型状态包括：

```text
name
sect
level
exp
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

Player 同时承担：

```text
状态
属性计算
装备
存档
读档
成长
```

因此未来如果 Player 继续膨胀，应优先考虑拆分：

```text
equipment.py
save_system.py
progression.py
```

但在真正复杂到需要拆分前，不应为了形式上的“架构漂亮”而过早拆分。

---

# 6. `engine.py`

`engine.py` 是当前最重要的基础设施文件。

主要概念：

```text
DEFAULT_* 数据
DataLoader
ROOMS
NPCS
ITEMS
ENEMIES
SKILLS
QUESTS
MapEngine
公共游戏工具
```

它的核心定位：

> “提供整个游戏运行所需要的世界数据和底层规则”。

---

# 7. 数据加载层

推荐理解为：

```text
DEFAULT DATA
      │
      ├─────────────┐
      │             │
      ↓             ↓
data/*.json     fallback
      │
      └──────→ DataLoader
                    ↓
              Runtime Data
                    ↓
         ROOMS / NPCS / ...
```

数据加载设计的目标是：

```text
开发时有默认值
正式运行时可以外置 JSON
```

因此：

> 修改内容时优先考虑 `data/*.json`。

---

# 8. Runtime Data

运行时主要世界数据可以抽象成：

```python
ROOMS
NPCS
ITEMS
ENEMIES
SKILLS
QUESTS
```

关系：

```text
ROOMS
 ├── NPC 引用
 └── Enemy 引用

NPCS
 ├── Quest 引用
 └── Shop → Item 引用

QUESTS
 ├── NPC
 ├── Target
 └── Reward → Item

ENEMIES
 ├── Skill
 └── Drop → Item

SKILLS
 └── Combat Effect
```

因此整个项目实际上是一个：

> **跨 JSON 数据集合的引用图。**

---

# 9. 数据引用图

```text
                    ┌─────────┐
                    │  ROOMS  │
                    └────┬────┘
                         │
             ┌───────────┴───────────┐
             ↓                       ↓
          NPCS                    ENEMIES
             │                       │
        ┌────┴────┐             ┌────┴────┐
        ↓         ↓             ↓         ↓
      QUESTS    ITEMS         SKILLS    ITEMS
        │
        └──────────→ ITEMS
```

这意味着：

> 修改任何一个 JSON 都可能影响其他 JSON。

因此不能只验证“JSON 本身合法”，还必须验证“引用合法”。

---

# 10. 地图模型

地图基本单位：

```text
Room
```

一个 Room 可以理解成：

```text
Room
├── id
├── name
├── zone
├── desc
├── coord
├── exits
├── npcs
├── enemies
└── other gameplay metadata
```

---

# 11. Zone

Zone 是空间分区。

例如：

```text
main
bandit_zone
guiyun_city
```

Zone 的意义：

```text
地图显示边界
坐标空间
大型区域组织
跨区域入口
```

大型地图应该逐渐使用：

```text
一个大型世界
→ 多个 Zone
→ 每个 Zone 多个 Room
```

---

# 12. Room ID

Room ID 是机器引用标识。

推荐：

```text
guiyun_gate
guiyun_main_street
guiyun_inn
guiyun_yamen
```

不要使用：

```text
归云城门口
归云城主街
```

作为未来大型系统中的唯一机器 ID。

显示名称与机器 ID 分离：

```text
id: gui yun_gate
name: 归云城城门
```

---

# 13. 坐标系统

Room 可以拥有：

```text
coord: [x, y]
```

坐标主要用于：

```text
MapEngine
ASCII 地图
空间布局
出口方向验证
```

基本方向关系：

```text
东：x + 1
西：x - 1
北：y + 1
南：y - 1
```

具体实现必须以当前 `MapEngine` 为准。

---

# 14. 出口系统

出口：

```json
"exits": {
    "东": "target_room"
}
```

逻辑上建议保持：

```text
A --东--> B
B --西--> A
```

否则会形成：

```text
单向出口
```

除非设计目标就是单向传送、悬崖、门禁、剧情出口等。

---

# 15. MapEngine

MapEngine 的职责不是保存整个游戏世界。

它更像：

```text
ROOMS
 ↓
空间索引
 ↓
坐标映射
 ↓
地图渲染
 ↓
移动关系检查
```

应避免让 MapEngine 同时承担：

```text
NPC AI
任务系统
战斗
经济
剧情
```

---

# 16. 地图自动布局

当部分 Room 没有明确坐标时，可以根据出口关系推导布局。

概念上：

```text
已有坐标 Room
      ↓
BFS / 邻接关系
      ↓
推导其他 Room
      ↓
检查冲突
      ↓
渲染
```

但：

> 自动布局不是城市设计工具。

重要城市应优先人工设计关键坐标。

---

# 17. 跨 Zone 出口

例如：

```text
main
  黄土官道
       │
       │ 东
       ↓
guiyun_city
  归云城城门
```

这是：

```text
Zone Boundary
```

不是普通的同 Zone 房间邻接。

设计大型世界时应明确记录：

```text
起点 Zone
起点 Room
出口方向
目标 Zone
目标 Room
```

---

# 18. NPC 架构

NPC 是世界中的行为节点。

概念结构：

```text
NPC
├── 身份
├── 描述
├── 对话
├── 情报
├── 商店
├── 任务
└── 未来扩展：
    ├── 好感
    ├── 阵营
    ├── 时间表
    ├── 状态
    └── 剧情事件
```

NPC 的“存在”通常需要两层：

```text
NPC 数据定义
+
Room.npcs 引用
```

---

# 19. Quest 架构

任务可以抽象成：

```text
Quest
├── giver
├── target
├── target_type
├── required_count
├── reward
└── description
```

运行生命周期：

```text
未接取
  ↓
已接取
  ↓
进行中
  ↓
目标完成
  ↓
提交
  ↓
已完成
```

以后扩展复杂任务时，可以增加：

```text
前置任务
条件
分支
失败
时间限制
选择
声望
多目标
剧情触发
```

---

# 20. Combat 架构

战斗可以抽象为：

```text
Combat State
├── Player
├── Enemy
├── Turn
├── Skills
├── Status Effects
└── Rewards
```

回合：

```text
玩家行动
 ↓
伤害/效果
 ↓
敌人行动
 ↓
状态结算
 ↓
死亡检查
 ↓
下一回合
```

---

# 21. 战斗数据与战斗规则必须分离

推荐：

```text
JSON
    ↓
描述敌人“是谁”
    ↓
Combat
    ↓
决定敌人“怎么战斗”
```

例如：

```json
{
  "name": "毒牙",
  "power": 1.2,
  "effect": "poison"
}
```

JSON 描述技能。

`combat.py` 决定：

```text
poison
到底如何造成伤害
持续多久
如何结束
```

---

# 22. Player 与 Equipment

装备关系：

```text
Player
 ├── equipment
 │    ├── weapon
 │    └── armor
 │
 └── equip_enhance
```

最终属性应该来自：

```text
基础属性
+
装备属性
+
强化
+
其他 Buff
```

不要在不同模块中分别实现一套“总攻击力”。

必须保持唯一计算来源。

---

# 23. Save / Load

存档实际上是：

```text
Runtime Player State
        ↓
serialize
        ↓
JSON / save
```

读取：

```text
save
 ↓
deserialize
 ↓
兼容旧字段
 ↓
Player
```

未来增加字段时：

```text
新字段必须有默认值
```

这样旧存档才不会因为缺字段而崩溃。

---

# 24. 建议的未来存档版本

当前如果继续发展，推荐最终增加：

```json
{
  "save_version": 2,
  "player": {},
  "world": {}
}
```

然后：

```text
save_version 1
    ↓
migration
    ↓
save_version 2
```

这样以后增加：

```text
声望
时间
天气
世界事件
NPC 状态
```

仍可以兼容旧存档。

---

# 25. 推荐未来拆分

当前架构继续扩大后，可以逐步演化：

```text
main.py

engine.py
map_engine.py

player.py
equipment.py
progression.py
save_system.py

combat.py
status_effects.py

actions.py
dialogue.py
quest_engine.py
npc_engine.py

faction.py
reputation.py
event_engine.py
world_time.py
```

但只有在复杂度真正达到需要拆分时再执行。

---

# 26. 推荐的数据目录演化

当前：

```text
data/
├── rooms.json
├── npcs.json
├── items.json
├── enemies.json
├── skills.json
└── quests.json
```

未来可以演化：

```text
data/
├── world/
│   ├── zones.json
│   └── rooms.json
├── actors/
│   ├── npcs.json
│   └── enemies.json
├── items/
│   ├── items.json
│   ├── weapons.json
│   └── armor.json
├── combat/
│   ├── skills.json
│   └── effects.json
├── quests/
│   └── quests.json
├── factions/
│   └── factions.json
└── events/
    └── events.json
```

但这是未来规划，不代表当前必须马上重构。

---

# 27. 数据验证器

当数据量扩大到数百 Room / NPC / Quest 后，强烈建议增加：

```text
validate_data.py
```

至少验证：

```text
JSON syntax
ID uniqueness
room references
NPC references
enemy references
item references
skill references
quest references
exit symmetry
coordinate conflicts
zone validity
save compatibility
```

---

# 28. 推荐测试层次

未来应逐步建立：

## Level 1 — JSON

```text
json.loads()
```

## Level 2 — 引用

```text
所有 ID 都能解析
```

## Level 3 — 地图

```text
出口
坐标
Zone
```

## Level 4 — 单元逻辑

```text
伤害
升级
装备
任务
状态
```

## Level 5 — 冒烟测试

```text
创建角色
进入村庄
移动
交谈
接任务
战斗
获得奖励
装备
保存
退出
重新读取
```

---

# 29. 扩展大型城市的架构模板

例如归云城：

```text
Zone: guiyun_city

Rooms:
├── guiyun_gate
├── guiyun_main_street
├── guiyun_east_market
├── guiyun_west_market
├── guiyun_inn
├── guiyun_medicine_shop
├── guiyun_blacksmith
├── guiyun_yamen
├── guiyun_dock
├── guiyun_martial_hall
└── guiyun_back_alley
```

每个 Room 再连接：

```text
NPC
Enemy
Shop
Quest
Event
Forage
```

这样城市可以不断扩展，而不需要修改核心引擎。

---

# 30. 架构演化路线

### 阶段 1

当前：

```text
模块化 Python
+
JSON
```

### 阶段 2

加入：

```text
数据验证
存档版本
更完整任务
```

### 阶段 3

加入：

```text
Faction
Reputation
Event
World Time
```

### 阶段 4

加入：

```text
动态 NPC
动态世界
经济
城市状态
```

### 阶段 5

最终：

```text
数据驱动武侠 RPG Framework
```

---

# 31. 架构决策原则

以后出现架构争议时，优先顺序：

```text
稳定性
>
兼容性
>
可维护性
>
可扩展性
>
代码漂亮
```

不要为了“看起来高级”而破坏已有玩法。

---

# 32. 最终架构目标

最终理想状态：

```text
                 WUXIA WORLD
                      │
          ┌───────────┼───────────┐
          ↓           ↓           ↓
        SPACE       ACTORS      FACTIONS
          │           │           │
        Zone         NPC        Reputation
        Room        Player       Relations
          │         Enemy
          │
          └───────────┬───────────┘
                      ↓
                   SYSTEMS
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
      Combat        Quest          Event
        ↓             ↓             ↓
      Skills        Reward        Story
        │             │             │
        └─────────────┼─────────────┘
                      ↓
                    SAVE
```

核心原则：

> **世界内容应该越来越多，而核心代码应该越来越稳定。**

