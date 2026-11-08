# ARCHITECTURE.md

# Wuxia 当前技术架构说明

> 本文件描述当前真实代码架构，并明确已知限制。
> 未来理想架构统一标记为 `[PLANNED]`。

---

# 1. 总体结构

```text
                         main.py
                            │
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
   command_policy.py    actions.py          combat.py
   命令准入/时钟        观察/交谈/任务      战斗/结算
        │                   │                   │
        │                   ├──────────┐        │
        ↓                   ↓          ↓        ↓
   world_time.py        player.py   rewards.py  item_feedback.py
   世界时钟             玩家/存档   统一奖励     物品变动提示
                            │
                            ↓
                        engine.py
                数据加载/地图/世界效果/状态
                            │
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
   world_ambience.py   region_activity.py   weather.py
   动态消息            区域生态              天气节气
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ↓
                        data/*.json
```

世界状态统一存放在 V12 存档的 `world_state.flags` 与 `world_state.variables` 中，由各系统读写，不新增存档顶层字段。

---

# 2. Runtime 层

## 2.1 `main.py`

入口层，负责：

```text
程序启动
命令解析与分发
主命令循环
移动与地图
保存 / 读取
reload
帮助入口
部分玩家操作
```

### [TECH DEBT]

`main.py` 仍承担部分具体逻辑，是当前最大的“超级控制器”。

## 2.2 `command_policy.py`

只判断“这条命令能否处理、是否推进世界时钟”，不执行游戏动作。

- 只读命令（查看、背包、任务列表等）不推进时间。
- 确定性失败的交互不推进时间。
- 成功交互与交谈各推进 1 个世界时刻。
- 与 `main.py` 的延后计时配合，避免失败命令仍消耗时间。

---

# 3. 游戏动作层

## 3.1 `actions.py`

负责：

```text
look / 观察
talk / ask / 条件对白
quest / 接取 / 交付 / 选择
trade / 商店 / 商队
equipment / 使用物品
forge / 强化
```

它直接使用 `ROOMS`、`NPCS`、`ITEMS`、`QUESTS` 等 engine 数据。

### [TECH DEBT]

部分数据通过 `from engine import ...` 绑定，与 `reload` 存在引用一致性问题。

## 3.2 `actor_display.py`

把 NPC 数据整理成传统 MUD 的五段式只读描述：

```text
相貌衣着
年龄
模糊武力评价
状态 / 伤势
装备
```

展示层不写世界状态。

---

# 4. 战斗层

## 4.1 `combat.py`

负责：

```text
combat()
handle_attack()
玩家回合 / 敌人回合
技能与物品
逃跑
状态效果
Boss 招牌技能预警
胜负与奖励结算
```

- 玩家状态保存在全局容器 `p_statuses_global`。
- 敌人状态是战斗局部数据。
- 预警技能当回合不造成伤害，下回合正常结算。
- 战斗胜利后统一提交任务进度、击败记录、区域联动与奖励，避免重复发奖。

---

# 5. 角色层

## 5.1 `player.py`

`Player` 是玩家状态核心，包含：

```text
name / sect / level / exp
hp / max_hp / mp / max_mp
atk / defense / gold
inventory / equipment / equip_enhance
location
active_quests / completed_quests / quest_states
world_state（V12）
```

同时负责存档写入、读取与迁移调用。

## 5.2 `rewards.py`

统一奖励结算层：经验、银两、物品、侠名、势力/NPC 关系、区域效果、复做奖励等，避免各入口各写一套。

## 5.3 `item_feedback.py`

统一物品增减与“获得 / 失去 / 消耗 / 交付”提示，所有改变背包的功能都应经由该模块。

---

# 6. 数据层

## 6.1 `DataLoader`

`engine.py` 中的 `DataLoader` 负责加载：

```text
rooms
npcs
items
enemies
skills
quests
build_profiles
world_regions
sects
factions
world_events
events
```

流程：

```text
默认数据（engine.py 内）
    ↓
data/<name>.json
    ↓
deep_merge
    ↓
GAME_DATA
```

经济数据由 `economy/` 包自行加载：

```text
data/economy/resources.json
data/economy/recipes.json
data/economy/caravans.json
data/economy/economy_events.json
data/economy/gatherers.json
```

## 6.2 deep_merge 的真实语义

