# ARCHITECTURE.md

# Wuxia 当前技术架构说明

> 本文件描述当前真实代码架构，并明确已知限制。
> “未来理想架构”统一标记为 `[PLANNED]`。

---

# 1. 总体结构

当前项目可以抽象为：

```text
                 main.py
                    │
        ┌───────────┼───────────┐
        ↓           ↓           ↓
    actions.py   combat.py   player.py
        │           │           │
        └───────────┼───────────┘
                    ↓
                 engine.py
                    │
                    ↓
                data/*.json
```

此外存在：

```text
wuxia.py
```

它属于历史遗留的大型实现。

---

# 2. Runtime 层

## 2.1 `main.py`

入口层。

主要职责：

```text
程序启动
命令解析
命令分发
主循环
移动
地图
保存/加载
reload
heal
help
```

### 当前特点

`main.py` 仍承担部分具体游戏逻辑，例如 heal。

### [TECH DEBT]

随着系统扩大，main.py 会逐渐变成“超级控制器”。

---

# 3. 游戏动作层

## 3.1 `actions.py`

当前负责：

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

它直接使用：

```text
ROOMS
NPCS
ITEMS
QUESTS
```

等 engine 数据。

### [TECH DEBT]

这些数据通过：

```python
from engine import ...
```

导入。

这会与 reload 产生引用一致性问题。

---

# 4. 战斗层

## 4.1 `combat.py`

负责：

```text
combat()
handle_attack()
```

以及：

- 玩家回合
- 敌人回合
- 技能
- 物品
- 逃跑
- 状态
- 奖励

---

# 5. 角色层

## 5.1 `player.py`

`Player` 是当前玩家状态核心。

主要状态：

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

# 6. 数据层

## 6.1 JSON 文件

```text
rooms.json
npcs.json
items.json
enemies.json
skills.json
quests.json
save.json
```

### 当前角色

这些文件是内容数据，不是数据库。

---

# 7. DataLoader

`engine.py` 中的 `DataLoader`：

```text
默认数据
    ↓
JSON
    ↓
deep_merge
    ↓
GAME_DATA
```

---

# 8. deep_merge 的真实语义

概念上：

```python
dict + dict → 递归合并
list + list → 后者替换
scalar + scalar → 后者替换
```

### [LIMITATION]

没有 schema-aware merge。

例如：

```text
quests list
skills list
items list
```

不能假设会自动追加。

---

# 9. MapEngine

`MapEngine` 当前负责：

```text
读取 Room
建立布局
坐标
出口
自动摆放
ASCII 地图
当前房间高亮
跨 Zone 门标记
```

---

# 10. MapEngine 坐标模型

方向：

```text
北 = (0, 1)
南 = (0,-1)
东 = (1, 0)
西 = (-1,0)
```

Room 坐标是地图渲染的重要辅助信息。

---

# 11. MapEngine 自动布局

如果 Room 没有有效显式坐标：

```text
根据已有 Room
+
exits
+
方向向量
```

进行 BFS / 邻近位置推断。

---

# 12. 地图引擎不是验证器

这是当前最容易被误解的地方。

### [LIMITATION]

MapEngine 当前没有完整 validator。

它可能：

- 自动处理部分无坐标房间
- 自动处理重复坐标导致的未定位房间

但这不等于：

```text
地图错误被检测出来
```

---

# 13. 地图需要独立 Validator

### [PLANNED]

未来建议新增：

```text
tools/map_validator.py
```

检查：

```text
Room ID
Zone
Exit target
反向出口
方向一致性
坐标冲突
孤立 Room
跨 Zone 出口
未知 Zone
```

输出：

```text
ERROR
WARNING
INFO
```

但目前尚未实现。

---

# 14. Zone

当前 Zone：

```text
main
bandit_zone
```

Zone 显示名目前在：

```text
MapEngine.ZONE_NAMES
```

中硬编码。

### [LIMITATION]

新增 Zone 后：

```text
rooms.json
```

不是唯一修改点。

---

# 15. Zone 的未来架构

### [PLANNED]

未来应逐渐数据化：

```json
{
  "id": "guiyun_city",
  "name": "归云城",
  "description": "...",
  "entry_rooms": [...]
}
```

但当前还没有独立 `zones.json`。

---

# 16. 跨 Zone

当前 Room exit 可以指向另一个 Zone 的 Room。

例如：

```text
main/cave_entrance
        ↓
bandit_zone/bandit_courtyard
```

跨 Zone 在世界设计上应理解为：

```text
边界 / 门 / 洞口 / 山口 / 城门
```

而不是普通房间跳转。

---

# 17. NPC

NPC 数据当前包含：

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

NPC 与 Room 通过 ID 关联。

---

# 18. 任务

当前任务数据是轻量模型。

例如：

```text
npc
target_type
target_name
required_cnt
reward
desc
```

