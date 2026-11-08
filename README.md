# Wuxia · 武侠文字 RPG

> 中文终端武侠 RPG。Python + JSON 数据驱动，包含地图探索、NPC 与关系、任务与选择、门派与武学、回合制战斗、采集与锻造、区域生态、世界时钟与天气、存档与迁移。

当前版本：`P3.2 BL1.0 Alpha308`（`VERSION.txt`），存档版本 `SAVE_VERSION = 12`。

---

## 1. 项目定位

本项目是一个**可持续扩展的单机中文武侠文字 MUD**。

当前运行形态：

- 终端 / 命令行（推荐 80 列左右终端）
- Python 3.13
- JSON 游戏数据
- 房间式地图 + Zone 分区
- NPC、对话、关系与日程
- 任务、分支选择与世界效果
- 商店、买卖、商队与城镇经济
- 装备、强化、采集与锻造
- 回合制战斗、状态效果、Boss 预警
- 门派、师承、身份与晋升
- 世界时钟、天气节气、区域生态
- JSON 存档（V12）+ 读档迁移

项目已经不是单文件原型，但仍不是通用 RPG 引擎。

**本 README 描述当前真实实现，而不是目标架构。** 规划内容统一标记为 `[PLANNED]`。

---

## 2. 当前状态速览

| 项目 | 当前值 |
|---|---|
| 房间 | 173 |
| 区域（Zone） | 12 |
| 固定 NPC | 74 |
| 物品 | 79 |
| 敌人模板 | 41 |
| 武学套系 | 6 |
| 任务 | 60 |
| 门派 / 出身 | 少林、武当、华山、铁衣门、散人 |
| 等级设计上限 | L15（软上限，不是硬锁） |
| 存档版本 | V12 |
| 自动化测试 | 2042 passed，616 subtests passed |

区域列表：

```text
main               主世界
bandit_zone        黑风寨
guiyun_city        归云城
northfront_town    北境商镇
mistwood           雾隐山林
sunken_ruins       沉河遗址
huashan_mountain   华山群峰
shaolin_mountain   嵩山少林
wudang_mountain    武当山
tieyi_mountain     铁衣门山庄
duanhun_ridge      断魂岭
inn_upper          悦来客栈二楼
```

---

## 3. 启动与验收

启动：

```bash
python main.py
```

推荐使用 UTF-8 输出（Windows 控制台或设置 `PYTHONIOENCODING=utf-8`）。

一键本地检查（Windows）：双击 `检查游戏.bat`，依次执行：

```text
pytest -q
python -m compileall -q .
python data_validator.py
```

手动验收：

```bash
python -m pytest -q
python -m compileall -q .
python data_validator.py
```

`data_validator.py` 为只读校验，当前结果：

```text
DATA VALIDATION: PASS
rooms=173 npcs=74 items=79 enemies=41 skills=6 quests=60 regions=12 events=3
```

---

## 4. 项目结构

```text
wuxia/
├── main.py                  入口、命令循环、移动、存读档
├── engine.py                数据加载、地图引擎、世界效果、状态效果
├── player.py                玩家、成长、任务状态、存档读写
├── combat.py                回合制战斗、技能、Boss 预警、奖励结算
├── actions.py               观察、交谈、任务、交易、装备、使用、锻造
├── actor_display.py         角色五段式观察视图
├── command_policy.py        命令准入与世界时钟策略
├── world_time.py            世界时钟唯一换算入口
├── world_ambience.py        世界动态消息（NPC 移动/天色/声响）
├── weather.py               天气与二十四节气
├── world_lifecycle.py       尸体、复活与敌人刷新
├── region_activity.py       区域治安、敌人活动池、巡逻与区域效果
├── entry_events.py          入口事件（进入新场景时触发）
├── help_system.py           三层帮助（13 类 / 84 条）
├── ui_output.py             输出防泄漏、折行与颜色开关
├── npc_behavior.py          NPC 五态微行为（纯函数）
├── npc_utility.py           NPC 效用行为（日程/营生/需求折算）
├── random_npcs.py           低密度随机路人
├── travel_system.py         已探索路线的快速旅行
├── item_feedback.py         统一的物品增减与提示
├── rewards.py               统一奖励结算
├── data_validator.py        数据完整性校验
├── economy/                 城镇经济、商队、税费与库存
├── data/                    游戏内容与存档
└── tests/                   回归测试
```

数据文件：

