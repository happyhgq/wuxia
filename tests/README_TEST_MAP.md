# 自动化测试地图

本文件只用于快速定位测试，不替代测试本身；现有测试文件不在本阶段批量移动或删除。

## 核心与兼容
- `test_v12_core.py`：V12 核心规则、角色、任务、关系、存档兼容等历史核心验收。
- `test_alpha280_color_constants_and_combat_smoke.py`：全项目颜色常量引用校验、未知颜色告警回退与严格模式报错，以及战斗普通攻击、Boss 阶段切换、武学招式、物品使用、逃跑、敌人行动、状态提示的冒烟回归。
- `test_alpha284_item_change_feedback.py`：统一获得/交付/消耗/售出文案与变动后持有量；任务交付先扣物后结算、数量不足拒绝、奖励失败按原顺序退还；消耗品/秘籍、锻造、奖励包与出售的原子增减和提示。
- `test_alpha285_balance_audit.py`：L1–15 等级表与旧档进度、L1–15 普通/精英/Boss 模板（含 Alpha286/287 覆盖值）、L10–12 普通怪可达性、17 个房间 `recommended_level` 兜底、守势减伤时机与数值、按实际房间档位计算的击杀任务经验比例、非击杀任务经验区间、Boss 刷新与 V12 存档版本。
- `test_alpha286_balance_tuning.py`：Boss 与 L8–12 普通怪 Alpha286 数值精确断言、非生命属性与掉落保持不变、9 项击杀任务奖励、15 项任务按实际房间实战经验计算的比例、任务总经验 11554 与 L14 门槛。
- `test_alpha287_sect_dps_and_boss_edges.py`：铁衣门破阵刀/铁衣功威力与效果字段、四门派最高威力区间、四首领 Alpha287 最终面板、经验/银两与 Boss 掉落保持不变。
- `test_alpha288_drop_gradient.py`：24 名穿戴装备敌人的普通/远程 2%、精英 5%、Boss 12% 掉率分档、双 Boss 0.2% 秘籍持有者、山贼宝库一次性探索秘籍（旗标防重复、8 次搜索仅 1 本）、Boss 保底材料与《清剿黑风山》玄铁重剑奖励不变。
- `test_alpha299a_npc_tiers.py`：T1/T2/T3 分层与 `always_available`、三间安全内室及自定义反向出口、`get_npc_current_state` 只读性与跨夜日程、T1 夜间在场、T2 离场与离场提示、任务 NPC 禁止 offstage、数据校验器 PASS。
- `test_alpha299c_inner_room_positioning.py`：三间 T1 内室统一按“夜间生活休息、白天私人空间”验收：安全区字段与双向父房出口、夜间日程落位、生活元素与铺面工作词过滤、昼夜文案切换、夜间人物生活状态、交谈与交付、铁匠内堂打烊仅拦买卖。
- `test_alpha300_npc_behavior.py`：五态常量、日程状态映射且不修改输入、未覆盖 NPC 的 action/场景/idle 回退、跨夜日程包装、只读观察不写 `npc_behaviors`、写 tick 只记录未覆盖 NPC、V12 存档往返。
- `test_alpha301_boss_telegraph.py`：四个首领招牌技能 ID 与 `telegraph` 标记、固定预警文案、预警回合无伤害且下一回合结算原技能、减伤仍生效、逃跑后预警状态不跨战斗泄漏、ANSI 复位。
- `test_alpha302_entry_events.py`：事件数据目标房间与时段、房间/时段/区域/条件/优先级筛选、`once` 与 `cooldown`、触发文本与记录、`look` 不触发、效果写入与 V12 存读档、快速旅行挂钩、主循环移动挂钩顺序。
- `test_alpha303_actor_view.py`：NPC 展示字段完整性、物品英文 ID 与布衣 `clothing` 归类、在场名单“头衔+称号+名字”（默认不显示拼音 ID，`关系` 标题保留 ID）、中文名/头衔/英文 ID 定位、五段式观察无元数据标签、女性代词与空装备省略、忙碌原因复用、`faction_conflict` 原因屏蔽、伤势等级、状态特征、名单单句号、`关系` 身份/势力/关系面板。
- `test_alpha304_talk_player_view.py`：玩家档案默认值与覆盖、`查看 自己` 五段式与装备段、自己/我/自身/self 别名、按等级生成武力评价、按气血比例生成伤势、`player_profile` 随 V12 存档往返、交谈无 `【NPC】`/`状态：` 元数据、忙碌自然语句、忙碌下接取委托、`关系` 状态/门派立场/印象面板、`injury_level` 三档与非法值忽略。
- `test_alpha305_talk_verb_busy_reply.py`：74 名固定 NPC 的 `talk_verb` 覆盖与格式、主对话行使用 NPC 专属措辞、未知 NPC 回退“说道”、忙碌无话题单句短应答（无关系变化/委托/时钟推进）、势力冲突忙碌通用句不泄露原因、重复忙碌交谈仍在场且时钟不变、忙碌带话题仍展示委托、忙碌接引人仍给新手引导。
- `test_alpha306_world_ambience.py`：旧档天色静默初始化、黄昏消息只报一次、NPC 移动优先于天色、同一 NPC 移动只推最后一条、最多五条且天色顺延、同方向同出口同类型移动合并并保留全部人名、不同方向/类型/特殊移动不合并、六名 NPC 超出上限时 `look` 人物列表仍实时列出全部在场者、`blocked` 抑制后补推、场景声响 6 刻间隔与区域取词、推送标记随 V12 存读档往返、主循环中动态消息位于指令输出之前、单步行动六阶段顺序完整、批量推进只报抵达阶段、空行只在有推送时出现且消息间不空行、`collect_messages` 候选顺序与延后来源。
- `test_p41_weather_seasons.py`：旧档静默初始化晴天、只在黎明换天且不连续重复、天气持续 1–3 天、逐步与跳跃推进得到同一序列、24 节气顺序与四季边界、节气每 15 天只播报一次、跨节气/跨天气只报抵达状态不补旧消息、天色与换天合并为一条、室内同轮先报天色再报室内换天、推送顺序为“车马 > 天色 > 天气 > 节气”、满五条时天气与节气顺延且天气状态仍推进、下一次只补最新换天、状态面板不显示被挤占的旧天色、`blocked` 抑制后补推、室内只用檐外/远处视角、室外与室内换天文案分离、非晴天室外天色措辞与室内常规天色、`weather_world` 随 V12 存读档往返、状态面板“立春 · 晴”格式、帮助说明天气不影响玩法数值。
- `test_p42_ambience_enhancements.py`：新角色首日引导天气在 10 次行动内转阴、20 次内落雨、最后一段从下一个黎明起按正常 1–3 天对齐、旧档/直接构造角色不命中引导、引导状态随 V12 往返、tick 5 读档续跑后仍于 8/16 刻变化、跳刻只报抵达状态不补中间阴天；普通行动车马按 tick+场景确定性低频触发、只对有正方向出口的房间生效、与停留共用至少 2 刻间隔、无“停留”也能在普通行动中推送、停留仍必推；有窗室内（含锁闭地字一号房）使用“窗外”换天文案、无窗室内保持“檐外”、室外与两者措辞互不相同、客栈二楼换天集成验证；晴/阴播报换天文案，雨/雷雨/雪/雾在阶段切换时使用专属天色且不重复换天。
- `test_alpha307_p2_copy_ui.py`：室外天色文案不假定街巷/屋脊/更鼓、晴天与雨雪雾的室外/室内取词分流、移动命令识别（方向别名与房间出口）、移动环境播报在抵达后按目的地取词、敌情列表中文顿号、商店缺物品提示使用中文动作示例、装备升级评分全角标点与“输入装备”提示。
- `test_p1_region_danger_labels.py`：`look` 与 `区域` 指令将势力冲突等级标为“势力动向”，与独立的环境“危险度”并列（断魂岭平静 + 极危不再显得矛盾）；安全区/室内仍只显示“安全”。
- `test_p1_autosave_throttle.py`：自动存档按世界 Tick 节流（3 刻内只写一次并挂起待写）、跨过间隔后立即写入、显式存档清空挂起状态、无 `autosave` 的测试替身回退为直接保存。
- `test_region_effects_infrastructure.py`：`region_effects` 写入并读取地区持久治安、叠加时保留既有事件记录、超出 -60~30 自动夹紧、非法区域/非数值/布尔与未知字段被忽略、`region_effects` 类型非法时整个效果不落盘、校验器接受合法配置并拒绝未知区域/未知字段/非整数/越界、不含 `region_effects` 的效果不受影响。
- `test_quest_herb_destination.py`：`百草堂·药材去向` 的前置（补齐药材 + `world:main:herb_stock_replenished`）与两个结局定义；行商结局的银两、主世界商路/通行/治安变化、青石村↔商会与村长/药铺老板关系；留村结局的疗伤药、侠名、治安/商路变化与势力/NPC 关系；两种结局后 `区域` 分别出现“商路繁荣”“治安较好”；未指定结局时列出两项且不结算；交付结算时按结局打印 `区域变化：主世界 …` 实际增量（行商 安全度 -3/商路 +12/通行 +4，留村 安全度 +8/商路 -4）。
- `test_npc_herb_destination_dialogue.py`：村长与药铺老板在行商结局后说“行商车队出村/货被拉走”，在留村结局后说“药材留在村里”，去向未定时仍回退到“药材补齐”旧台词，任务进行中询问“药材去向”则解释行商出价与村长顾虑；带话题询问在无对应情报时先回退到条件对白（不再回“并不知道什么信息”），确无条件对白时仍回“不知道”；同一 NPC 在两种世界状态下输出不同。
- `test_northfront_blackmarket_settlement.py`：`北境暗线·了断` 的前置（完成北境失货追查 + 沉星黑市、L8）与四阶段目标；封死暗线/留一线暗路/设卡查验三结局仅在对应前置旗标下可选，且每名玩家至少有两项可选、不会静默自动结算；三结局各自的银两、侠义/恶名、江胡行动、世界旗标、北境商镇与归云城区域增量、势力关系与 NPC 关系；歧义交付列出全部可选结局；巡河老兵与北境货栈掌柜按封/留/查验及任务进行中切换台词，未满足任何结局时回落到基础台词。
- `test_sect_closure_endings.py`：四门派收束任务（少林/武当/华山/铁衣门）的发布与交付 NPC、前置委托/等级/门派声望、三阶段目标；每条线的前两个结局只在对应中段分支旗标下可选、第三项始终可选，分支均未选时只剩中道结局不静默结算；每门派三种结局各自的银两、侠义/恶名、门派声望、物品、江湖行动、世界旗标、门派山场区域增量、势力与两名 NPC 关系、结算区域提示；接取写入进行中旗标，缺前置/等级/声望时拒绝；颁布 NPC 与协助 NPC 按三种结局及任务进行中切换台词，未结算时回落到基础台词。
- `test_guiyun_threeway.py`：归云三方中盘主线（`归云三方·探风` → `暗流交锋` → `定局三择`）的发布/交付 NPC、L9–11 与前置链；探风需完成 `沉星黑市`，交锋需探风旗标，定局需交锋旗标；交锋首阶段三选一调查倾向（官府/商会/黑市）各自写旗标、变量与侠义/恶名；定局三结局（扶商宽市/严法安城/夜市通融）均有独立经验、银两、物品、侠义/恶名、变量、势力与 NPC 关系、`guiyun_city` 区域增量与结算提示，三结局旗标互斥且区域数值互不相同；默认三项全可选并提示选择、不静默结算；五名 NPC（会长/捕头/管事/陆文清/文书）按结局及任务进行中切换台词，旧档无新旗标时回退基础台词，且完成 `沉星黑市` 的旧档只看到探风开放。
- `test_sect_l15_exclusivity.py`：四门派 L15 委托的互斥后果——首次完成本门委托时本门声望 +8、其余三门各 -2，并写入 `world:sect_l15:*` 效力旗标；复做仍只结经验/银两/断魂精铁，不动任何门派声望，`repeat_reward` 保持 `exp/gold/items` 且不含 `region_effects`；退门文案列出替本门出手后各门声望并提示转投不抹旧账，转投目标门派声望为负时入门提示需修复嫌隙；跨门派连做会累积负声望（少林→武当后四门为 +6/+6/-4/-4），V12 存读档保留旗标与声望；数据校验器通过。
- `test_alpha306_map_direction_consistency.py`：全图出口方向与坐标步进一致、对向出口完整（单向/弯折出口白名单）、青石村口→长街→广场→后街逐级北移且旧街名不再出现、NPC 对话文案不再引用旧街名。
- `test_alpha306_npc_movement_cadence.py`：日程移动后同一世界时刻不被再次拉回、在岗守卫连续多个时刻不离岗且无往返播报、同一 NPC 单轮只保留一条移动播报、在岗巡逻原地记录行动。
- `conftest.py`：全局自动夹具把无参 `save_to_file()`（默认 `engine.SAVE_PATH`）重定向到 `tmp_path`，确保全量测试不会覆盖正式存档；显式传入临时路径的存读档测试不受影响。
- `test_alpha298_inn_second_floor.py`：悦来客栈二楼数据与安全区、上下楼别名不覆盖历史指令、垂直移动各耗时 1 时刻、客房专用下楼提示、锁门拒绝、观察与地图分区标题、探索与随机遭遇拦截、苏挽晴四种药品报价库存、旧档 NPC 名册回退、跨楼层消息与同层方向消息分离。
- `test_alpha289_duanhun_ridge.py`：断魂岭 6 场景坐标/出口/双向连通与旧烽台北接、全图可达性、L13–15 敌人模板/装备/掉率/变体/Boss 阶段与掉落、装备数值、守岭猎户与三任务前置/奖励/复做冷却、区域元数据、V12 存读档保留任务与堡垒旗标。
- `test_alpha290_patrol_repeat_reward.py`：巡道除匪首做 300 经验/90 银两、复做 160 经验/60 银两的数据契约与实际交付分流、48 tick 冷却与复做时间戳写入、复做奖励不含永久成长字段。
- `test_alpha291_l15_endgame.py`：断魂精铁材料与断魂崖夜行客 L15 精英模板/保底掉落/240 秒刷新、断魂堡门守卫长 60 秒刷新的第二条必掉精铁来源与任务提示、敌人级刷新覆盖与旧普通/Boss 默认计时兼容、四门派 L15 终局委托的前置/首做与复做奖励/不含永久成长、精铁换药采集交付与数量不足拒绝、终局面板内容与只读性、第五子面板导航/提示符/80 列宽度、V12 存读档保留满级进度。
- `test_alpha307_stage_effect_idempotency.py`：最终阶段达标后重复击杀不再重复结算阶段效果，待选分支阶段重复触发不重置进度，分支选择后阶段效果仍只结算一次。
- `test_alpha292_sanren_panel_and_tieyi_skills.py`：散人 `exclusive_skills` 与全部可学武学一致、门派总览/详情显示 7 招且折行不超 80 列、7 招无授课地点门槛可学；铁衣门横练铁布衫/裂石断岳刀精确数值与 `skill_teachers` 覆盖、演武场/职位/声望门槛、四派最高威力差 ≤0.35、V12 存读档保留新武学熟练度。
- `test_alpha293_display_roles_prompt_and_color_switch.py`：语义色表正文/标题/战斗角色、auto 对 `NO_COLOR`/`TERM=dumb`/非 TTY 的判断、显式开关与重定向日志去 ANSI、`颜色` 指令与只读时钟策略、`> ` 与战斗气血提示符、78 列统一折行、中文宽字符输入行清理。
- `test_alpha294_world_time_policy.py`：tick 0 = 卯时 06:00、经济工时与 NPC 日程共用左闭右开边界、只读查看不推进世界、交易/采集/锻造/旅行/任务等普通交互各 1 个时刻、交谈按对话路径计时、失败交谈不耗时、状态面板显示世界时间。
- `test_alpha295_npc_utility_behavior.py`：工作时段优先营生、夜间休息、饭点用餐、任务发布者锚定、受阻状态原地停留、需求值有界且噪声稳定、只沿真实出口移动一步、`utility_profile` 为可选配置且引用真实房间、效用状态在 V12 `world_state` 内往返。
- `test_alpha296_inn_overnight.py`：`ticks_until_next_dawn` 跨昼夜换算、住店成功恢复气血/内力并报告真实睡眠步数、主循环睡到卯时 06:00、失败住店不耗时、不新增存档字段。
- `test_alpha297_failed_commands_cost_no_time.py`：买不起/卖无货/无路线旅行/攻击无目标/锻造材料不足或取消/装备或使用不存在物品/无钱吃饭/走错方向均不耗时；成功买卖、旅行与吃饭仍各 1 个时刻。
- `test_p40_command_policy_module.py`：命令可否处理、是否推进世界、只读命令集合与 `events`/`skills` 子命令区分的既有契约。
- `test_p40_command_world_tick_contract.py`：纯查看不耗时、交易/采集/锻造/旅行等各 1 刻、失败动作不耗时、控制命令不推进世界、未知命令在 Tick 前被拒绝、`停留` 与住店时序。
- `test_p40_quest_tick_order.py`：限时任务最后一个准时时刻交付成功、委托人日程边界仍可交付、交付未接取任务/非法分支选择/放弃未知任务不耗时、放弃成功推进 1 刻。
- `test_p40_preflight_failures.py`：采矿/伐木/搜寻/采集的确定性失败不耗时且保留提示；武学学习/遗忘、门派地点与等级门槛、晋升/修习、未知事件、治安未知子命令、属性非法输入均不耗时；成功搜寻/采矿/加点与资源耗尽仍按旧时序推进。
- `test_p40_p2_feedback_and_save_order.py`：满血/接近满血疗伤按实际恢复量播报；延迟自动存档在动作后 Tick 完成才落盘、显式路径立即写入；不存在的内/外出口不耗时。
- `test_alpha275_v12_save_recovery_long_cycle.py`：异常字段类型的 V12 读档恢复、合法动态状态保留、二次存读档续跑与跨系统长周期一致性。
- `test_phase28_30_save_safety.py`：原子保存、备份、损坏存档恢复。
- `test_phase46_48_content_localization.py`、`test_phase31_33_command_safety.py`：内容与指令安全相关验收。

