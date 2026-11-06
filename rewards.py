# -*- coding: utf-8 -*-
"""
rewards.py - 统一奖励结算层

P2.11：把战斗、任务及未来 NPC/剧情/宝箱奖励统一到同一个结算入口。
保持 V12 存档结构不变；奖励只修改已有的玩家成长/背包/世界状态字段。
"""

import engine
from item_feedback import add_inventory_items, format_item_change
from ui_output import safe_print as print

Color = engine.Color


def _amount(value, default=0):
    """读取固定奖励数值；区间奖励应在上游先解析。"""
    if isinstance(value, dict):
        return int(value.get("amount", value.get("min", default)))
    return int(value if value is not None else default)


def normalize_reward_items(reward):
    """把 item/items/drops 统一成 [(item_name, quantity)]。"""
    if not isinstance(reward, dict):
        return []

    raw = []
    if reward.get("item"):
        raw.append({"item": reward["item"], "quantity": reward.get("item_quantity", 1)})
    raw.extend(reward.get("items", []) or [])
    raw.extend(reward.get("drops", []) or [])

    normalized = []
    for entry in raw:
        if isinstance(entry, str):
            name, quantity = entry, 1
        elif isinstance(entry, dict):
            name = entry.get("item") or entry.get("name")
            quantity = entry.get("quantity", 1)
        else:
            continue
        if not name:
            continue
        normalized.append((str(name), int(quantity)))
    return normalized


def _safe_nonnegative_int(value, default=0):
    """读取旧档/运行态流水计数；异常值按 0 处理，避免奖励发放到一半才报错。"""
    try:
        if isinstance(value, bool):
            return max(0, int(default))
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return max(0, int(default))


