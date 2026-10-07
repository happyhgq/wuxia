# Wuxia · 武侠文字 RPG

> 中文终端武侠 RPG。当前版本采用 Python + JSON 数据驱动，核心玩法包括房间探索、地图移动、NPC 对话、任务、交易、装备、强化、资源采集、回合制战斗、状态效果、角色成长与存档。

---

## 1. 项目定位

本项目是一个**可持续扩展的中文武侠文字 RPG**。

当前运行形态：

- 终端 / 命令行
- Python
- JSON 游戏数据
- 房间式地图
- Zone（区域）概念
- NPC / 对话 / 任务
- 商店 / 买卖
- 装备 / 强化
- 采集
- 回合制战斗
- 状态效果
- 角色升级
- JSON 存档

项目目前已经不是单文件原型，但也还不是成熟的通用 RPG 引擎。

**重要：本 README 描述的是当前真实实现，而不是目标架构。**

详细文档：

- `AI_CONTEXT.md`：未来 AI 接手本项目时必须遵守的开发规则。
- `ARCHITECTURE.md`：当前代码架构、数据流、依赖关系和技术债。
- `WORLD_DESIGN.md`：本游戏的世界观、地图设计、Zone 设计和内容扩展规则。

---

## 2. 当前状态标签

文档统一使用以下标签：

| 标签 | 含义 |
|---|---|
| `[CURRENT]` | 当前代码/数据已经存在并可使用 |
| `[LIMITATION]` | 当前实现存在明确限制 |
| `[TECH DEBT]` | 已知技术债，后续应重构 |
| `[PLANNED]` | 规划中的功能，不代表已经实现 |
| `[RULE]` | 后续开发必须遵守的规则 |

不要把 `[PLANNED]` 写成 `[CURRENT]`。

---

## 3. 当前项目结构

```text
wuxia/
├── README.md
├── AI_CONTEXT.md
├── ARCHITECTURE.md
├── WORLD_DESIGN.md
├── main.py
├── engine.py
├── player.py
├── combat.py
├── actions.py
├── wuxia.py
└── data/
    ├── rooms.json
    ├── npcs.json
    ├── items.json
    ├── enemies.json
    ├── skills.json
    ├── quests.json
    └── save.json
```

### 核心代码

| 文件 | 当前职责 |
|---|---|
| `main.py` | 程序入口、主命令循环、移动、保存/读取、部分玩家动作 |
| `engine.py` | 数据加载、默认数据、地图引擎、状态效果、全局运行时数据 |
| `player.py` | Player、属性、升级、装备计算、任务进度、存档读写 |
| `combat.py` | 回合制战斗、技能、敌人技能、状态处理、战斗结算 |
| `actions.py` | 查看、对话、任务、交易、装备、使用物品、锻造 |
| `wuxia.py` | `[TECH DEBT]` 旧的/重复的大型实现，不是当前默认扩展入口 |
| `data/*.json` | 游戏内容数据 |

---

## 4. 当前启动方式

项目当前以 `main.py` 为主要入口。

```bash
python main.py
```

如果仓库环境使用其他 Python 命令，应以实际环境为准。

---

## 5. 当前主要命令

主循环目前支持的核心命令包括：

```text
n / north       北
s / south       南
e / east        东
w / west        西

l / look        查看
m / map         地图
search          搜索/采集

i / inventory   背包
wield           装备武器
wear            装备防具
use             使用物品

kill / attack   战斗
flee            逃跑入口

talk / chat     对话
ask / 问        询问信息

quest / quests  任务
jiequ           接取任务
jiaofu          交付任务

shop / list     商店
buy             买
sell            卖

forge           打铁铺强化
heal / dazuo    恢复

status          状态
save            保存
load            读取
reload          重新加载游戏数据
help            帮助
q / quit        退出
```

具体命令行为以 `main.py` 当前代码为准。

---

## 6. 当前游戏循环

当前基本循环为：

```text
进入世界
  ↓
查看当前位置
  ↓
移动 / 查看 / 对话 / 任务 / 商店 / 采集
  ↓
遇敌
  ↓
回合制战斗
  ↓
获得经验、金币、掉落
  ↓
角色成长
  ↓
继续探索
  ↓
保存
```

