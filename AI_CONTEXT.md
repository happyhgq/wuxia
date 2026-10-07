# Wuxia — AI_CONTEXT.md

> AI 项目接管上下文。  
> 适用对象：ChatGPT、Claude、Gemini、Cursor、Copilot、代码代理及未来维护者。
>
> 本文件回答一个问题：**“如果你第一次接手这个仓库，应该如何理解它、修改它，并避免破坏已有系统？”**

---

## 1. 项目身份

仓库：`happyhgq/wuxia`

类型：Python 中文武侠文字 RPG。

当前仓库以模块化代码 + JSON 数据为主体，同时保留一个历史单文件实现 `wuxia.py`。

当前顶层结构：

```text
wuxia/
├── README.md
├── AI_CONTEXT.md
├── ARCHITECTURE.md
├── main.py
├── engine.py
├── player.py
├── combat.py
├── actions.py
├── wuxia.py
└── data/
```

GitHub 当前 `main` 分支仍以以上核心 Python 文件和 `data/` 为主要项目结构。

---

# 2. AI 第一原则

任何 AI 接手项目时：

1. **先阅读 `README.md`。**
2. **再阅读 `AI_CONTEXT.md`。**
3. **再阅读 `ARCHITECTURE.md`。**
4. 根据任务读取相关源码。
5. 最后才修改代码或 JSON。

不要看到需求后直接重写文件。

---

# 3. 当前架构判断

当前推荐的主架构是：

```text
main.py
   │
   ├── 游戏启动
   ├── 游戏主循环
   ├── 输入解析
   └── 指令分发
           │
           ├── actions.py
           ├── combat.py
           └── player.py
                    │
                    ▼
                 engine.py
                    │
                    ├── 世界数据
                    ├── 数据加载
                    ├── MapEngine
                    └── 公共游戏机制

data/*.json
    │
    └── 世界内容
```

`wuxia.py` 不应被默认视为新功能的主要开发位置。

---

# 4. 文件职责速记

| 文件 | 当前职责 | 修改优先级 |
|---|---|---|
| `main.py` | 启动、主循环、命令解析/分发 | 输入和流程 |
| `engine.py` | 核心数据、数据加载、地图引擎、基础机制 | 谨慎修改 |
| `player.py` | Player、成长、属性、装备、存档 | 玩家系统 |
| `combat.py` | 战斗、技能、敌人行动、状态 | 战斗系统 |
| `actions.py` | 观察、NPC、任务、交易、装备等行为 | 行为系统 |
| `data/*.json` | 世界内容 | 内容扩展首选 |
| `wuxia.py` | 历史/旧式单文件实现 | 默认不新增功能 |

---

# 5. 需求 → 文件映射

## 只增加内容

优先修改：

```text
data/rooms.json
data/npcs.json
data/items.json
data/enemies.json
data/skills.json
data/quests.json
```

## 修改玩家规则

```text
player.py
```

## 修改战斗规则

```text
combat.py
```

## 修改玩家行为

```text
actions.py
```

## 修改核心地图 / 数据加载机制

```text
engine.py
```

## 修改命令或游戏主流程

```text
main.py
```

---

# 6. 最重要的安全规则

## 6.1 不要随意修改已有 ID

尤其是：

```text
room_id
npc_id
item_id
enemy_id
skill_id
quest_id
```

这些 ID 很可能被：

- 存档
- 房间引用
- NPC
- 任务
- 掉落
- 商店
- 代码

引用。

如果必须改 ID，应先建立兼容映射，而不是直接删除旧 ID。

---

## 6.2 新增引用必须保证目标存在

必须避免：

```text
room → 不存在 NPC
room → 不存在 enemy
NPC → 不存在 quest
quest → 不存在 item
enemy → 不存在 item
enemy → 不存在 skill
shop → 不存在 item
```

---

## 6.3 不要只改 JSON 来实现不存在的机制

例如 JSON 中增加：

```json
"effect": "poison"
```

并不代表系统已经支持中毒。

必须确认：

```text
combat.py
    ↓
创建状态
    ↓
每回合处理
    ↓
持续时间
    ↓
状态结束
```

全部存在。

---

# 7. 地图修改规则

地图是本项目最容易被 AI 改坏的部分。

一个房间至少涉及：

```text
room_id
name
zone
desc
coord
exits
npcs
enemies
```

修改地图时必须检查：

```text
[ ] room_id 唯一
[ ] zone 正确
[ ] coord 合理
[ ] exits 目标存在
[ ] 双向出口一致
[ ] 方向与坐标关系一致
[ ] Zone 边界明确
[ ] 关键地点可达
```

方向与坐标应保持一致：

```text
东 = x + 1
西 = x - 1
北 = y + 1
南 = y - 1
```

实际符号约定必须以当前 `MapEngine` 实现为准；不要仅凭视觉地图猜测坐标方向。

---

# 8. 新增 Zone 的标准流程

例如增加：

```text
guiyun_city
```

建议：