```text
data/rooms.json            房间、出口、区域与坐标
data/npcs.json             固定 NPC、对话、条件对白、商店与委托
data/items.json            物品、装备与材料
data/enemies.json          敌人、技能、掉落与刷新
data/skills.json           武学套系与招式
data/quests.json           任务、阶段、前置、选择与效果
data/factions.json         势力与初始关系
data/sects.json            门派、身份、师承与专属武学
data/events.json           入口事件表
data/world_events.json     世界事件
data/region_activity.json  区域生态基础值
data/random_npcs.json      随机路人模板
data/build_profiles.json   出身/成长配置
data/economy/*.json        资源、配方、商队与经济事件
data/save.json             正式存档（V12）
```

---

## 5. 当前核心系统

### 5.1 世界时钟

- 1 tick = 1 个世界时辰（1 小时），tick 0 = 卯时 06:00。
- 世界只在玩家行动后推进；不输入指令时世界不会自行流动。
- 只读查看命令不耗时；失败的交互也不消耗时间。
- `停留`（简写 `停`）主动等过一个时辰。
- 客栈过夜推进到下一次卯时。

### 5.2 地图与移动

- 房间由 `data/rooms.json` 驱动，出口使用方向或自定义出口（如 `上/下`、`内/外`）。
- 室内房间标记 `indoor`，安全区标记 `safe_zone`。
- 已探索路线支持快速旅行；跨 Zone 通过道路、城门、山口、洞口等边界房间连接。
- 地图引擎负责布局与自动摆放，`data_validator.py` 负责出口、坐标与反向出口校验。

### 5.3 NPC、交谈与关系

- NPC 有五段式观察描述（相貌衣着、年龄、武力、状态、装备）。
- 交谈支持话题、`ask` 询问、关系面板、记忆与条件对白（`conditional_dialogue`）。
- NPC 有日程与行为层：按时离场、在岗、巡逻、营生与随机路人。
- 忙碌 NPC 会给短应答，不推进时间，但仍可接取/交付委托。
- 势力关系与 NPC 关系写入世界状态，任务与选择可改变它们。

### 5.4 任务与选择

- 任务支持前置、阶段、计数、可重复（复做冷却与复做奖励）、难度与经验。
- 交付时可出现分支选择（`交付 <任务> <选项>`），不同选择结算不同奖励与世界效果。
- 效果统一由 `engine.apply_world_effects` 处理：旗标、变量、势力关系、NPC 关系、区域效果。
- `region_effects` 会持久改变区域的治安/商路/通行，并夹紧在 -60~30；交付后打印实际区域变化。
- 未选择分支时会列出选项且不结算。

### 5.5 战斗

- 轻量回合制：普攻、招式、物品、逃跑。
- 状态：中毒、流血、眩晕、护盾。
- Boss 招牌技能带一回合预警。
- 战斗奖励、任务进度、击败记录与区域联动共用统一结算。

### 5.6 门派与武学

- 门派：少林、武当、华山、铁衣门；散人为无门派出身。
- 身份、晋升、师承、门派声望与专属武学均有数据门槛。
- 武学存在熟练度、内力消耗、威力与特殊效果（护盾、破防等）。

### 5.7 区域生态与经济

- 每个区域有治安、商路、通行三项持久值，任务、事件与玩家行为可改变它们。
- 区域状态影响敌人活动、巡逻、商店与商队、传闻与地方面板。
- 城镇有资金池与商税闭环；商队携带真实库存与报价。
- 采集、资源、配方与锻造构成基础生产链。

### 5.8 天气、节气与氛围

- 六种天气：晴、阴、小雨、雷雨、小雪、雾；一年 360 天，每 15 天一个节气。
- 天气只在黎明变化，由角色名与世界 tick 确定性驱动，不使用随机数或线程。
- 动态消息按“NPC 移动 > 车马过客 > 天色 > 天气 > 节气 > 场景声响”推送，每轮最多 5 条。
- 室内外按房间 `indoor` 与 `window_view` 分别取词。

### 5.9 入口事件

- `data/events.json` 按房间/区域、时段、条件、once 与 cooldown 筛选。
- 只在成功进入新场景时判定，`look`、读档与 NPC 自行移动不触发。
- 触发记录写入 V12 `world_state.variables`。

### 5.10 帮助与界面

- 三层帮助：分类目录 → 分类页 → 单条详情，共 13 类 84 条。
- 支持序号导航、分类别名、上下文清理。
- 颜色支持 `auto/on/off`，非 TTY 或 `NO_COLOR` 时自动关闭。
- 输出层会剥离内部 ID、路径与调试对象。

---

## 6. 命令入口

游戏内输入 `帮助` 查看完整三层帮助（13 类 84 条），常用命令：