```text
dict + dict → 递归合并
list + list → 后者整体替换
scalar + scalar → 后者替换
```

### [LIMITATION]

没有 schema-aware merge，列表不会自动追加。

## 6.3 数据校验

`data_validator.py` 是只读校验器，检查房间、出口、NPC、物品、敌人、武学、任务、区域、事件与效果字段，当前全量数据通过。

---

# 7. 地图引擎

## 7.1 MapEngine

负责：

```text
读取 Room
建立布局与坐标
出口解析（含自定义出口 上/下、内/外、后/前）
自动摆放
ASCII 地图
当前房间高亮
跨 Zone 标记
```

方向模型：

```text
北 = (0, 1)
南 = (0,-1)
东 = (1, 0)
西 = (-1,0)
```

## 7.2 Zone 数据

- 区域基础数据在 `data/world_regions.json`，运行时为 `engine.WORLD_REGIONS`。
- 地图标题显示名仍硬编码在 `MapEngine.ZONE_NAMES`。

### [LIMITATION]

新增 Zone 需要同时修改：

```text
data/rooms.json
data/world_regions.json
MapEngine.ZONE_NAMES
```

## 7.3 地图引擎不是验证器

MapEngine 会容忍无坐标房间并尝试自动摆放，但这不等于地图正确。

真正的出口、双向、坐标与区域校验由 `data_validator.py` 与回归测试承担。

---

# 8. 世界层

## 8.1 `world_time.py`

世界时钟唯一换算入口：

```text
1 tick = 1 小时
tick 0 = 卯时 06:00
```

负责时刻、日期、时辰文案与“到下一次卯时”的计算。

## 8.2 `world_ambience.py`

把以下动态自然推送给玩家：

```text
NPC 移动
车马过客
天色
天气
节气
场景声响
```

每轮最多 5 条，优先级从高到低；满额时顺延，`blocked` 时可暂缓并补推。推送标记写入 V12 `world_state.variables.ambient_world`。

## 8.3 `weather.py`

六种天气与二十四节气：

```text
晴 / 阴 / 小雨 / 雷雨 / 小雪 / 雾
```

一年 360 天、每 15 天一个节气；只在黎明变化，由角色名与 tick 确定性驱动，不使用随机数、线程或定时器。状态写入 V12 `weather_world`。

## 8.4 `world_lifecycle.py`

尸体消失、复活计时与敌人刷新策略；状态写入 V12 `world_state.variables`。

## 8.5 `region_activity.py`

区域治安、敌人活动池、官府巡逻与区域效果：

- 三项持久值：`security`、`commerce`、`travel`。
- 永久变化夹紧在 -60~30；展示值叠加基础值与事件修正。
- 提供 `apply_region_effects`，由 `engine.apply_world_effects` 的 `region_effects` 字段调用。

## 8.6 `entry_events.py`

按 `data/events.json` 在成功进入新场景时触发一次入口事件：

- 支持房间/区域、左闭右开时段、条件、`once`、`cooldown`、`priority`。
- `look`、读档与 NPC 自行移动不触发。
- 触发记录写入 V12 `world_state.variables.entry_events`。

## 8.7 `travel_system.py`

已探索路线上的快速旅行；路线与解锁状态写入 V12 `world_state.flags`。

## 8.8 `npc_behavior.py` / `npc_utility.py`

- `npc_behavior`：`idle / working / resting / moving / interacting` 五态纯函数。
- `npc_utility`：把日程、营生工时、关系、治安与需求折算成行动分数。
- 日程优先，行为层只处理未覆盖的 NPC；写 tick 时才记录，观察不创建状态。
- `npc_utility.get_npc_current_state` 为只读纯函数，供观察层使用。

## 8.9 `random_npcs.py`

低密度随机路人，只管理临时路人，不进入固定 NPC 名册与存档。

---

# 9. NPC 模型

`data/npcs.json` 当前主要字段：

```text
id / name / title / rank_title / nickname
desc / dialogue / talk_verb / conditional_dialogue
info / shop / quests
daily_schedule / utility_profile / home_room
relations / faction / tags
```

- `conditional_dialogue`：按 `requires` 条件与 `priority` 选择当前世界状态下的一句对白。
- 交谈带话题且没有对应情报时，优先回退条件对白，再回“不知道”。
- 忙碌 NPC 给短应答，不推进时间，但仍可接取/交付委托。
- NPC 与 Room 通过房间 `npcs` 名册与 `home_room` 关联。

