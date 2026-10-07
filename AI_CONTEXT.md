# AI_CONTEXT.md

# Wuxia AI 开发上下文与接管规范

> 本文件是未来 AI 接手 `happyhgq/wuxia` 时的最高优先级项目说明之一。
> 它描述“现在真实存在什么”“修改时必须遵守什么”，不把未来规划伪装成现状。

---

# 1. 项目身份

项目：

```text
Wuxia · 武侠文字 RPG
```

仓库：

```text
happyhgq/wuxia
```

技术形态：

```text
Python
+
终端交互
+
JSON 数据
+
房间地图
+
轻量 RPG 系统
```

当前主要入口：

```text
main.py
```

---

# 2. AI 必须先区分五种状态

所有理解和修改必须区分：

### [CURRENT]

当前代码真实存在，并已经参与运行。

### [LIMITATION]

当前虽然能运行，但能力不完整。

### [TECH DEBT]

当前设计可以工作，但继续扩展会造成问题。

### [PLANNED]

设计目标，尚未实现。

### [RULE]

未来修改不得违反的项目规则。

---

# 3. AI 接手项目后的固定阅读顺序

不要直接开始改代码。

必须按：

```text
README.md
    ↓
AI_CONTEXT.md
    ↓
ARCHITECTURE.md
    ↓
WORLD_DESIGN.md
    ↓
data/*.json
    ↓
相关 Python 文件
```

如果任务是战斗：

```text
combat.py
engine.py
player.py
data/enemies.json
data/skills.json
```

如果任务是地图：

```text
engine.py
data/rooms.json
WORLD_DESIGN.md
```

如果任务是 NPC / 任务：

```text
actions.py
engine.py
data/npcs.json
data/quests.json
```

---

# 4. 当前真实架构

```text
                  ┌──────────────┐
                  │   main.py    │
                  │ 主循环/命令   │
                  └──────┬───────┘
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │ actions.py │ │ combat.py  │ │ player.py  │
   │ 游戏动作    │ │ 战斗        │ │ 玩家        │
   └──────┬─────┘ └──────┬─────┘ └──────┬─────┘
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                  ┌────────────┐
                  │ engine.py  │
                  │ 数据/地图/状态│
                  └──────┬─────┘
                         ↓
                    data/*.json
```

注意：

> 这是当前依赖关系的概括，不代表理想架构。

---

# 5. 文件职责

## `main.py`

### [CURRENT]

负责：

- 程序入口
- 命令映射
- 主循环
- 移动
- 保存 / 读取
- help
- map
- reload
- heal
- 部分玩家操作分发

### [RULE]

不要把所有新玩法继续堆进 `main.py`。

如果是：

- 对话
- 任务
- 商店
- 装备
- 使用物品

优先考虑 `actions.py`。

如果是战斗：

```text
combat.py
```

---

# 6. `engine.py`

### [CURRENT]

负责：

- 默认数据
- DataLoader
- 全局游戏数据
- MapEngine
- 状态效果
- 地图渲染
- 数据重载

---

# 7. `player.py`

### [CURRENT]

负责：

- Player
- 属性
- 门派
- 升级
- 装备属性计算
- 任务进度
- save/load

---

# 8. `combat.py`

### [CURRENT]

负责：

- 回合制战斗
- 普攻
- 技能
- 物品
- 逃跑
- 敌人技能
- 状态效果
- 战斗胜负
- 奖励

### [LIMITATION]

当前战斗并不是独立 `CombatState` 架构。

玩家状态使用：

```text
p_statuses_global
```

全局容器。

### [TECH DEBT]

未来复杂化时应逐渐改成：

```text
CombatState
 ├── player
 ├── enemies
 ├── turns
 ├── statuses
 └── battle_result
```

但除非任务明确要求，不要一次性重写整个战斗系统。

---

# 9. `actions.py`

### [CURRENT]

负责：

```text
look
talk
ask
quest
trade
equipment
consumable
forge
```