当前不是完整开放世界模拟器。

---

## 7. 当前地图模型

地图由 `data/rooms.json` 驱动。

Room 是游戏世界的基本空间单位。

典型结构包括：

```json
{
  "id": "village_gate",
  "name": "村口",
  "zone": "main",
  "description": "...",
  "exits": {
    "北": "south_street"
  },
  "npcs": ["guard"],
  "enemies": [],
  "safe": true
}
```

### 当前 Zone

代码中目前明确存在：

```text
main
bandit_zone
```

`MapEngine.ZONE_NAMES` 当前也只硬编码了：

```text
main        → 主世界
bandit_zone → 黑风寨
```

因此：

> `[LIMITATION]` 新增 Zone 后，不能只添加 `rooms.json` 数据；当前地图显示名称还需要处理 `MapEngine.ZONE_NAMES`。

---

## 8. 当前地图机制的重要事实

### 8.1 坐标

Room 可以提供显式坐标。

MapEngine 会根据坐标和出口关系建立地图布局。

### 8.2 自动摆放

对于没有可用坐标的房间，MapEngine 会尝试根据出口关系自动摆放。

### 8.3 重复坐标

`[LIMITATION]` 当前重复坐标不会直接作为地图验证错误阻止加载，而可能进入自动重新摆放流程。

因此：

> 不要把当前 MapEngine 当作完整地图验证器。

### 8.4 出口

当前出口使用：

```text
北 / 南 / 东 / 西
```

并映射到坐标方向。

### 8.5 跨 Zone

当前存在跨 Zone 连接，例如：

```text
cave_entrance
    ↓
bandit_courtyard

bandit_back_mountain
    ↓
wild_fields
```

这类连接属于世界地图边界连接。

---

## 9. 当前数据加载机制

`engine.py` 中的 `DataLoader` 负责加载：

```text
rooms
npcs
items
enemies
skills
quests
```

默认数据也定义在 `engine.py`。

加载逻辑是：

```text
默认数据
   ↓
读取 data/*.json
   ↓
deep_merge
   ↓
GAME_DATA
   ↓
模块使用
```

### 重要限制

`deep_merge()` 的递归合并主要针对字典。

对于列表和普通标量：

> `[LIMITATION]` 后加载数据会整体替换，而不是智能逐项合并。

因此不要假设两个 JSON 列表会自动合并。

---

## 10. 当前战斗系统

当前为轻量回合制战斗。

玩家行动包括：

```text
普通攻击
技能
物品
逃跑
```

技能受到：

- 门派
- 等级
- MP
- 技能倍率

影响。

敌人也可以使用技能。

---

## 11. 当前状态系统

当前状态包括：

```text
poison   中毒
bleed    流血
stun     眩晕
shield   护盾
```

状态会在战斗回合处理中生效。

### 技术限制

`p_statuses_global` 是全局玩家状态容器。

因此：

> `[TECH DEBT]` 当前状态系统并不是可同时支持多个独立战斗实例的通用 CombatState 架构。

未来若加入复杂战斗、队伍、多敌人、多角色，应逐步改造。

---

## 12. 当前角色系统

`Player` 当前包含：

- 姓名
- 门派
- 等级
- 经验
- HP / MP
- 攻击
- 防御
- 金币
- 背包
- 武器
- 防具
- 装备强化等级
- 当前地点
- 当前任务
- 已完成任务

当前门派：

```text
少林
武当
华山
```

并存在不同初始属性加成。

---

## 13. 当前升级系统

升级会：

- 增加最大 HP
- 增加最大 MP
- 增加攻击
- 增加防御
- 恢复 HP / MP

经验需求按约 1.5 倍增长。

---

## 14. 当前任务系统

当前任务系统属于轻量任务系统。

现有任务数据包含：

```text
清剿黑风山
```

其核心目标是击杀指定敌人并领取奖励。

当前任务模型主要支持：

```text
kill
target_name
required_cnt
reward
```

因此：

> `[LIMITATION]` 当前还不是完整的多目标、条件链、阶段任务、世界状态任务系统。