```text
查看与移动    看 / 地图 / 北 南 东 西 / 旅行 / 敲门 / 探索 / 停留
交谈与人物    交谈 人物 [话题] / 关系 / 记忆 / 人物行动 / 世界动态 / 商情
任务与委托    任务 / 任务 交付 / 任务 放弃 / 任务 选择
门派与师承    门派 / 拜师 / 门派 查看|晋升|修习|声望|关系|师徒|受戒|退出
武学与招式    武学 / 武学 查看|学习|遗忘
状态与成长    状态 / 属性 / 加点 / 流派 / 天时
背包与装备    背包 / 装备 / 装备武器 / 穿戴 / 卸下 / 比较 / 使用
采集与生产    职业 / 搜索 / 采集 / 伐木 / 采矿 / 打造
战斗与恢复    攻击 / 打坐 / run
商店与交易    商店 / 货架 / 购买 / 出售
客栈与休息    住店 / 吃饭 / 喝茶 / 听消息
江湖与消息    公告 / 信息 / 商队 / 势力 / 冲突 / 区域 / 影响 / 治安 / 事件
系统与帮助    帮助 / 百科 / 建议 / 颜色 / 保存 / 读档 / 退出 / 别名 / 历史
```

具体别名、子命令与参数以游戏内帮助和 `main.py` 当前代码为准。

---

## 7. 存档与兼容

- 存档路径：`data/save.json`，备份 `data/save.json.bak`。
- 当前 `SAVE_VERSION = 12`，世界状态集中在 `world_state`（`flags`、`variables`）。
- 读档时自动迁移旧版本（v10→v11→v12），补齐世界状态、阶段任务与旧地点别名。
- 迁移只在读档时进行，玩家再次保存后才写回文件。
- 旧字段缺失使用默认值；无效地点回退 `village_gate`，不会直接崩溃。
- 新增存档字段时必须同时处理：写入、读取默认值、旧档兼容、版本号是否需要提升。

---

## 8. 开发规则

### [RULE] 不破坏已有 ID

`room / npc / item / enemy / skill / quest` 的 ID 是长期资产，可能被出口、NPC、任务、存档与代码引用。没有迁移计划不得改名。

### [RULE] 新内容优先数据化

NPC、物品、敌人、武学、任务、房间、事件、区域效果尽量放入 `data/*.json`，不要把大段具体内容硬编码进 Python。

### [RULE] 新 Zone 必须有英文 ID

Zone ID 稳定、唯一、ASCII 化（如 `guiyun_city`），并同步 `data/world_regions.json` 与 `MapEngine` 的显示名。

### [RULE] 跨 Zone 出口双向设计

`A → B` 必须在设计中明确 `B → A`，不要依赖玩家找不到路。

### [RULE] 测试不得覆盖正式存档

`tests/conftest.py` 会把无参 `save_to_file()` 重定向到临时目录；写存档测试必须显式隔离。

### [RULE] 数据改动必须过校验

修改 JSON 后运行 `data_validator.py`，并跑全量测试。

---

## 9. 已知限制

- `[LIMITATION]` 地图引擎不是完整验证器，布局正确性依赖 `data_validator.py` 与测试。
- `[LIMITATION]` 部分模块仍通过 `from engine import ...` 绑定数据，`reload` 不是严格的热更新。
- `[LIMITATION]` 没有通用存档迁移框架，迁移是按版本手写并逐步补齐的。
- `[LIMITATION]` 玩家状态使用全局容器，不支持多场并行战斗或队伍。
- `[LIMITATION]` L15 是当前内容上限，L16+ 尚未设计。
- `[TECH DEBT]` `main.py` 与 `engine.py` 责任仍偏多，后续应逐步抽服务，但不做一次性重写。

---

## 10. 文档索引

- `AI_CONTEXT.md`：接手本项目时必须遵守的开发规则与当前状态。
- `ARCHITECTURE.md`：模块划分、数据流、依赖关系与技术债。
- `WORLD_DESIGN.md`：世界观、地图与 Zone 设计、内容扩展规则。
- `SAVE_MIGRATIONS.md`：存档版本迁移记录。
- `P4.0_COMMAND_TICK_CONTRACT.md`：命令与世界时钟契约。
- `开发规范.md`、`开发任务清单.md`、`最新交接记录.md`：本地开发流程与交付记录。

---

## 11. 最重要的一句话

> **先理解当前代码，再修改；不要把规划中的架构当成已经实现的架构。**

当前目标不是“代码看起来漂亮”，而是：

```text
保持可玩性
+
保持 ID / 存档兼容
+
逐步数据化
+
逐步扩大世界
+
保持测试与数据校验通过
```