---

# 10. 任务模型

任务数据支持：

```text
type / npc / desc / difficulty
target_type / target_name / required_cnt
prerequisites / stages / stage progress
reward / repeat_reward / cooldown
choices（交付分支）
on_accept / on_complete / effects
world:main:* 旗标条件
```

交付流程：

```text
检查前置与阶段
    ↓
按选择结算奖励
    ↓
apply_world_effects（旗标/变量/势力/关系/区域）
    ↓
交付反馈与区域变化
```

效果字段：

```text
set_flags
set_variables
increment_variables
faction_relations
relations
region_effects
```

### [RULE]

- 可重复任务的 `repeat_reward.effects` 与 `on_*` 不得包含 `region_effects`，防止重复刷区域值。
- 未选择分支时只列出选项，不结算。

---

# 11. 存档架构

## 11.1 文件

```text
data/save.json
data/save.json.bak
```

## 11.2 顶层结构

```text
player
inventory
equipment
location
quests
version
world_state
```

`world_state` 包含：

```text
flags
variables（时钟、区域生态、天气、ambient、entry_events、关系、经济等）
```

## 11.3 Save Version

```text
SAVE_VERSION = 12
```

读档迁移：

```text
v10 → v11：补 world_state，旧地点别名映射
v11 → v12：阶段任务 quest_states
```

迁移只在读档时进行，再次保存才写回。

### [LIMITATION]

没有通用 Migration Framework；迁移是按版本手写并逐步补齐的，新增字段仍必须手动处理默认值与旧档兼容。

---

# 12. 帮助与界面层

## 12.1 `help_system.py`

三层帮助：

```text
分类目录 → 分类页 → 单条指令详情
```

当前 13 类 84 条，注册表 `ENTRIES` 是唯一数据源；分类页只显示名称与一句话用途，详情页才展开参数、别名与示例。

## 12.2 `ui_output.py`

- 统一正文宽度与折行。
- 剥离内部 ID、路径与调试对象，避免泄漏到游戏文本。
- 三态颜色开关：`auto / on / off`，非 TTY、`NO_COLOR`、`TERM=dumb` 时自动关闭。

---

# 13. 测试与验收

```text
tests/                      pytest 回归
tests/conftest.py           无参 save_to_file 重定向到临时目录
data_validator.py           数据完整性校验
python -m compileall .      编译检查
检查游戏.bat                Windows 一键执行以上三项
```

### [RULE]

写存档的测试必须显式隔离，不得覆盖正式 `data/save.json`。

---

# 14. 热重载

`reload_game_data()` 会重新加载 JSON 并重建 `MAP_ENGINE`。

### [TECH DEBT]

其他模块存在 `from engine import ROOMS` 等静态引用，重新绑定后旧引用可能不会自动更新，因此 `reload` 不是严格热更新。

---

# 15. 当前架构的主要风险

## 风险 A：数据引用过早绑定

`from engine import ROOMS` 造成 reload 风险。

## 风险 B：engine 责任过多

同时承担默认数据、加载、地图、状态、世界效果与渲染入口。

## 风险 C：main.py 责任过多

命令分发之外仍有具体逻辑，接近“超级控制器”。

## 风险 D：地图拥有两套 Zone 名称来源

`data/world_regions.json` 与 `MapEngine.ZONE_NAMES` 需要手工保持一致。

## 风险 E：缺少通用存档迁移框架

版本号存在，但迁移仍是逐版本手写。

## 风险 F：世界状态集中在 variables

灵活但缺少 schema，字段命名与类型依赖测试和校验器约束。

---

# 16. 推荐的渐进式未来架构

### [PLANNED]

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
 ├── Player / Room / NPC / Item / Enemy / Quest / Skill
  ↓
Data Repository
  ↓
JSON
```

不要为了架构整齐一次性重写可玩版本。

---

# 17. 当前架构结论

本项目当前属于：

```text
模块化的可玩 MUD / 早期内容驱动 RPG
```

不是成熟通用引擎。下一阶段重点是：

```text
数据稳定
+
地图质量
+
世界内容
+
ID / 存档兼容
+
测试与校验覆盖
```

而不是大规模重写。