---

# 10. `wuxia.py`

### [TECH DEBT]

这是历史遗留的大型重复实现。

它不是当前推荐的新功能入口。

### [RULE]

默认：

```text
禁止新增核心玩法到 wuxia.py
```

除非任务本身就是：

- 清理旧代码
- 迁移旧功能
- 比较旧新实现
- 删除遗留实现

---

# 11. JSON 数据规则

当前 DataLoader 支持：

```text
rooms
npcs
items
enemies
skills
quests
```

---

## 11.1 ID 是长期资产

以下 ID 视为稳定标识：

```text
room id
npc id
item id
enemy id
skill id
quest id
```

### [RULE]

没有明确迁移计划，不得修改已有 ID。

错误示例：

```text
village_gate
```

改成：

```text
village_entrance
```

即使名字看起来更漂亮，也可能破坏：

- save
- exit
- NPC
- Quest
- location
- 其他引用

---

# 12. DataLoader 的真实行为

`deep_merge()` 递归合并 dict。

但：

```text
list
scalar
```

不是智能合并。

### [LIMITATION]

例如两个列表：

```json
["a", "b"]
```

和：

```json
["c"]
```

后者可能整体替换前者。

### [RULE]

新增 JSON 内容前必须确认实际结构。

不要假设：

```text
列表 = 自动追加
```

---

# 13. 地图规则

Room 是地图基本单位。

核心字段通常包括：

```text
id
name
zone
description
exits
npcs
enemies
safe
coord
```

---

# 14. Zone 规则

当前：

```text
main
bandit_zone
```

未来允许继续增加。

例如：

```text
guiyun_city
```

### [RULE]

Zone ID 必须稳定、唯一、英文/ASCII 化。

---

# 15. 当前地图引擎的重要限制

MapEngine：

- 支持坐标
- 支持出口
- 支持自动摆放部分房间
- 支持跨 Zone 门/出口显示

但它不是完整地图验证器。

### [LIMITATION]

目前不会系统性检查：

- 所有出口是否存在
- 是否所有出口双向
- 方向与坐标是否完全一致
- 重复坐标是否为设计错误
- Zone 是否都注册显示名

---

# 16. 地图修改时 AI 必须执行的检查

新增 Room 后至少检查：

```text
1. id 是否唯一
2. name 是否合理
3. zone 是否正确
4. exits 指向的 room 是否存在
5. 坐标是否冲突
6. 坐标是否符合出口方向
7. 是否需要反向出口
8. 是否跨 Zone
9. 是否需要安全区
10. 是否影响现有 save
```

---

# 17. 跨 Zone 设计

跨 Zone 不应该被当成普通随机传送。

应有明确世界语义：

```text
道路
城门
山口
洞口
渡口
关隘
```

例如：

```text
主世界
  ↓
黄土官道
  ↓
城门
  ↓
guiyun_city
```

---

# 18. 归云城专门规则

归云城未来必须是：

```text
guiyun_city
```

独立 Zone。

用户当前世界设计要求：

```text
主世界
  黄土官道
      ↓
另一个同名“黄土官道”
      ↓
归云城
```

两个同名 Room 可以存在。

但是：

```text
id 必须不同
```

例如：

```text
official_road_west
official_road_east
```

而显示名可以同为：

```text
黄土官道
```

### [RULE]

“显示名可以重复，内部 ID 不得重复”。

---

# 19. NPC 修改规则

NPC ID 稳定。

NPC 数据尽量包括：

```text
name
title
desc
type
dialogue
info
shop
quests
```

不要为了一个对话分支直接硬编码一大片逻辑。

优先数据化。

---

# 20. Quest 修改规则

当前任务系统是轻量结构。

典型：

```text
npc
target_type
target_name
required_cnt
reward
desc
```

### [LIMITATION]

暂不支持完整：

```text
多阶段任务
条件分支
世界状态
失败条件
时间限制
复杂任务链
```