def _prepare_reward_tracking(player):
    """在发放奖励前修复流水容器的形状和计数，避免已有脏数据造成半结算。"""
    economy_state = getattr(player, "economy_state", None)
    if not isinstance(economy_state, dict):
        economy_state = {}
        player.economy_state = economy_state
    events = economy_state.get("events")
    if not isinstance(events, dict):
        events = {}
        economy_state["events"] = events
    ledger = events.get("economic_flow_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
        events["economic_flow_ledger"] = ledger

    for key in ("player_reward_gold_created", "player_reward_item_units_created"):
        ledger[key] = min(2_000_000_000, _safe_nonnegative_int(ledger.get(key, 0)))

    item_totals = ledger.get("player_reward_items_created")
    if not isinstance(item_totals, dict):
        item_totals = {}
        ledger["player_reward_items_created"] = item_totals
    else:
        ledger["player_reward_items_created"] = {
            str(name): min(2_000_000_000, _safe_nonnegative_int(value))
            for name, value in item_totals.items()
        }

    flow_rows = events.get("economic_flow_history")
    if not isinstance(flow_rows, list):
        events["economic_flow_history"] = []


def _reward_tick(player):
    world_state = getattr(player, "world_state", {})
    variables = world_state.get("variables", {}) if isinstance(world_state, dict) else {}
    return _safe_nonnegative_int(variables.get("quest_clock", 0)) if isinstance(variables, dict) else 0


def validate_reward_bundle(reward):
    """在实际修改玩家状态前验证整个奖励包，避免半套奖励落地。"""
    if not isinstance(reward, dict):
        return False, "奖励数据必须是对象。"

    for field in ("exp", "gold"):
        if field in reward:
            try:
                value = _amount(reward[field])
            except (TypeError, ValueError, OverflowError):
                return False, f"{field} 奖励必须是有效的非负数值。"
            if value < 0:
                return False, f"{field} 奖励不能为负数。"

    try:
        normalized_items = normalize_reward_items(reward)
    except (TypeError, ValueError, OverflowError):
        return False, "奖励物品数量必须是有效整数。"
    for item_name, quantity in normalized_items:
        if item_name not in engine.ITEMS:
            return False, f"奖励物品不存在：【{item_name}】。"
        if quantity < 1:
            return False, f"奖励物品数量必须为正数：【{item_name}】。"

    sect_rep = reward.get("sect_reputation", {}) or {}
    if not isinstance(sect_rep, dict):
        return False, "门派声望奖励必须是对象。"
    for sect_name, delta in sect_rep.items():
        if sect_name not in engine.SECTS:
            return False, f"门派不存在：【{sect_name}】。"
        if not isinstance(delta, int) or isinstance(delta, bool):
            return False, f"门派声望奖励必须为整数：【{sect_name}】。"

    for field in ("honor_delta", "infamy_delta", "jianghu_amount"):
        if field in reward and (not isinstance(reward[field], int) or isinstance(reward[field], bool)):
            return False, f"江湖成长字段 {field} 必须为整数。"
    if reward.get("jianghu_action") is not None:
        if not isinstance(reward.get("jianghu_action"), str) or not reward["jianghu_action"].strip():
            return False, "jianghu_action 必须是非空字符串。"
        known_actions = {"help_people", "rescue_npc", "assist_officials", "escort_trade",
                         "black_market_trade", "refuse_factions", "solo_explore"}
        if reward["jianghu_action"] not in known_actions:
            return False, f"未知江湖路线行为：【{reward['jianghu_action']}】。"

    effects = reward.get("effects")
    if effects is not None:
        if not isinstance(effects, dict):
            return False, "世界状态奖励必须是对象。"
        for field in ("set_flags", "set_variables", "increment_variables", "faction_relations", "relations"):
            if field in effects and effects[field] is not None and not isinstance(effects[field], dict):
                return False, f"世界状态奖励 {field} 必须是对象。"
        for key, amount in (effects.get("increment_variables", {}) or {}).items():
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                return False, f"世界状态增量必须是数值：【{key}】。"
        for key, delta in (effects.get("relations", {}) or {}).items():
            if isinstance(delta, bool) or not isinstance(delta, int):
                return False, f"人物关系变化必须是整数：【{key}】。"
        for pair, delta in (effects.get("faction_relations", {}) or {}).items():
            if isinstance(delta, bool) or not isinstance(delta, int):
                return False, f"势力关系变化必须是整数：【{pair}】。"
            if isinstance(pair, str) and ":" in pair:
                a, b = pair.split(":", 1)
            elif isinstance(pair, (list, tuple)) and len(pair) == 2:
                a, b = pair
            else:
                return False, f"势力关系目标格式无效：【{pair}】。"
            if a not in engine.FACTIONS or b not in engine.FACTIONS or a == b:
                return False, f"势力关系目标无效：【{pair}】。"

    return True, ""


def apply_reward_bundle(player, reward, source="奖励", announce=True):
    """统一结算奖励包，返回结构化结果。

    支持旧格式：exp/gold/item；也支持 items/drops + quantity。
    可选 effects 使用与现有世界状态系统相同的 set_flags/set_variables/
    increment_variables 结构，不改变 SAVE_VERSION。
    """
    ok, message = validate_reward_bundle(reward)
    if not ok:
        if announce:
            print(f"{Color.RED}奖励暂时无法结算，请稍后重试。{Color.RESET}")
        return {"ok": False, "message": message, "exp": 0, "gold": 0, "items": []}

    exp = _amount(reward.get("exp", 0))
    gold = _amount(reward.get("gold", 0))
    items = normalize_reward_items(reward)

    # 先验证整个奖励包的背包容量，再修改经验、银两、声望或世界状态。
    # 物品格按 inventory 中的实际条目计数，与 Player 的既有容量约定一致。
    inventory = getattr(player, "inventory", None)
    capacity = getattr(player, "inventory_capacity", None)
    if items and not isinstance(inventory, list):
        message = "玩家背包数据异常，奖励未结算。"
        if announce:
            print(f"{Color.RED}{message}{Color.RESET}")
        return {"ok": False, "message": message, "exp": 0, "gold": 0, "items": []}
    if items and capacity is not None:
        try:
            current_slots = len(inventory)
            max_slots = max(0, int(capacity))
            incoming_slots = sum(quantity for _, quantity in items)
        except (TypeError, ValueError, OverflowError):
            message = "玩家背包容量数据无效，奖励未结算。"
            if announce:
                print(f"{Color.RED}{message}{Color.RESET}")
            return {"ok": False, "message": message, "exp": 0, "gold": 0, "items": []}
        if current_slots + incoming_slots > max_slots:
            message = f"背包空间不足（当前 {current_slots}/{max_slots} 格，需要 {incoming_slots} 格），奖励未结算。"
            if announce:
                print(f"{Color.RED}{message}{Color.RESET}")
            return {"ok": False, "message": message, "exp": 0, "gold": 0, "items": []}

    # 奖励真正改动经验/银两/物品前，先清理可能来自旧档或手工编辑的流水异常值。
    # 否则例如流水计数为 "bad" 时，玩家银两会先增加，随后才因 int 转换失败而中断。
    _prepare_reward_tracking(player)

    if exp:
        player.gain_exp(exp)
    elif announce and "exp" in reward:
        print(f"{Color.GREEN}获得了 0 点经验。{Color.RESET}")

    if gold:
        player.gold += gold
        # Alpha109：把任务、战斗、世界事件等统一奖励的货币增发记入流水。
        # 这是来源统计，不改变既有奖励数值，也不把玩家交易误记为新增货币。
        economy_state = player.economy_state
        events = economy_state["events"]
        ledger = events["economic_flow_ledger"]
        ledger["player_reward_gold_created"] = min(
            2_000_000_000, _safe_nonnegative_int(ledger.get("player_reward_gold_created", 0)) + gold,
        )
        flow_rows = events.get("economic_flow_history")
        if not isinstance(flow_rows, list):
            flow_rows = []
            events["economic_flow_history"] = flow_rows
        reward_tick = _reward_tick(player)
        flow_rows.append({"tick": reward_tick, "source": str(source)[:48], "direction": "获得奖励",
                          "item": "银两", "quantity": gold, "gold": gold, "counterparty": "系统"})
        if len(flow_rows) > 100:
            del flow_rows[:-100]
        if announce:
            print(f"{Color.YELLOW}{source}：银两 +{gold}。{Color.RESET}")
    elif announce and "gold" in reward:
        print(f"{Color.YELLOW}{source}：银两 +0。{Color.RESET}")

    for item_name, quantity in items:
        added, held = add_inventory_items(player, item_name, quantity, announce=False)
        if not added:
            # 背包容量已在前面统一校验；这里只防御异常行囊数据。
            print(f"{Color.RED}物品【{item_name}】未能放入行囊，奖励未结算。{Color.RESET}")
            return {"ok": False, "message": "行囊数据异常，奖励未结算。", "exp": 0, "gold": 0, "items": []}
        # 奖励物品属于外部注入，不是交易转移；单独统计，便于后续查找物品膨胀来源。
        economy_state = player.economy_state
        events = economy_state["events"]
        ledger = events["economic_flow_ledger"]
        ledger["player_reward_item_units_created"] = min(
            2_000_000_000, _safe_nonnegative_int(ledger.get("player_reward_item_units_created", 0)) + quantity,
        )
        item_totals = ledger.get("player_reward_items_created")
        if not isinstance(item_totals, dict):
            item_totals = {}
            ledger["player_reward_items_created"] = item_totals
        item_totals[item_name] = min(2_000_000_000, _safe_nonnegative_int(item_totals.get(item_name, 0)) + quantity)
        flow_rows = events.get("economic_flow_history")
        if not isinstance(flow_rows, list):
            flow_rows = []
            events["economic_flow_history"] = flow_rows
        reward_tick = _reward_tick(player)
        flow_rows.append({"tick": reward_tick, "source": str(source)[:48], "direction": "获得奖励",
                          "item": item_name[:48], "quantity": quantity, "gold": 0, "counterparty": "系统"})
        if len(flow_rows) > 100:
            del flow_rows[:-100]
        if announce:
            print(f"{Color.GREEN}{format_item_change(item_name, quantity, held, action='获得')}{Color.RESET}")
            evaluator = getattr(player, "evaluate_equipment", None)
            if evaluator:
                evaluation = evaluator(item_name)
                if evaluation:
                    label = {"upgrade": "推荐装备", "build_upgrade": "推荐：契合当前流派",
                             "sidegrade": "同级装备", "build_tradeoff": "流派变化型装备", "downgrade": "暂不推荐"}.get(evaluation["recommendation"], "装备")
                    print(f"{Color.BRIGHT_YELLOW}  └─ {label} | 评分 {evaluation['score']} "
                          f"(当前 {evaluation['current_score']}, {evaluation['score_delta']:+d}){Color.RESET}")
                    before = evaluation.get("build_before") or {}
                    after = evaluation.get("build_after") or {}
                    if after.get("name") != before.get("name") and after.get("name"):
                        print(f"{Color.BRIGHT_CYAN}  └─ 流派预览：{before.get('name', '无流派')} → {after['name']}{Color.RESET}")

    sect_rep_result = {}
    for sect_name, delta in (reward.get("sect_reputation", {}) or {}).items():
        changer = getattr(player, "change_sect_reputation", None)
        if changer and sect_name in engine.SECTS:
            new_rep = changer(sect_name, int(delta))
            sect_rep_result[sect_name] = new_rep
            if announce:
                print(f"{Color.MAGENTA}{source}：{sect_name} 门派声望 {int(delta):+d}，当前 {new_rep}。{Color.RESET}")

    # 江湖成长与物品/经验奖励在同一验证门之后执行；奖励包无效时不会提前改变声名。
    jianghu_changed = False
    jianghu_action = reward.get("jianghu_action")
    if jianghu_action:
        recorder = getattr(player, "record_jianghu_action", None)
        if recorder:
            jianghu_changed = bool(recorder(jianghu_action, reward.get("jianghu_amount", 1))) or jianghu_changed
    honor_delta = int(reward.get("honor_delta", 0) or 0)
    infamy_delta = int(reward.get("infamy_delta", 0) or 0)
    if honor_delta or infamy_delta:
        changer = getattr(player, "add_jianghu_reputation", None)
        if changer:
            changer(honor=honor_delta, infamy=infamy_delta)
            jianghu_changed = True

    effects = reward.get("effects")
    if effects:
        engine.apply_world_effects(player.world_state, effects)

    return {
        "ok": True,
        "message": "",
        "exp": exp,
        "gold": gold,
        "items": [{"item": name, "quantity": qty} for name, qty in items],
        "sect_reputation": sect_rep_result,
        "jianghu_changed": jianghu_changed,
        "effects_applied": bool(effects),
    }
