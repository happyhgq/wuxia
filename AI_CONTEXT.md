# AI_CONTEXT.md

# Wuxia AI 开发上下文与接管规范

> 本文件是未来 AI 接手 `happyhgq/wuxia` 时的最高优先级项目说明之一。
> 它描述“现在真实存在什么”“修改时必须遵守什么”，不把规划伪装成现状。

---

# 1. 项目身份

```text
Wuxia · 武侠文字 RPG
仓库：happyhgq/wuxia
版本：P3.2 BL1.0 Alpha313
存档：SAVE_VERSION = 12
```

技术形态：Python 3.13 + 终端交互 + JSON 数据 + 房间式地图 + 轻量 RPG 系统。

入口：`main.py`。

---

# 2. AI 必须先区分五种状态

| 标签 | 含义 |
|---|---|
| `[CURRENT]` | 当前代码真实存在并参与运行 |
| `[LIMITATION]` | 能运行但能力不完整 |
| `[TECH DEBT]` | 可工作但继续扩展会出问题 |
| `[PLANNED]` | 设计目标，尚未实现 |
| `[RULE]` | 后续修改不得违反的项目规则 |

不要把 `[PLANNED]` 写成 `[CURRENT]`。

---

# 3. 固定阅读顺序

```text
README.md
    ↓
AI_CONTEXT.md
    ↓
ARCHITECTURE.md
    ↓
WORLD_DESIGN.md
    ↓
data/*.json 与相关测试
    ↓
相关 Python 文件
```

按任务定位：

| 任务 | 优先文件 |
|---|---|
| 战斗 | `combat.py`、`engine.py`、`player.py`、`data/enemies.json`、`data/skills.json` |
| 地图 | `engine.py`、`data/rooms.json`、`data/world_regions.json`、`data_validator.py` |
| NPC / 任务 | `actions.py`、`engine.py`、`data/npcs.json`、`data/quests.json` |
| 世界时间 / 氛围 | `world_time.py`、`world_ambience.py`、`weather.py` |
| 区域生态 | `region_activity.py`、`data/region_activity.json` |
| 经济 | `economy/`、`data/economy/*.json` |
| 存档 | `player.py`、`engine.py`、`SAVE_MIGRATIONS.md` |
| 帮助 / 界面 | `help_system.py`、`ui_output.py`、`actor_display.py` |
| 入口事件 | `entry_events.py`、`data/events.json` |

---

# 4. 当前真实架构

```text
main.py（主循环 / 命令分发）
   │
   ├── command_policy.py（准入与世界时钟策略）
   ├── actions.py（观察 / 交谈 / 任务 / 交易 / 装备 / 锻造）
   ├── combat.py（回合制战斗）
   └── player.py（玩家 / 存档）
          │
          ↓
       engine.py（数据加载 / 地图 / 世界效果 / 状态）
          │
          ├── world_time.py  world_ambience.py  weather.py
          ├── world_lifecycle.py  region_activity.py  entry_events.py
          ├── travel_system.py  npc_behavior.py  npc_utility.py
          └── random_npcs.py
          │
          ↓
       data/*.json
```

这是依赖关系概括，不是理想架构。

---

# 5. 文件职责

| 文件 | 当前职责 |
|---|---|
| `main.py` | 入口、命令映射、主循环、移动、保存/读取、帮助入口 |
| `engine.py` | 默认数据、DataLoader、全局数据、MapEngine、世界效果、状态效果 |
| `player.py` | Player、属性、门派、成长、任务进度、存档读写与迁移 |
| `combat.py` | 战斗、技能、敌人技能、Boss 预警、状态、奖励提交 |
| `actions.py` | look、talk、ask、任务、交易、装备、使用、锻造 |
| `actor_display.py` | 五段式角色观察（只读） |
| `command_policy.py` | 命令是否可处理、是否推进世界时钟 |
| `world_time.py` | tick、时刻、日期与时辰换算 |
| `world_ambience.py` | NPC 移动 / 车马 / 天色 / 天气 / 节气 / 声响推送 |
| `weather.py` | 天气与二十四节气 |
| `world_lifecycle.py` | 尸体、复活与刷新 |
| `region_activity.py` | 区域治安、活动池、巡逻、区域效果 |
| `entry_events.py` | 入口事件筛选与触发 |
| `help_system.py` | 三层帮助注册表与渲染 |
| `ui_output.py` | 折行、颜色开关、输出防泄漏 |
| `npc_behavior.py` | NPC 五态微行为（纯函数） |
| `npc_utility.py` | NPC 效用行为与只读状态 |
| `random_npcs.py` | 临时随机路人 |
| `travel_system.py` | 快速旅行与路线记录 |
| `item_feedback.py` | 统一物品增减与提示 |
| `rewards.py` | 统一奖励结算 |
| `data_validator.py` | 数据完整性校验 |
| `economy/` | 城镇资金池、商队、税费、库存与生产 |