如果要增加这些能力，应先设计 Quest schema，不要继续无规则堆字段。

---

# 21. 战斗规则

当前伤害是轻量公式。

技能主要受到：

```text
attack
power
defense
mp_cost
```

影响。

### [RULE]

修改伤害公式时必须同时考虑：

- 玩家普攻
- 玩家技能
- 敌人普攻
- 敌人技能
- 装备
- 防御
- 等级
- MP
- 状态效果

不要只改一个公式导致系统失衡。

---

# 22. 状态系统规则

当前：

```text
poison
bleed
stun
shield
```

### [RULE]

新增状态时必须同步：

```text
STATUS_EFFECTS
add_status
process_status_effects
format_statuses
```

并检查：

```text
玩家
敌人
战斗结算
```

---

# 23. 存档规则

当前：

```text
SAVE_VERSION = 10
```

### [LIMITATION]

没有通用 Migration Framework。

### [RULE]

增加 Player 字段时：

1. save 写入
2. load 默认值
3. 老存档兼容
4. 版本号是否需要增加
5. 旧存档字段缺失时不能崩溃

如果修改：

```text
location
inventory
equipment
quest
```

必须特别检查兼容性。

---

# 24. 热重载规则

当前存在：

```python
from engine import ROOMS
```

等模块级引用。

### [TECH DEBT]

`reload_game_data()` 重新绑定 `engine.ROOMS` 后，其他模块可能仍持有旧对象引用。

### [RULE]

任何修改 reload 的任务都必须检查：

```text
main.py
actions.py
combat.py
player.py
engine.py
```

不要仅修改 `reload_game_data()` 就宣称热重载彻底解决。

---

# 25. 修改策略

## 小改动

例如：

```text
新增 NPC
新增物品
新增敌人
新增任务
```

优先只改：

```text
data/*.json
```

---

## 中型改动

例如：

```text
新增一种交互
新增商店规则
新增装备行为
```

先找现有责任模块：

```text
actions.py
combat.py
player.py
```

---

## 大型改动

例如：

```text
Zone
城市
任务系统
战斗系统
世界状态
```

必须先更新：

```text
WORLD_DESIGN.md
ARCHITECTURE.md
```

再实现。

---

# 26. AI 禁止事项

### [RULE] 禁止

1. 未阅读相关代码就重写核心系统。
2. 随意改已有 ID。
3. 把中文显示名当内部 ID。
4. 把 `wuxia.py` 当新系统入口。
5. 把规划功能写成已经实现。
6. 声称 MapEngine 已经是完整验证器。
7. 声称 reload 已经彻底热更新。
8. 声称 save version 已经具备完整 migration。
9. 大量内容继续硬编码。
10. 为小功能顺手重构整个项目。

---

# 27. AI 修改后的检查

完成修改后至少回答：

```text
[ ] 是否破坏已有 ID？
[ ] 是否破坏 save？
[ ] 是否破坏 Room exit？
[ ] 是否破坏跨 Zone？
[ ] 是否破坏 combat？
[ ] 是否破坏 NPC / Quest 引用？
[ ] 是否需要更新文档？
[ ] 是否把 PLANNED 写成 CURRENT？
[ ] 是否把 TECH DEBT 当成已解决？
```

---

# 28. 未来目标架构

这不是当前实现。

属于：

```text
[PLANNED]
```

未来可以逐步演进到：

```text
Application
    │
    ├── Command System
    ├── World System
    │     ├── Zone
    │     ├── Room
    │     └── Travel
    │
    ├── Character System
    ├── Combat System
    ├── Quest System
    ├── Economy System
    ├── Save System
    └── Data System
```

但不应为了架构漂亮而一次性推翻当前可玩版本。

---

# 29. AI 最终原则

> **兼容优先，数据优先，渐进重构，真实状态优先。**

每次修改都应该让项目：

```text
更稳定
+
更容易扩展
+
更容易被下一次 AI 接手
```

而不是只让本次功能“看起来完成”。
