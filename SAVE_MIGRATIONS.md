# 存档迁移说明

当前存档版本：**v12**

## v10 → v11

新增：

```json
"world_state": {
  "flags": {},
  "variables": {}
}
```

同时校正旧位置别名：

- `cave` → `cave_entrance`
- `bandit_camp` → `bandit_courtyard`

如果旧存档的位置 ID 在当前地图中不存在，会安全回退到 `village_gate`，而不会让游戏直接崩溃。

迁移在读档时进行；只有玩家再次保存时，v11 数据才会正式写回存档文件。这样可以避免一次升级过程意外覆盖原始存档。


## v11 → v12

V12 正式持久化阶段任务 `quest_states`。

- 旧 `active_quests` 数据保持不变。
- 如果当前任务已经在新式 `stages` 定义中，则自动补出 `stage/progress`。
- 没有阶段任务的旧任务继续使用原有整数进度格式。
- 不删除玩家已有任务、物品、属性和世界状态。

## Alpha275：V12 读档时的动态状态恢复

本轮不提升存档版本，仍在读取 V12 数据时做类型收敛：

- 世界时钟、危机起止/恢复时刻、NPC 位置与自主行动计时统一转为安全整数；无法解析的值按字段默认值处理。
- 区域生态数值限制在 0–100；区域治安持久值限制在 -60–30；治安事件与危机救援比例按原有合法区间收敛。
- `npc_autonomy`、`faction_actions.history`、`faction_conflicts.history`、`dynamic_world_stability.faction_recovery`、`npc_information`、`player_information` 只保留可继续运行的记录结构。
- `quest_interventions`、`quest_competitions` 是“任务:配置 -> 最近触发时刻”的历史字典，读取时保留并规范整数时刻；日志列表字段若不是列表则重置为空列表。
- 合法数值、玩家任务、物品、势力关系与已有世界状态不会被改写；再次保存时写回规范化后的 V12 结构。