### [RULE]

- 新玩法不要继续堆进 `main.py`。
- 对话 / 任务 / 商店 / 装备 / 物品优先放 `actions.py`。
- 战斗相关放 `combat.py`。
- 世界时间、天气、区域、事件等横切能力放对应独立模块。

---

# 6. JSON 数据规则

DataLoader 当前加载：

```text
rooms / npcs / items / enemies / skills / quests
build_profiles / world_regions / sects / factions
world_events / events
```

`deep_merge()` 只递归合并 dict：

```text
dict + dict → 递归合并
list + list → 整体替换
scalar + scalar → 替换
```

### [RULE]

新增 JSON 内容前必须确认实际结构，不要假设列表会自动追加。

### [RULE]

修改数据后必须运行：

```bash
python data_validator.py
```

---

# 7. ID 是长期资产

稳定标识：

```text
room id / npc id / item id / enemy id / skill id / quest id
```

### [RULE]

没有明确迁移计划，不得修改已有 ID。ID 可能被出口、NPC、任务、存档、玩家位置与代码引用。

---

# 8. Zone 规则

当前 12 个 Zone：

```text
main / bandit_zone / guiyun_city / northfront_town / mistwood
sunken_ruins / huashan_mountain / shaolin_mountain / wudang_mountain
tieyi_mountain / duanhun_ridge / inn_upper
```

### [RULE]

- Zone ID 稳定、唯一、ASCII 化。
- 新增 Zone 要同步：
  - `data/rooms.json`
  - `data/world_regions.json`
  - `MapEngine.ZONE_NAMES`
  - `data_validator.py` 中的区域校验
- 显示名可以重复，内部 ID 不得重复。
- 跨 Zone 出口必须有明确世界语义（道路、城门、山口、洞口、渡口、关隘），并双向设计。

---

# 9. 地图修改检查

新增 Room 后至少检查：

```text
1. id 唯一
2. zone 正确且已注册
3. exits 目标存在
4. 坐标与出口方向一致
5. 对向出口是否需要
6. 是否跨 Zone
7. 是否需要 safe_zone / indoor / window_view
8. 是否影响旧存档位置
9. 入口事件是否需要引用
10. 地图与 validator 是否通过
```

---

# 10. NPC 规则

NPC 常用字段：

```text
id / name / title / rank_title / nickname / desc
dialogue / talk_verb / conditional_dialogue
info / shop / quests
daily_schedule / utility_profile / home_room
faction / relations
```

### [RULE]

- 条件对白用 `conditional_dialogue`（`priority` + `requires`），不要把世界状态判断硬编码进 Python。
- 条件对白优先级相同时，按数据中的先后顺序取前者。
- 展示字段（称号、性别、年龄、武评、装备）由 `actor_display.py` 读取，不在对话里重复输出面板。
- NPC 的关系、记忆与势力写入 V12 `world_state.variables`。

---

# 11. Quest 规则

任务支持：

```text
type / difficulty / npc / desc
prerequisites / stages / target_type / required_cnt
reward / repeat_reward / cooldown
choices（交付分支）
on_accept / on_complete / effects
```

世界效果字段：

```text
set_flags / set_variables / increment_variables
faction_relations / relations / region_effects
```

### [RULE]

- 可重复任务的 `repeat_reward.effects` 与 `on_*` 不得包含 `region_effects`。
- 有分支的任务必须在数据中列出选项；未选择时不得自动结算。
- 新任务类型应先更新 schema、校验器与文档，不要无规则堆字段。

### [LIMITATION]

仍不支持任意脚本化条件、失败链与动态生成任务。

---

# 12. 世界状态规则

所有世界状态放在 V12：

```text
world_state.flags
world_state.variables
```

约定使用 `world:main:*` 等命名空间旗标，变量按系统分组：

```text
world_clock / region_activity / weather_world / ambient_world
entry_events / npc_relations / faction_relations / npc_behaviors
quest_states / economy / ...
```

### [RULE]

- 新增状态优先写入 `variables`，不要新增存档顶层字段，除非同时提升 `SAVE_VERSION` 并写迁移。
- 数值状态必须有合法区间与夹紧逻辑，并在读档时收敛。
- 只读观察不得创建状态记录。