---

## 15. 当前装备与强化

当前装备分为：

```text
weapon
armor
```

攻击/防御会由基础属性与装备属性共同计算。

强化系统目前在打铁铺进行：

- 上限 +5
- 每级消耗铁矿石
- 每级消耗金币

装备新物品时当前会重置对应强化等级。

---

## 16. 当前存档

存档：

```text
data/save.json
```

当前保存了：

- 玩家属性
- 背包
- 装备
- 地点
- 任务
- 存档版本号

当前 `SAVE_VERSION = 10`。

### 非常重要

虽然存在版本号：

> `[LIMITATION]` 当前没有完整的通用 Save Migration / 版本迁移框架。

读取时主要是：

- 缺字段使用默认值
- 旧地点名称映射
- 无效地点回退 `village_gate`

未来增加存档字段时必须谨慎。

---

## 17. 当前热重载限制

主程序支持：

```text
reload
```

用于重新加载 JSON。

但当前架构存在：

```python
from engine import ROOMS
from engine import NPCS
...
```

这样的模块级导入。

`reload_game_data()` 会重新绑定 `engine.ROOMS` 等对象。

因此：

> `[TECH DEBT]` 某些已经通过 `from engine import ...` 获取的旧引用可能不会自动指向新的数据对象。

所以当前 `reload` 不能被描述为“所有模块完全热更新”。

---

## 18. `wuxia.py` 的地位

`wuxia.py` 是项目历史遗留的大型实现。

它包含大量旧逻辑，并与当前模块化实现存在重复。

因此：

> `[RULE]` 新功能默认不得继续向 `wuxia.py` 添加逻辑。

优先修改：

```text
main.py
engine.py
player.py
combat.py
actions.py
data/*.json
```

除非明确要求迁移/删除旧代码。

---

## 19. 开发原则

### [RULE] 不破坏已有 ID

尤其是：

```text
room id
npc id
item id
enemy id
skill id
quest id
```

不要为了“命名更漂亮”随意改 ID。

因为 ID 可能被：

- Room exit
- NPC
- Quest
- Item
- Enemy
- Save
- Player location

引用。

---

### [RULE] 新内容优先数据化

NPC、物品、敌人、技能、任务、房间尽量放入：

```text
data/*.json
```

不要把大段具体游戏内容硬编码进 Python。

---

### [RULE] 新 Zone 必须有明确 Zone ID

例如未来归云城：

```text
guiyun_city
```

而不是使用中文名称作为内部 ID。

---

### [RULE] 跨 Zone 出口必须双向设计

如果：

```text
A → B
```

逻辑上需要返回：

```text
B → A
```

就必须明确设计，不要依赖“玩家以后找不到路”。

---

## 20. 未来世界扩展

近期重要扩展方向：

```text
主世界
 ├── 村庄
 ├── 野外
 ├── 黑风寨
 └── 归云城
```

归云城将作为独立 Zone：

```text
guiyun_city
```

其世界设计详见：

`WORLD_DESIGN.md`

特别需要保持：

- 城市作为独立 Zone
- 主世界与城市之间通过明确道路/城门连接
- 两段同名“黄土官道”可以作为不同 Room 存在
- 内部 ID 必须唯一
- 地图方向、出口、坐标必须保持可解释
- 城市内部内容逐步数据化

---

## 21. 给未来 AI 的入口

如果你是第一次接手本项目：

### 第一步

阅读：

```text
AI_CONTEXT.md
```

### 第二步

阅读：

```text
ARCHITECTURE.md
```

### 第三步

如果修改世界、地图、NPC、城市、剧情：

```text
WORLD_DESIGN.md
```

### 第四步

查看实际：

```text
data/*.json
```

### 第五步

最后才修改 Python。

---

## 22. 最重要的一句话

> **先理解当前代码，再修改；不要把规划中的架构当成已经实现的架构。**

本项目目前最重要的目标不是“代码看起来漂亮”，而是：

```text
保持现有可玩性
+
保持 ID / 存档兼容
+
逐步数据化
+
逐步扩大世界
+
避免新旧架构继续混杂
```