## 地图、探索与玩家界面
- `test_phase22_24_ecology.py`、`test_phase25_27_region_intel.py`、`test_p32_alpha55_hidden_exploration.py`：区域、探索和隐藏内容。
- `test_alpha121_terminal_layout_consistency.py`、`test_alpha122_terminal_color_wrap.py`、`test_alpha123_terminal_sgr_state.py`、`test_alpha124_compact_zmud_ui.py`、`test_alpha125_terminal_layout_consistency.py`、`test_alpha128_status_panel.py`、`test_alpha130_label_alignment.py`、`test_alpha133_new_player_map_labels.py`、`test_alpha135_scene_action_hints.py`、`test_alpha136_read_only_commands_do_not_tick.py`：终端排版、提示和只读命令行为。
- `test_alpha278_inventory_stack_use_and_wrapping.py`：同名叠放物品单件消耗与剩余、括号/空白归一化、歧义编号候选与序号使用、候选过期、单行使用反馈无存档噪声、背包标点优先折行、带括号装备匹配及品质变体选择。
- `test_p32_alpha25_help_navigation_consistency.py`、`test_alpha126_action_feedback.py`、`test_alpha115_action_result_feedback.py`：帮助与动作反馈。
- `test_help_world_rules.py`：帮助第十四类“世界规则”三页概念说明——门派声望（范围、L15 首次 +8/−2、复做冻结、退门保留）、选择与后果（分支/交付定结局命令、区域变化三项、结局互斥）、终局目标（L15 软上限、3500 经验、状态按 5 打开面板）；名称/别名直达、无 command 字段、行宽与帮助导航。