---

# 13. 存档规则

```text
SAVE_VERSION = 12
```

读档迁移：

```text
v10 → v11：补 world_state + 旧地点别名
v11 → v12：阶段任务 quest_states
```

### [RULE]

增加玩家字段或世界状态时：

1. save 写入
2. load 默认值
3. 旧档兼容
4. 判断是否需要提升 `SAVE_VERSION`
5. 提升版本必须同步 `SAVE_MIGRATIONS.md` 与迁移测试

### [RULE]

- 迁移只在读档时进行，再次保存才写回。
- 保留正式存档不动；测试必须隔离存档。
- 修改 `location / inventory / equipment / quest / world_state` 必须特别检查兼容性。

---

# 14. 测试与验收规则

```text
tests/                     pytest 回归
tests/conftest.py          无参 save_to_file 重定向到 tmp_path
data_validator.py          只读数据校验
```

### [RULE]

- 写存档的测试必须显式隔离（patch `Player.save_to_file` 或传临时路径）。
- 修改任务/数据计数时，同步更新总量断言。
- 交付前至少执行：

```bash
python -m pytest -q
python -m compileall -q .
python data_validator.py
```

- 只报告实际运行过的结果；估算值必须标明。

---

# 15. 战斗与状态

状态：中毒、流血、眩晕、护盾。新增状态必须同步：

```text
STATUS_EFFECTS
add_status
process_status_effects
format_statuses
```

战斗修改必须同时考虑玩家普攻、玩家技能、敌人普攻、敌人技能、装备、防御、等级、MP 与状态效果。

### [LIMITATION]

玩家状态使用全局 `p_statuses_global`，不支持并行战斗或队伍。

---

# 16. 帮助与界面

- 帮助注册表 `ENTRIES` 是唯一数据源。
- 分类页只显示名称与一句话用途，详情页才展开参数。
- 新增命令必须同时加入帮助注册表与测试。
- 输出层负责折行、颜色与防泄漏；不要在业务代码里直接打印内部 ID。

---

# 17. 热重载

`reload_game_data()` 会重建 `GAME_DATA` 与 `MAP_ENGINE`，但模块级 `from engine import ...` 引用可能仍指向旧对象。

### [RULE]

任何修改 reload 的任务必须检查 `main.py`、`actions.py`、`combat.py`、`player.py`、`engine.py`，不要仅改 `reload_game_data()` 就宣称热重载完成。

---

# 18. 修改策略

## 小改动

新增 NPC / 物品 / 敌人 / 任务 / 房间 → 优先只改 `data/*.json`，并过校验器。

## 中型改动

新增交互、商店规则、装备行为 → 先找现有责任模块，不新建平行实现。

## 大型改动

Zone、城市、任务系统、战斗系统、世界状态 → 先更新 `WORLD_DESIGN.md` 与 `ARCHITECTURE.md`，再实现。

---

# 19. AI 禁止事项

1. 未阅读相关代码就重写核心系统。
2. 随意改已有 ID。
3. 把中文显示名当内部 ID。
4. 把规划功能写成已经实现。
5. 声称 MapEngine 已经是完整验证器。
6. 声称 reload 已经彻底热更新。
7. 声称存档已经具备完整通用迁移。
8. 大量内容继续硬编码。
9. 在可重复任务里放 `region_effects`。
10. 测试覆盖正式存档。
11. 为小功能顺手重构整个项目。

---

# 20. 修改后的检查

```text
[ ] 是否破坏已有 ID？
[ ] 是否破坏存档或世界状态？
[ ] 是否破坏 Room exit / 跨 Zone？
[ ] 是否影响战斗结算？
[ ] 是否影响 NPC / Quest 引用？
[ ] 是否更新数据校验与测试？
[ ] 是否更新文档？
[ ] 是否把 PLANNED 写成 CURRENT？
```

---

# 21. 未来目标架构

`[PLANNED]`，不是当前实现：

```text
Application
 ├── Command System
 ├── World System（Zone / Room / Travel / Time / Weather / Region）
 ├── Character System
 ├── Combat System
 ├── Quest System
 ├── Economy System
 ├── Save System（通用迁移）
 └── Data System（schema 校验）
```

但不应为了架构漂亮而推翻当前可玩版本。

---

# 22. 最终原则

> **兼容优先，数据优先，渐进重构，真实状态优先。**

每次修改都应该让项目更稳定、更容易扩展、更容易被下一次接手者理解，而不是只让本次功能“看起来完成”。