```text
1. 规划 Zone
2. 设计主干道路
3. 设计关键建筑
4. 给关键房间确定 coord
5. 建立 exits
6. 检查反向出口
7. 加 NPC
8. 加商店/物品
9. 加敌人
10. 加任务
11. 加剧情
12. 验证全部引用
13. 运行游戏
14. 检查 map
15. 检查 save/load
```

不要把大型城市全部无差别塞入旧 Zone。

---

# 9. 城市扩展的设计原则

大型城市建议独立 Zone：

```text
guiyun_city
```

城市内部可以继续划分：

```text
城门
主街
东市
西市
客栈
药铺
铁匠铺
官府
码头
武馆
民居
特殊地点
```

城市地图首先追求：

```text
空间合理
```

然后再追求：

```text
内容密度
```

---

# 10. `wuxia.py` 的处理原则

仓库中存在 `wuxia.py`。

它与当前模块化代码存在历史上的职责重叠，因此：

> 默认把 `wuxia.py` 当作 Legacy / 历史实现参考。

除非用户明确要求：

- 修复旧版单文件
- 保持旧启动方式
- 做迁移
- 比较新旧实现

否则新功能优先放入：

```text
main.py
engine.py
player.py
combat.py
actions.py
data/
```

不要为了“方便”重新把模块合并回 `wuxia.py`。

---

# 11. 存档兼容原则

修改：

```text
Player
room_id
属性字段
装备字段
任务字段
```

时必须考虑旧存档。

推荐兼容方式：

```text
旧数据
  ↓
兼容转换
  ↓
当前 Player
```

而不是要求所有旧存档作废。

---

# 12. AI 修改方式

推荐：

```text
阅读
 ↓
定位
 ↓
理解调用关系
 ↓
小范围修改
 ↓
静态检查
 ↓
运行
 ↓
验证
 ↓
再扩展
```

不要：

```text
需求
 ↓
全文件重写
```

---

# 13. 输出完整文件原则

如果用户要求：

> “给我完整代码”

必须给完整文件，而不是只给几个需要替换的片段。

如果用户不是程序员，更应该：

- 给出完整文件
- 明确文件路径
- 不要求用户自己寻找修改位置
- 保持 JSON 可直接复制使用

---

# 14. JSON 原则

标准 JSON：

```text
UTF-8
双引号
无尾逗号
无注释
结构完整
```

不要写：

```json
{
  // 这是注释
}
```

---

# 15. 新功能检查矩阵

任何较大功能至少检查：

| 层 | 检查内容 |
|---|---|
| 数据 | JSON 是否存在、格式是否正确 |
| 引擎 | 机制是否真的实现 |
| 玩家 | 状态是否保存 |
| 战斗 | 是否影响战斗 |
| 行为 | 是否有用户操作入口 |
| UI | 玩家是否能看到 |
| 存档 | save/load 是否兼容 |
| 地图 | 地点和引用是否正确 |
| 旧系统 | 是否破坏已有玩法 |

---

# 16. AI 接手新任务时的标准流程

收到：

> “增加归云城。”

不要立即写 JSON。

先：

```text
读取 README
读取 AI_CONTEXT
读取 ARCHITECTURE
读取 engine.py 的 MapEngine
读取当前 rooms 数据
读取 main.py 的地图/移动调用
```

然后再设计。

收到：

> “增加声望系统。”

先判断：

```text
Player 是否需要新字段
存档是否需要升级
NPC 是否读取声望
任务是否奖励声望
商店是否读取声望
剧情是否读取声望
```

收到：

> “增加毒伤。”

先检查：

```text
combat.py
状态结构
回合流程
伤害结算
状态持续
```

---

# 17. 不要假设 README 等于代码

README 是设计和维护指南。

真实行为最终以：

```text
当前源码
+
当前 JSON
```

为准。

如果 README 与代码冲突：

> **先以代码为准，并在完成修改后更新文档。**

---

# 18. 文档更新规则

重大变化后更新：

```text
README.md
AI_CONTEXT.md
ARCHITECTURE.md
```

至少包括：

```text
新增模块
新增数据类型
新增 Zone
新增系统
存档结构变化
重要兼容性变化
```

---

# 19. 长期发展目标

项目长期目标：

```text
数据驱动
+
模块化
+
可验证
+
可扩展
+
存档兼容
+
大型武侠世界
```

最终希望做到：

```text
代码负责规则
数据负责世界
MapEngine 负责空间
Player 负责角色状态
Combat 负责冲突
Actions 负责行为
Quest 负责目标
NPC 负责关系
剧情系统负责世界事件
```

---

# 20. 给 AI 的最终指令

维护本项目时始终遵守：

> **不要为了实现一个新功能而破坏已有功能。**
>
> **不要把数据问题硬编码到 Python。**
>
> **不要把核心规则偷偷放进 JSON。**
>
> **不要随意修改已有 ID。**
>
> **不要默认修改 `wuxia.py`。**
>
> **不要在不了解调用关系时重写核心文件。**
>
> **大型扩展先规划结构，再生成内容。**
>
> **每次修改都要考虑数据、逻辑、入口、UI、存档和兼容性。**

这份文件是 AI 的“接手说明书”。