## 经济、交易与商队
- `test_p32_economy_*.py`、`test_p32_alpha*_economy*.py`：经济状态、资金、价格、生产和长期运行。
- `test_p32_alpha104_caravan_trade_atomicity.py`、`test_p32_alpha131_failed_trade_no_wallet_bootstrap.py`：交易原子性与失败安全。
- `test_p32_alpha51_npc_production_caravan_loop.py`、`test_p32_alpha78_npc_economy_workflow.py`、`test_p32_alpha110_consumption_ledger.py`、`test_p32_alpha111_caravan_ore_payment.py`：NPC 生产消耗与商队流转。
- `test_alpha137_trade_save_load_continuity.py`、`test_alpha139_regional_market_isolation.py`、`test_alpha140_economy_long_cycle_acceptance.py`：近期存档连续性、区域隔离和长期经济验收。
- `test_alpha273_merchant_caravan_trade_consistency.py`：商人/商队交易资格、真实库存与售罄、货架报价与实际成交一致、出售回补库存、错认交易对象、商队歧义候选与 V12 库存存档往返。

## 区域、NPC 与危机
- `test_p32_alpha61_daily_villagers.py`、`test_p32_alpha64_residence_schedule.py`、`test_p32_alpha74_world_activity.py`、`test_p32_alpha77_npc_work_hours.py`、`test_p32_alpha81_lifecycle_and_ecology.py`：NPC 日常与区域生态。
- `test_p32_alpha85_security_events.py`、`test_p32_alpha88_crisis_response.py`、`test_p32_alpha91_crisis_action_outcomes.py`、`test_p32_alpha93_crisis_relief_trade_link.py`、`test_p32_alpha94_crisis_supply_link.py`：治安、危机及其后果。
- `test_alpha274_region_security_crisis_linkage.py`：危机扣分与持久治安隔离、巡逻上限、到期治安事件、危机触发巡查/恶人池、额外恶人与街头惯犯的重生过滤。
- `test_alpha276_busy_interaction_and_quest_names.py`：忙碌 NPC 的在场/交谈/交易/接取/交付、暂离仍拦截、任务列表与详情显示名、新旧名称匹配交付、交付提示名称一致、NPC 委托分层与别名解析。
- `test_alpha277_quest_delivery_state_and_chat_separation.py`：目标完成（待交付）与已交付区分、前置提示“需先交付”、目标达成后的委托人/地点/指令、单一候选禁止自动结算、序号交付、任务列表与详情待交付标记、默认交谈不泄露闲聊、明确闲聊触发及默认/详细委托分层。
- `test_alpha279_business_activity_cleanup.py`：默认场景不显示后台“近期营生”、主动查询自然化且不泄露时辰/单价/内部字段、本地商情只取当前场景、无人场景查询、查看商情路由、在场工匠/采集者的真实营生状态、歇工后仍显示休息及帮助/指令入口。
- `test_alpha306b_wait_command.py`：停留/停注册为同一指令、每次推进 1 个时刻、街巷车马与室内过客按场景取词、方向和邻接地名取自真实出口、无方位出口场景不生成车马、满 5 条上限时车马顺延、连续停留不复用同一句/句式、室内场景声响不混入街巷犬吠、无动态停留反馈轮换、主循环无动态时回退提示、V12 保存仅写 `ambient_world` 子字典、帮助列出停留；全图 `indoor` 标记房间统一使用室内过客与室内声响，露天街巷/院落/演武场保持室外取词。

## 使用方式
- 全量回归：`python -m pytest -q`
- Python 编译：`python -m compileall -q .`
- 数据校验：`python data_validator.py`

新增测试优先使用明确的 Alpha/阶段名，并覆盖行为契约；测试文件名可以按历史保留，不为整齐而破坏导入路径。

- `test_alpha242_unified_quest_state_help.py`：31 项任务的发布/交付 NPC 与地点审计、条件不足不泄露目标、接取后任务列表、ask/交谈同处理器、忙碌 NPC 可正常交谈与接取、错误 NPC 交付提示、帮助文案及公告栏消息上限。

- `test_alpha244_resource_quest_integration.py`：四类新手任务实际资源/击杀进度、交付与物品消耗；两项新野外后续任务的前置条件、公告线索解锁、奖励与世界对白反馈。

- `test_alpha309_duanhun_expansion.py`：断魂岭 12 房拓扑、反向出口与可达性；L14/L15 新敌人数值与掉落；房间档位不越级；击杀任务经验比；狼皮/镖局镖箱/断剑残锋登记；三名 T3 NPC；三条新委托的门槛、奖励、旗标、关系与 `region_effects`；镖货采集交付与消耗；剑冢交付后果；条件台词；V12 往返。