当前实现主要围绕：

```text
击杀目标
计数
交付
奖励
```

---

# 19. 战斗

当前战斗流程：

```text
进入 combat
    ↓
deepcopy enemy
    ↓
处理玩家状态
    ↓
玩家行动
    ↓
敌人行动
    ↓
循环
    ↓
胜利 / 失败 / 逃跑
```

---

# 20. 战斗伤害

玩家技能主要基于：

```text
player.get_total_atk()
×
skill.power
-
enemy.defense
```

并至少造成 1 点伤害。

敌人技能类似。

---

# 21. 战斗状态

当前：

```text
p_statuses_global
```

用于玩家状态。

敌人状态为当前战斗局部数据。

### [TECH DEBT]

这是一个全局状态设计。

如果未来出现：

```text
多人
队伍
召唤物
多场战斗
战斗嵌套
```

会逐渐成为限制。

---

# 22. 状态效果

当前：

```text
poison
bleed
stun
shield
```

定义于 engine。

状态处理：

```text
add_status
process_status_effects
format_statuses
apply_shield
```

---

# 23. 角色成长

Player 升级：

```text
+ max_hp
+ max_mp
+ atk
+ defense
```

并恢复生命/内力。

经验需求：

```text
旧阈值 × 1.5
```

---

# 24. 装备

当前：

```text
weapon
armor
```

计算：

```text
total_atk
total_defense
```

会加入：

```text
装备属性
+
强化属性
```

---

# 25. 强化

强化入口：

```text
blacksmith
```

当前：

```text
上限 +5
铁矿石
金币
```

每次强化增加对应装备属性。

---

# 26. 存档架构

当前存档：

```text
data/save.json
```

保存：

```text
player
inventory
equipment
location
quests
version
```

---

# 27. Save Version

当前：

```text
SAVE_VERSION = 10
```

### [LIMITATION]

这不是完整迁移框架。

当前主要是：

```text
缺字段默认值
+
旧地点映射
+
无效地点回退
```

未来不能把：

```text
version
```

误解为：

```text
Migration System
```

---

# 28. Legacy Location

当前存在：

```text
cave → cave_entrance
bandit_camp → bandit_courtyard
```

这说明项目已经有历史 ID 兼容需求。

### [RULE]

不要随意删除旧 ID 映射。

---

# 29. 热重载

当前：

```text
reload_game_data()
```

会重新加载 JSON 并重建：

```text
MAP_ENGINE
```

### 但是

其他模块存在：

```python
from engine import ROOMS
```

等静态引用。

### [TECH DEBT]

所以 reload 不是严格意义上的依赖注入式热更新。

---

# 30. 当前架构的主要风险

## 风险 A：数据引用过早绑定

```text
from engine import ROOMS
```

造成 reload 风险。

---

## 风险 B：engine 责任过多

同时承担：

```text
默认数据
数据加载
地图
状态
渲染
全局变量
```

---

## 风险 C：main.py 责任过多

主循环之外仍有部分具体逻辑。

---

## 风险 D：wuxia.py 重复实现

容易导致：

```text
旧逻辑
新逻辑
```

分叉。

---

## 风险 E：缺少 Validator

JSON 可以加载，不代表世界数据逻辑正确。

---

# 31. 推荐的渐进式未来架构

### [PLANNED]

不是立即重写。

建议逐步演进：

```text
main.py
  ↓
Command Router
  ↓
Services
 ├── WorldService
 ├── CombatService
 ├── QuestService
 ├── InventoryService
 ├── EconomyService
 └── SaveService
  ↓
Domain Objects
 ├── Player
 ├── Room
 ├── NPC
 ├── Item
 ├── Enemy
 ├── Quest
 └── Skill
  ↓
Data Repository
  ↓
JSON
```

---

# 32. 推荐未来数据结构

### [PLANNED]

未来可以逐步增加：

```text
data/zones.json
data/shops.json
data/dialogues.json
data/world_states.json
```

但没有明确需求时不要提前大规模拆分。

---

# 33. 世界内容与代码的边界

正确：

```text
“归云城有哪些店铺”
→ WORLD_DESIGN.md + JSON
```

错误：

```text
“归云城有哪些店铺”
→ 在 main.py 写 500 行 if
```

---

# 34. 架构演进原则

```text
旧代码能运行
      ↓
先数据化
      ↓
再抽服务
      ↓
再抽领域对象
      ↓
最后考虑框架化
```

不要：

```text
发现问题
  ↓
整个项目重写
```

---

# 35. 当前架构结论

本项目当前属于：

```text
“模块化的可玩原型 / 早期 RPG 框架”
```

而不是：

```text
成熟通用 RPG Engine
```

它已经具备继续扩展的基础，但下一阶段重点应是：

```text
数据稳定
+
地图质量
+
世界内容
+
ID 兼容
+
逐步消除技术债
```
