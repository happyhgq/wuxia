import json
import os
import time
import random
from .state import EconomyState
from world_time import world_hour

def _safe_int(value, default=0):
    """把旧存档或配置中的异常数值安全转换为整数。"""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)

def _dict_at(parent, key):
    """确保嵌套状态字段是字典，避免损坏存档在 Tick 中触发异常。"""
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value

def _record_regional_market_trade(state, world_rooms, room_id, item, amount, supply_delta, unit_price):
    """把商队在实际停靠地区的成交同步到区域行情；不改动全局统计的既有口径。"""
    room = world_rooms.get(str(room_id), {}) if isinstance(world_rooms, dict) else {}
    region = str(room.get("zone", "")) if isinstance(room, dict) else ""
    if not region:
        return
    regional_market = state.regional_market if isinstance(state.regional_market, dict) else {}
    state.regional_market = regional_market
    region_rows = regional_market.get(region)
    if not isinstance(region_rows, dict):
        region_rows = {}
        regional_market[region] = region_rows
    key = str(item)
    row = region_rows.get(key)
    if not isinstance(row, dict):
        row = {"traded": 0, "last_price": max(1, _safe_int(unit_price, 1)), "supply": 20}
        region_rows[key] = row
    row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))) + max(0, _safe_int(amount)))
    row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20)) + _safe_int(supply_delta)))
    row["last_price"] = max(1, _safe_int(unit_price, 1))


def _adjust_regional_market_supply(state, world_rooms, room_id, item, amount):
    """按生产/消耗地点调整区域可供量，不把生产过程伪记为买卖成交。"""
    room = world_rooms.get(str(room_id), {}) if isinstance(world_rooms, dict) else {}
    region = str(room.get("zone", "")) if isinstance(room, dict) else ""
    if not region:
        return
    regional_market = state.regional_market if isinstance(state.regional_market, dict) else {}
    state.regional_market = regional_market
    rows = regional_market.get(region)
    if not isinstance(rows, dict):
        rows = {}
        regional_market[region] = rows
    key = str(item)
    row = rows.get(key)
    if not isinstance(row, dict):
        row = {"traded": 0, "last_price": 5, "supply": 20}
        rows[key] = row
    row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20)) + _safe_int(amount)))


def _within_work_hours(work_hours, tick):
    """按世界钟点判断是否在工作时间，区间为左闭右开 [开始, 结束)。

    与 NPC 日常日程共用同一套边界语义：结束钟点属于下一班次，
    例如 [7, 18] 表示 07:00–17:59。省略工时表示全天；开始与结束
    相同视为没有工时。
    """
    if not isinstance(work_hours, list) or len(work_hours) != 2:
        return True
    start = max(0, min(23, _safe_int(work_hours[0], 0)))
    end = max(0, min(23, _safe_int(work_hours[1], 23)))
    if start == end:
        return False
    hour = world_hour(max(0, _safe_int(tick)))
    return start <= hour < end if start < end else (hour >= start or hour < end)


def _record_world_activity(state, kind, actor, action, item, amount, room_id="", detail=""):
    """记录由真实库存/资金变动产生的世界活动；限制长度，兼容旧存档。"""
    events = state.events if isinstance(state.events, dict) else {}
    state.events = events
    rows = events.get("world_activity")
    if not isinstance(rows, list):
        rows = []
        events["world_activity"] = rows
    rows.append({
        "tick": max(0, _safe_int(state.tick)),
        "kind": str(kind)[:24],
        "actor": str(actor)[:48],
        "action": str(action)[:32],
        "item": str(item)[:48],
        "amount": max(0, min(9999, _safe_int(amount))),
        "room_id": str(room_id)[:64],
        "detail": str(detail)[:100],
    })
    if len(rows) > 100:
        del rows[:-100]


def _register_caravan_arrival(state, caravan_id, room_id, stay_ticks=3):
    """统一登记到场状态与公告；同一商队同一地点同一 Tick 只触发一次。"""
    if room_id not in ("village_square", "guiyun_central_square"):
        return
    events = state.events if isinstance(state.events, dict) else {}
    state.events = events
    arrivals = _dict_at(events, "caravan_last_arrival_tick")
    arrival_key = f"{caravan_id}:{room_id}"
    if _safe_int(arrivals.get(arrival_key, -1), -1) == state.tick:
        return
    arrivals[arrival_key] = state.tick
    active = _dict_at(events, "active_caravans")
    active[arrival_key] = {"name": caravan_id, "room": room_id, "until_tick": state.tick + max(1, _safe_int(stay_ticks, 3))}
    pending = events.get("pending_world_announcements")
    if not isinstance(pending, list):
        pending = []
        events["pending_world_announcements"] = pending
    square_name = "村中广场" if room_id == "village_square" else "天衡广场"
    # 商队到场只发布一条简洁的商旅消息，避免世界公告与江湖传闻重复刷屏。
    pending.append(f"【商旅消息】{caravan_id}带来沿途货物，正在{square_name}停留。")
    # 长时间离线或批量推进世界 Tick 时，公告可能无人领取；只保留最近 100 条，避免存档无限膨胀。
    if len(pending) > 100:
        del pending[:-100]


class EconomyManager:
    """负责资源恢复、铁匠生产与商队路线的轻量世界 Tick。"""
    # Alpha294：城镇资金池的税源参数。商税只在商户钱包与资金池之间转移，
    # 不新增货币；资金池接近目标时停征，避免国库无限囤积。
    TOWN_TAX_INTERVAL = 10
    TOWN_TAX_BASE_RATE = 0.015
    TOWN_TAX_RESERVE = 200
    CARAVAN_TAX_RESERVE = 800
    TOWN_TREASURY_TARGET = 8000

    def __init__(self, state=None, data_dir=None, real_time_regen=False):
        self.state = EconomyState(state)
        self.real_time_regen = bool(real_time_regen)
        self.data_dir = data_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "economy")
        self.resources = self._load("resources.json")
        self.recipes = self._load("recipes.json")
        self.caravan_config = self._load("caravans.json")
        self.gatherers = self._load("gatherers.json")
        try:
            with open(os.path.join(os.path.dirname(self.data_dir), "rooms.json"), encoding="utf-8") as f:
                self.world_rooms = json.load(f)
        except (OSError, ValueError, TypeError):
            self.world_rooms = {}

    def _load(self, name):
        try:
            with open(os.path.join(self.data_dir, name), encoding="utf-8") as f:
                value = json.load(f)
            return value if isinstance(value, (dict, list)) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def apply_world_progress(self, world_state=None):
        """按已完成的世界委托调整真实采集、供料与资源配置，不增加存档字段。"""
        world_state = world_state if isinstance(world_state, dict) else {}
        flags = world_state.get("flags", {}) if isinstance(world_state.get("flags", {}), dict) else {}

        if flags.get("world:main:mistwood_boardwalk_repaired"):
            gatherer = self.gatherers.get("樵夫老周", {}) if isinstance(self.gatherers, dict) else {}
            if isinstance(gatherer, dict):
                gatherer["capacity"] = max(20, _safe_int(gatherer.get("capacity", 16), 16))
                gatherer["amount"] = max(3, _safe_int(gatherer.get("amount", 2), 2))
                gatherer["interval"] = min(3, max(1, _safe_int(gatherer.get("interval", 4), 4)))
            carpenter = self.recipes.get("木匠老许", {}) if isinstance(self.recipes, dict) else {}
            if isinstance(carpenter, dict):
                for route in carpenter.get("supplier_routes", []) if isinstance(carpenter.get("supplier_routes", []), list) else []:
                    if isinstance(route, dict) and route.get("item") == "木材" and "樵夫老周" in route.get("suppliers", []):
                        route["max_stock"] = max(6, _safe_int(route.get("max_stock", 3), 3))
                        route["max_per_tick"] = max(4, _safe_int(route.get("max_per_tick", 3), 3))
                        route["interval"] = min(8, max(1, _safe_int(route.get("interval", 12), 12)))

        if flags.get("world:main:abandoned_mine_supply_secured"):
            gatherer = self.gatherers.get("矿工顾三", {}) if isinstance(self.gatherers, dict) else {}
            if isinstance(gatherer, dict):
                gatherer["capacity"] = max(14, _safe_int(gatherer.get("capacity", 10), 10))
                gatherer["amount"] = max(4, _safe_int(gatherer.get("amount", 3), 3))
                gatherer["interval"] = min(4, max(1, _safe_int(gatherer.get("interval", 5), 5)))
            for recipe_id in ("铁匠", "百炼铁铺铁匠"):
                recipe = self.recipes.get(recipe_id, {}) if isinstance(self.recipes, dict) else {}
                if not isinstance(recipe, dict):
                    continue
                recipe["interval"] = min(4, max(1, _safe_int(recipe.get("interval", 5), 5)))
                for route in recipe.get("supplier_routes", []) if isinstance(recipe.get("supplier_routes", []), list) else []:
                    if isinstance(route, dict) and route.get("item") == "铁矿石" and "矿工顾三" in route.get("suppliers", []):
                        route["max_stock"] = max(8, _safe_int(route.get("max_stock", 3), 3))
                        route["max_per_tick"] = max(4, _safe_int(route.get("max_per_tick", 1), 1))
                        route["interval"] = min(4, max(1, _safe_int(route.get("interval", 8), 8)))

        if flags.get("world:main:deep_iron_gallery_cleared"):
            resource = self.resources.get("deep_iron_gallery", {}) if isinstance(self.resources, dict) else {}
            if isinstance(resource, dict):
                resource["capacity"] = max(34, _safe_int(resource.get("capacity", 28), 28))
                resource["regen_amount"] = max(4, _safe_int(resource.get("regen_amount", 3), 3))
            # 清理深矿后，村中铁匠才有稳定原料尝试打造精铁剑。
            # 城内铁铺继续制作铁剑，避免一次性把基础装备供给全部替换掉。
            smith = self.recipes.get("铁匠", {}) if isinstance(self.recipes, dict) else {}
            if isinstance(smith, dict):
                smith["interval"] = max(6, _safe_int(smith.get("interval", 6), 6))
                smith["inputs"] = {"铁矿石": 8}
                smith["outputs"] = {"精铁剑": 1}
                smith["output_capacity"] = {"精铁剑": 3}
                smith["trade_prices"] = {"精铁剑": 150}
        return self

    def _collect_town_tax(self):
        """按城镇商业与治安征收商户周转银两，转入城镇资金池。

        商税只调整既有钱包余额，不创造货币；低治安会降低实收比例，
        资金池达到目标储备后停止征收，避免税款无限囤积。
        """
        interval = max(1, _safe_int(self.TOWN_TAX_INTERVAL, 10))
        if self.state.tick % interval:
            return 0
        town_gold = max(0, _safe_int(self.state.town_gold))
        room = max(0, _safe_int(self.TOWN_TREASURY_TARGET, 8000) - town_gold)
        if room <= 0:
            return 0
        events = self.state.events if isinstance(self.state.events, dict) else {}
        ecology = events.get("region_ecology", {}) if isinstance(events, dict) else {}
        row = ecology.get("guiyun_city", {}) if isinstance(ecology, dict) else {}
        commerce = max(0, min(100, _safe_int(row.get("commerce", 70), 70))) if isinstance(row, dict) else 70
        security = max(0, min(100, _safe_int(row.get("security", 70), 70))) if isinstance(row, dict) else 70
        # 商业决定税基，治安决定实收；两者都取区域生态快照，缺省时按中立值计算。
        activity = commerce * 0.7 + security * 0.3
        rate = max(0.004, min(0.03, float(self.TOWN_TAX_BASE_RATE) * activity / 70.0))
        # 资金池低于目标储备一半时逐步提税，避免城镇在商户/商队仍有余钱时先见底。
        target = max(0, _safe_int(self.TOWN_TREASURY_TARGET, 8000))
        deficit = max(0.0, (target * 0.5 - town_gold) / max(1.0, target * 0.5))
        rate = min(0.03, rate * (1.0 + deficit))
        reserve = max(0, _safe_int(self.TOWN_TAX_RESERVE, 200))
        collected = 0
        for npc_id, value in list(self.state.npc_gold.items()):
            balance = max(0, _safe_int(value))
            taxable = max(0, balance - reserve)
            tax = int(taxable * rate)
            if tax <= 0:
                continue
            tax = min(tax, room - collected)
            if tax <= 0:
                break
            self.state.npc_gold[npc_id] = balance - tax
            collected += tax
        # 商队长期囤积货款同样会让城镇无钱进货；对超出周转储备的部分征收行商税，
        # 仍只是资金转移，商队保留足够本钱继续沿途收购。
        caravan_reserve = max(0, _safe_int(self.CARAVAN_TAX_RESERVE, 800))
        for caravan in self.state.caravans.values():
            if not isinstance(caravan, dict):
                continue
            balance = max(0, _safe_int(caravan.get("gold", 0)))
            taxable = max(0, balance - caravan_reserve)
            tax = int(taxable * rate)
            if tax <= 0:
                continue
            tax = min(tax, room - collected)
            if tax <= 0:
                break
            caravan["gold"] = balance - tax
            collected += tax
        if collected:
            self.state.town_gold = min(2_000_000_000, town_gold + collected)
            ledger = _dict_at(events, "economy_money_ledger")
            ledger["town_tax_collected"] = min(
                2_000_000_000, _safe_int(ledger.get("town_tax_collected", 0)) + collected
            )
        return collected

    def export_state(self):
        return self.state.to_dict()

    def recent_world_activity(self, limit=20):
        """返回最近的 NPC 世界活动，供场景提示、状态面板或测试调用。"""
        events = self.state.events if isinstance(self.state.events, dict) else {}
        rows = events.get("world_activity", [])
        if not isinstance(rows, list):
            return []
        count = max(0, min(100, _safe_int(limit, 20)))
        return [dict(row) for row in rows[-count:] if isinstance(row, dict)] if count else []

    def economic_audit_snapshot(self):
        """汇总模拟层可见的资金与实物库存，供长周期经济审计使用。

        该快照不把行情 supply 当作实物库存，也不把交易额当作新增资金；
        玩家背包与任务/战斗奖励不在 EconomyManager 管辖范围内，不能据此声称是全游戏总量。
        """
        state = self.state
        npc_gold = sum(max(0, _safe_int(value, 0)) for value in state.npc_gold.values())
        caravan_gold = 0
        item_totals = {}
        npc_item_units = 0
        caravan_item_units = 0
        for stock in state.npc_inventory.values():
            if not isinstance(stock, dict):
                continue
            for item, amount in stock.items():
                amount = max(0, _safe_int(amount, 0))
                item_totals[str(item)] = item_totals.get(str(item), 0) + amount
                npc_item_units += amount
        for caravan in state.caravans.values():
            if not isinstance(caravan, dict):
                continue
            caravan_gold += max(0, _safe_int(caravan.get("gold", 0)))
            cargo = caravan.get("inventory", {})
            if not isinstance(cargo, dict):
                continue
            for item, amount in cargo.items():
                amount = max(0, _safe_int(amount, 0))
                item_totals[str(item)] = item_totals.get(str(item), 0) + amount
                caravan_item_units += amount
        ledger = state.events.get("economy_money_ledger", {}) if isinstance(state.events, dict) else {}
        if not isinstance(ledger, dict):
            ledger = {}
        return {
            "tick": max(0, _safe_int(state.tick, 0)),
            "tracked_gold": npc_gold + caravan_gold + max(0, _safe_int(state.town_gold, 0)),
            "npc_gold": npc_gold,
            "caravan_gold": caravan_gold,
            "town_gold": max(0, _safe_int(state.town_gold, 0)),
            "npc_item_units": npc_item_units,
            "caravan_item_units": caravan_item_units,
            "tracked_item_units": npc_item_units + caravan_item_units,
            "item_totals": dict(sorted(item_totals.items())),
            "seeded_npc_gold": max(0, _safe_int(ledger.get("seeded_npc_gold", 0))),
            "seeded_caravan_gold": max(0, _safe_int(ledger.get("seeded_caravan_gold", 0))),
            "seeded_trade_counterparty_gold": max(0, _safe_int(ledger.get("seeded_trade_counterparty_gold", 0))),
            "destroyed_caravan_upkeep": max(0, _safe_int(ledger.get("destroyed_caravan_upkeep", 0))),
            "town_tax_collected": max(0, _safe_int(ledger.get("town_tax_collected", 0))),
        }

    def npc_work_status(self, npc_id):
        """返回 NPC 当前营生状态，供交谈/场景提示使用，不改变游戏状态。"""
        npc_id = str(npc_id)
        hour = world_hour(max(0, _safe_int(self.state.tick)))
        gather_cfg = self.gatherers.get(npc_id, {}) if isinstance(self.gatherers, dict) else {}
        recipe = self.recipes.get(npc_id, {}) if isinstance(self.recipes, dict) else {}
        cfg = gather_cfg if isinstance(gather_cfg, dict) and gather_cfg else recipe
        stock = self.state.npc_inventory.get(npc_id, {})
        if not isinstance(stock, dict):
            stock = {}
        if not cfg:
            return {"npc": npc_id, "status": "暂无营生记录", "hour": hour}
        hours = cfg.get("work_hours")
        if not _within_work_hours(hours, self.state.tick):
            return {"npc": npc_id, "status": "已歇工", "detail": "眼下不是做工时辰", "hour": hour}
        if npc_id in self.gatherers:
            item = str(cfg.get("item", "草药"))
            capacity = max(0, _safe_int(cfg.get("capacity", 12), 12))
            amount = max(0, _safe_int(stock.get(item, 0)))
            if amount >= capacity:
                return {"npc": npc_id, "status": "货物已满", "detail": f"{item}已存满，暂时不再采集", "hour": hour}
            room_id = str(cfg.get("resource_room_id", ""))
            resource = self.state.resources.get(room_id, {})
            if isinstance(resource, dict) and _safe_int(resource.get("remaining", 0)) <= 0:
                return {"npc": npc_id, "status": "等待资源恢复", "detail": "附近资源暂时耗尽", "hour": hour}
            return {"npc": npc_id, "status": "正在营生", "detail": f"正在获取{item}", "hour": hour}
        inputs = cfg.get("inputs", {})
        if isinstance(inputs, dict):
            for item, need in inputs.items():
                if _safe_int(stock.get(item, 0)) < _safe_int(need, 0):
                    routes = cfg.get("supplier_routes", [])
                    if routes:
                        return {"npc": npc_id, "status": "等待原料", "detail": f"{item}不足，正等待进货", "hour": hour}
                    return {"npc": npc_id, "status": "缺少原料", "detail": f"{item}不足，暂时无法制作", "hour": hour}
        outputs = cfg.get("outputs", {})
        caps = cfg.get("output_capacity", {})
        if isinstance(outputs, dict) and isinstance(caps, dict):
            for item in outputs:
                if _safe_int(stock.get(item, 0)) >= _safe_int(caps.get(item, 999999)):
                    return {"npc": npc_id, "status": "成品待售", "detail": f"{item}库存已满，等待售出", "hour": hour}
        return {"npc": npc_id, "status": "正在营生", "detail": "按库存和原料安排制作", "hour": hour}

    PROFESSION_NAMES = {"mine": "采矿", "chop": "伐木", "gather": "采集"}
    PROFESSION_THRESHOLDS = (5, 15, 30, 50, 75)

    def profession_level(self, action):
        name = self.PROFESSION_NAMES.get(str(action), str(action))
        rows = self.state.professions if isinstance(self.state.professions, dict) else {}
        row = rows.get(name, {}) if isinstance(rows, dict) else {}
        xp = max(0, _safe_int(row.get("xp", 0))) if isinstance(row, dict) else 0
        return 1 + sum(xp >= threshold for threshold in self.PROFESSION_THRESHOLDS)

    def record_profession_action(self, action, amount=1):
        """记录玩家真实采集成果；NPC 的自动生产不调用此方法。"""
        name = self.PROFESSION_NAMES.get(str(action))
        if not name:
            return None
        professions = self.state.professions
        if not isinstance(professions, dict):
            professions = {}
            self.state.professions = professions
        row = professions.get(name)
        if not isinstance(row, dict):
            row = {"xp": 0, "actions": 0, "level": 1}
            professions[name] = row
        amount = max(1, min(999, _safe_int(amount, 1)))
        before_level = self.profession_level(action)
        row["xp"] = min(1_000_000, max(0, _safe_int(row.get("xp", 0))) + amount)
        row["actions"] = min(1_000_000, max(0, _safe_int(row.get("actions", 0))) + 1)
        row["level"] = self.profession_level(action)
        row["total_gathered"] = min(1_000_000, max(0, _safe_int(row.get("total_gathered", 0))) + amount)
        next_threshold = next((t for t in self.PROFESSION_THRESHOLDS if row["xp"] < t), None)
        return {"name": name, "xp": row["xp"], "level": row["level"],
                "leveled_up": row["level"] > before_level, "next_threshold": next_threshold}

    def profession_summary(self):
        result = []
        for action, name in self.PROFESSION_NAMES.items():
            rows = self.state.professions if isinstance(self.state.professions, dict) else {}
            row = rows.get(name, {}) if isinstance(rows, dict) else {}
            xp = max(0, _safe_int(row.get("xp", 0))) if isinstance(row, dict) else 0
            level = self.profession_level(action)
            next_threshold = next((t for t in self.PROFESSION_THRESHOLDS if xp < t), None)
            result.append({"name": name, "level": level, "xp": xp, "next_threshold": next_threshold,
                           "actions": max(0, _safe_int(row.get("actions", 0))) if isinstance(row, dict) else 0,
                           "total_gathered": max(0, _safe_int(row.get("total_gathered", 0))) if isinstance(row, dict) else 0})
        return result

    def _harvest(self, room_id, quantity=1, action="mine", max_quantity=None):
        cfg = self.resources.get(room_id)
        if not isinstance(cfg, dict):
            return False, "此处没有可采集的资源。"
        configured_action = str(cfg.get("action", "mine"))
        if configured_action != action:
            return False, "此处没有适合当前操作的资源。"
        row = self.state.resources.setdefault(room_id, {
            "remaining": max(0, _safe_int(cfg.get("capacity", 20))),
            "last_tick": self.state.tick,
        })
        if not isinstance(row, dict):
            row = {"remaining": max(0, _safe_int(cfg.get("capacity", 20))), "last_tick": self.state.tick}
            self.state.resources[room_id] = row
        remaining = max(0, _safe_int(row.get("remaining", 0)))
        if remaining <= 0:
            return False, "这处资源暂时耗尽了，请过些时日再来。"
        base_yield_max = max(1, _safe_int(cfg.get("yield_max", 3)))
        # 熟练等级 3 起，玩家每次成功采集有机会固定获得额外一份；仍受资源储量、
        # 场景单次上限和背包剩余空间约束。NPC 生产走独立逻辑，不吃玩家熟练加成。
        bonus = 1 if self.profession_level(action) >= 3 else 0
        quantity = max(1, _safe_int(quantity, 1)) + bonus
        quantity = min(quantity, base_yield_max + bonus, remaining)
        if max_quantity is not None:
            quantity = min(quantity, max(0, _safe_int(max_quantity)))
        if quantity <= 0:
            return False, "行囊已满，无法继续采集。"
        row["remaining"] = remaining - quantity
        # Alpha81：每次成功采集的每一份资源独立计时，现实时间到期后逐份恢复。
        # 这样后续采集不会重置之前已经开始的恢复进度，且计时队列会随经济状态存档。
        try:
            regen_seconds = max(1, int(cfg.get("regen_seconds", 0))) if self.real_time_regen else 0
        except (TypeError, ValueError, OverflowError):
            regen_seconds = 0
        if regen_seconds:
            now = time.time()
            # 采集动作可能发生在两次世界 Tick 之间。先补算此前停留在本场景的暂停时长，
            # 再给新采集的资源单独起算，避免新资源被错误地额外延迟一个命令间隔。
            events = self.state.events if isinstance(self.state.events, dict) else {}
            if events.get("last_player_location") == room_id:
                try:
                    last_check = float(row.get("regen_check_at", now))
                except (TypeError, ValueError, OverflowError):
                    last_check = now
                paused_seconds = max(0.0, now - last_check)
                prior_due = row.get("regen_due", [])
                if paused_seconds and isinstance(prior_due, list):
                    row["regen_due"] = [stamp + paused_seconds if isinstance(stamp, (int, float)) else stamp for stamp in prior_due]
            due = row.get("regen_due", [])
            if not isinstance(due, list):
                due = []
            due.extend([now + regen_seconds] * quantity)
            row["regen_due"] = due[:max(0, int(cfg.get("capacity", 20)))]
            row["regen_check_at"] = now
            row["last_harvest_at"] = now
        else:
            row["last_harvest_at"] = time.time()
        return True, (str(cfg.get("item", "铁矿石")), quantity)

    def mine(self, room_id, quantity=1, max_quantity=None):
        return self._harvest(room_id, quantity, "mine", max_quantity)

    def chop(self, room_id, quantity=1, max_quantity=None):
        return self._harvest(room_id, quantity, "chop", max_quantity)

    def gather(self, room_id, quantity=1, max_quantity=None):
        """采集草药等可再生资源，与玩家和 NPC 共用同一处资源储量。"""
        return self._harvest(room_id, quantity, "gather", max_quantity)

    def update(self, steps=1, player_location=None):
        # player_location 用于暂停玩家当前场景的资源恢复计时；不传时保持旧调用行为。
        # 旧版/手工修改过的存档可能包含类型错误的嵌套字段，先修复容器结构。
        for field in ("resources", "npc_inventory", "npc_gold", "caravans", "market", "regional_market", "events", "professions"):
            _dict_at(self.state.__dict__, field)
        previous_player_location = self.state.events.get("last_player_location") if isinstance(self.state.events, dict) else None
        for key, value in list(self.state.resources.items()):
            if not isinstance(value, dict): self.state.resources[key] = {}
        for key, value in list(self.state.npc_inventory.items()):
            if not isinstance(value, dict):
                self.state.npc_inventory[key] = {}
                continue
            # 旧存档/损坏状态中的 NPC 库存统一归一化，避免负数、字符串和超大数量
            # 在生产、贸易与长周期模拟中扩散。
            for item_name, amount in list(value.items()):
                value[item_name] = min(9999, max(0, _safe_int(amount, 0)))
        # 采集型 NPC 的库存上限不仅约束未来产出，也约束读取的旧存档。
        for npc_id, cfg in (self.gatherers.items() if isinstance(self.gatherers, dict) else []):
            if not isinstance(cfg, dict):
                continue
            stock = self.state.npc_inventory.get(npc_id)
            if not isinstance(stock, dict):
                continue
            item_name = str(cfg.get("item", "草药"))
            capacity = max(0, _safe_int(cfg.get("capacity", 12), 12))
            if item_name in stock:
                stock[item_name] = min(capacity, max(0, _safe_int(stock[item_name], 0)))
        # 生产成品遵守配方库存上限，旧存档也在第一个 Tick 前完成修复。
        for npc_id, recipe in (self.recipes.items() if isinstance(self.recipes, dict) else []):
            if not isinstance(recipe, dict):
                continue
            stock = self.state.npc_inventory.get(npc_id)
            caps = recipe.get("output_capacity", {})
            if not isinstance(stock, dict) or not isinstance(caps, dict):
                continue
            for item_name, cap in caps.items():
                if item_name in stock:
                    stock[item_name] = min(max(0, _safe_int(cap, 0)), max(0, _safe_int(stock[item_name], 0)))
        for key, value in list(self.state.caravans.items()):
            if not isinstance(value, dict): self.state.caravans[key] = {}
        for key, value in list(self.state.market.items()):
            if not isinstance(value, dict):
                value = {}
                self.state.market[key] = value
            value["traded"] = min(2_000_000_000, max(0, _safe_int(value.get("traded", 0))))
            value["supply"] = min(9999, max(0, _safe_int(value.get("supply", 20), 20)))
            value["last_price"] = min(1_000_000, max(0, _safe_int(value.get("last_price", 5), 5)))
        for region, rows in list(self.state.regional_market.items()):
            if not isinstance(rows, dict):
                self.state.regional_market[region] = {}
                continue
            for item, row in list(rows.items()):
                if not isinstance(row, dict):
                    rows[item] = {"traded": 0, "last_price": 5, "supply": 20}
                    row = rows[item]
                row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))))
                row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20), 20)))
                row["last_price"] = min(1_000_000, max(0, _safe_int(row.get("last_price", 5), 5)))
        for key, value in list(self.state.npc_gold.items()):
            self.state.npc_gold[key] = min(2_000_000_000, max(0, _safe_int(value, 1000)))
        # Alpha107：经济 NPC 的起始资金只发放一次，后续交易不得通过“缺少钱包时默认 1000”反复造钱。
        # 旧 V12 存档首次进入新版时也只补齐一次缺失的钱包；已有余额完全保留。
        wallet_events = _dict_at(self.state.events, "economy_money_ledger")
        if not wallet_events.get("initial_wallets_seeded"):
            actors = set(str(key) for key in self.gatherers) | set(str(key) for key in self.recipes)
            for recipe in self.recipes.values() if isinstance(self.recipes, dict) else []:
                if not isinstance(recipe, dict):
                    continue
                for route in recipe.get("supplier_routes", []) if isinstance(recipe.get("supplier_routes", []), list) else []:
                    if isinstance(route, dict):
                        actors.update(str(x) for x in route.get("suppliers", []) if x)
            seeded = 0
            for actor in sorted(actors):
                if actor not in self.state.npc_gold:
                    self.state.npc_gold[actor] = 1000
                    seeded += 1000
            wallet_events["initial_wallets_seeded"] = True
            wallet_events["seeded_npc_gold"] = min(2_000_000_000, _safe_int(wallet_events.get("seeded_npc_gold", 0)) + seeded)
        self.state.town_gold = min(2_000_000_000, max(0, _safe_int(self.state.town_gold)))
        for name, row in list(self.state.professions.items()):
            if not isinstance(row, dict):
                self.state.professions[name] = {"xp": 0, "actions": 0, "level": 1, "total_gathered": 0}
                row = self.state.professions[name]
            row["xp"] = min(1_000_000, max(0, _safe_int(row.get("xp", 0))))
            row["actions"] = min(1_000_000, max(0, _safe_int(row.get("actions", 0))))
            row["total_gathered"] = min(1_000_000, max(0, _safe_int(row.get("total_gathered", 0))))
            action = next((a for a, label in self.PROFESSION_NAMES.items() if label == name), None)
            row["level"] = self.profession_level(action) if action else min(6, max(1, _safe_int(row.get("level", 1), 1)))
        for _ in range(max(0, _safe_int(steps))):
            self.state.tick += 1
            # 周期性行情事件只改变报价倍率，不凭空创造商品或资金。
            events = _dict_at(self.state.__dict__, "events")
            market_event = events.get("market_event")
            if isinstance(market_event, dict) and _safe_int(market_event.get("until_tick", -1), -1) <= self.state.tick:
                events.pop("market_event", None)
                events["market_event_rate"] = 1.0
                market_event = None
            if not isinstance(market_event, dict) and self.state.tick > 0 and self.state.tick % 30 == 0:
                cycle = (self.state.tick // 30 - 1) % 3
                event_rows = (("山货需求上扬", 1.15), ("药材行情回落", 0.90), ("兵器采购旺季", 1.20))
                event_name, event_rate = event_rows[cycle]
                events["market_event"] = {"name": event_name, "rate": event_rate, "until_tick": self.state.tick + 10}
                events["market_event_rate"] = event_rate
                pending = events.get("pending_world_announcements")
                if not isinstance(pending, list):
                    pending = []
                    events["pending_world_announcements"] = pending
                pending.append(f"【江湖行情】{event_name}，各地行商报价随行情变化。")
                if len(pending) > 100:
                    del pending[:-100]
            # 地区性行情事件：每 45 Tick 轮换一个区域，事件到期后自动失效。
            regional_events = _dict_at(events, "regional_market_events")
            for zone, event_row in list(regional_events.items()):
                if not isinstance(event_row, dict) or _safe_int(event_row.get("until_tick", -1), -1) <= self.state.tick:
                    regional_events.pop(zone, None)
            if self.state.tick > 0 and self.state.tick % 45 == 0:
                zone_rows = (("mistwood", "山林药材需求增加", 1.18),
                             ("guiyun_city", "城中兵器采购增多", 1.16),
                             ("northfront_town", "北境补给价格上涨", 1.20),
                             ("main", "村镇山货行情转旺", 1.12))
                zone, event_name, rate = zone_rows[((self.state.tick // 45) - 1) % len(zone_rows)]
                regional_events[zone] = {"name": event_name, "rate": rate, "until_tick": self.state.tick + 12}
                pending = events.get("pending_world_announcements")
                if not isinstance(pending, list):
                    pending = []
                    events["pending_world_announcements"] = pending
                pending.append(f"【地区行情】{event_name}，本地商贩报价暂时变化。")
                if len(pending) > 100:
                    del pending[:-100]
            # 同步时钟供交易报价判断事件是否到期；兼容旧存档缺少该字段。
            events["tick"] = self.state.tick
            # 城镇资金池向商队购货需要持续税源；商税在商户钱包与资金池间转移。
            self._collect_town_tax()
            active_caravans = _dict_at(self.state.events, "active_caravans")
            for active_id, active in list(active_caravans.items()):
                if not isinstance(active, dict) or _safe_int(active.get("until_tick", -1), -1) <= self.state.tick:
                    active_caravans.pop(active_id, None)
            # 市场供给指标每 10 Tick 缓慢向常态值回归。该指标只影响报价，
            # 不会生成真实物品；真实库存仍由采集、生产和交易系统管理。
            if self.state.tick % 10 == 0:
                baseline = 20
                for market_item, market_row in self.state.market.items():
                    if not isinstance(market_row, dict):
                        continue
                    supply = min(9999, max(0, _safe_int(market_row.get("supply", 20), 20)))
                    if supply < baseline:
                        market_row["supply"] = supply + 1
                    elif supply > baseline:
                        market_row["supply"] = supply - 1
                    else:
                        market_row["supply"] = baseline
                # 各区域供需分别向常态值回归，保留地区行情差异但避免永久极端价格。
                for regional_rows in self.state.regional_market.values():
                    if not isinstance(regional_rows, dict):
                        continue
                    for regional_row in regional_rows.values():
                        if not isinstance(regional_row, dict):
                            continue
                        supply = min(9999, max(0, _safe_int(regional_row.get("supply", 20), 20)))
                        if supply < baseline:
                            regional_row["supply"] = supply + 1
                        elif supply > baseline:
                            regional_row["supply"] = supply - 1
                        else:
                            regional_row["supply"] = baseline

            # 资源每隔设定 Tick 恢复，储量永不超过上限。
            for room_id, cfg in self.resources.items():
                if not isinstance(cfg, dict): continue
                row = self.state.resources.setdefault(room_id, {"remaining": _safe_int(cfg.get("capacity", 20)), "last_tick": self.state.tick})
                if not isinstance(row, dict):
                    row = {"remaining": _safe_int(cfg.get("capacity", 20)), "last_tick": self.state.tick}
                    self.state.resources[room_id] = row
                capacity = max(0, _safe_int(cfg.get("capacity", 20)))
                # 先归一化存档中的资源数值，不能让旧版/损坏存档在恢复周期前
                # 暂时保留超过资源点上限的储量或负数。
                row["remaining"] = min(capacity, max(0, _safe_int(row.get("remaining", 0))))
                row["last_tick"] = max(0, _safe_int(row.get("last_tick", self.state.tick)))
                # Alpha81 优先使用现实秒计时。旧资源配置没有 regen_seconds 时，继续沿用旧 Tick 规则。
                try:
                    regen_seconds = max(0, int(cfg.get("regen_seconds", 0))) if self.real_time_regen else 0
                except (TypeError, ValueError, OverflowError):
                    regen_seconds = 0
                if regen_seconds:
                    now = time.time()
                    # 玩家停留在资源点时，恢复计时暂停；离开时把停留期间的真实时间
                    # 加回每份资源的到期时间。使用上次世界 Tick 的位置，确保离开场景的
                    # 那一刻也会正确结算最后一段停留时间。
                    try:
                        last_check = float(row.get("regen_check_at", now))
                    except (TypeError, ValueError, OverflowError):
                        last_check = now
                    if player_location is not None and previous_player_location == room_id:
                        paused_seconds = max(0.0, now - last_check)
                        if paused_seconds:
                            due_before_pause = row.get("regen_due", [])
                            if isinstance(due_before_pause, list):
                                row["regen_due"] = [stamp + paused_seconds if isinstance(stamp, (int, float)) else stamp for stamp in due_before_pause]
                    row["regen_check_at"] = now
                    # 旧存档没有逐份计时队列时，为已经消耗的储量补建恢复记录；
                    # 仅首次迁移时初始化，空队列不代表新资源再次被消耗。
                    if "regen_due" not in row and row["remaining"] < capacity:
                        missing = capacity - row["remaining"]
                        row["regen_due"] = [now + regen_seconds] * min(capacity, missing)
                    due = row.get("regen_due", [])
                    if not isinstance(due, list):
                        due = []
                    ready = sum(1 for stamp in due if isinstance(stamp, (int, float)) and stamp <= now)
                    if ready:
                        row["remaining"] = min(capacity, row["remaining"] + ready)
                        left = ready
                        kept = []
                        for stamp in due:
                            if left and isinstance(stamp, (int, float)) and stamp <= now:
                                left -= 1
                            else:
                                kept.append(stamp)
                        row["regen_due"] = kept
                    else:
                        row["regen_due"] = [stamp for stamp in due if isinstance(stamp, (int, float))][:capacity]
                else:
                    interval = max(1, _safe_int(cfg.get("regen_interval", 8)))
                    if self.state.tick - row["last_tick"] >= interval:
                        row["remaining"] = min(capacity, row["remaining"] + max(0, _safe_int(cfg.get("regen_amount", 2))))
                        row["last_tick"] = self.state.tick
            # NPC 采集职业按周期补充自己的库存，库存有上限，避免无限囤积。
            gather_progress = _dict_at(self.state.events, "gather_progress")
            for npc_id, cfg in (self.gatherers.items() if isinstance(self.gatherers, dict) else []):
                if not isinstance(cfg, dict):
                    continue
                # 可选职业工时按世界 Tick 的 24 小时循环；未配置工时的旧配置保持原行为。
                if not _within_work_hours(cfg.get("work_hours"), self.state.tick):
                    continue
                interval = max(1, _safe_int(cfg.get("interval", 3)))
                gather_progress[npc_id] = _safe_int(gather_progress.get(npc_id, 0)) + 1
                if gather_progress[npc_id] < interval:
                    continue
                gather_progress[npc_id] = 0
                item = str(cfg.get("item", "草药"))
                amount = max(1, _safe_int(cfg.get("amount", 1)))
                # NPC 采集必须绑定真实资源点。缺少资源点、资源点配置损坏或物品不匹配时，
                # 不能仅凭 gatherers.json 凭空生成材料；数据修正后即可恢复生产。
                resource_room = str(cfg.get("resource_room_id", ""))
                resource_cfg = self.resources.get(resource_room)
                if not resource_room or not isinstance(resource_cfg, dict):
                    continue
                if str(resource_cfg.get("item", "")) != item:
                    continue
                # 物品名称相同并不代表资源点可被任意职业采集：例如草药点不能被矿工
                # 当成矿脉，林木点也不能被采药人消耗。显式 action 优先，旧配置则按物品推断。
                expected_action = str(cfg.get("action", "")).strip()
                if not expected_action:
                    expected_action = {"木材": "chop", "铁矿石": "mine"}.get(item, "gather")
                resource_action = str(resource_cfg.get("action", "mine")).strip() or "mine"
                if resource_action != expected_action:
                    continue
                # 库存上限是硬约束，不能因为单次采集量较大而自动抬高上限。
                # 例如 amount=3、capacity=1 时，每轮最多只允许补到 1；capacity=0 则停产。
                cap = max(0, _safe_int(cfg.get("capacity", 12), 12))
                stock = self.state.npc_inventory.setdefault(npc_id, {})
                if not isinstance(stock, dict):
                    self.state.npc_inventory[npc_id] = stock = {}
                current = min(cap, max(0, _safe_int(stock.get(item, 0))))
                gathered = min(amount, max(0, cap - current))
                if gathered:
                    resource_row = self.state.resources.setdefault(resource_room, {
                        "remaining": max(0, _safe_int(resource_cfg.get("capacity", 20))),
                        "last_tick": self.state.tick,
                    })
                    if not isinstance(resource_row, dict):
                        resource_row = {"remaining": 0, "last_tick": self.state.tick}
                        self.state.resources[resource_room] = resource_row
                    available = max(0, _safe_int(resource_row.get("remaining", 0)))
                    gathered = min(gathered, available)
                    resource_row["remaining"] = available - gathered
                    try:
                        regen_seconds = max(0, int(resource_cfg.get("regen_seconds", 0))) if self.real_time_regen else 0
                    except (TypeError, ValueError, OverflowError):
                        regen_seconds = 0
                    if regen_seconds and gathered:
                        due = resource_row.get("regen_due", [])
                        if not isinstance(due, list): due = []
                        due.extend([time.time() + regen_seconds] * gathered)
                        resource_row["regen_due"] = due[:max(0, _safe_int(resource_cfg.get("capacity", 20)))]
                        resource_row["last_harvest_at"] = time.time()
                if gathered:
                    stock[item] = current + gathered
                    _record_world_activity(self.state, "采集", npc_id, "采集", item, gathered,
                                           str(cfg.get("room_id", resource_room)), "从实际资源点取得")
            # 制作 NPC 可按配方中的供应路线采购真实原料；采购会同步扣减供应者库存与双方资金，
            # 不凭空生成材料或银两。先补齐最低制作需求，避免无限囤货。
            for buyer_id, recipe in (self.recipes.items() if isinstance(self.recipes, dict) else []):
                if not isinstance(recipe, dict):
                    continue
                routes = recipe.get("supplier_routes", [])
                if not isinstance(routes, list) or not routes:
                    continue
                buyer_stock = self.state.npc_inventory.setdefault(buyer_id, {})
                if not isinstance(buyer_stock, dict):
                    self.state.npc_inventory[buyer_id] = buyer_stock = {}
                for route in routes:
                    if not isinstance(route, dict):
                        continue
                    item = str(route.get("item", ""))
                    suppliers = route.get("suppliers", [])
                    inputs = recipe.get("inputs", {})
                    if not item or not isinstance(suppliers, list) or not isinstance(inputs, dict) or item not in inputs:
                        continue
                    try:
                        price = max(1, min(1_000_000, int(route.get("unit_price", 1))))
                        max_per_tick = max(0, min(999, int(route.get("max_per_tick", 1))))
                        target_stock = max(0, min(9999, int(route.get("max_stock", inputs.get(item, 0)))))
                        required = max(0, int(inputs.get(item, 0)))
                        purchase_interval = max(1, min(10000, int(route.get("interval", 1))))
                    except (TypeError, ValueError, OverflowError):
                        continue
                    # 定期采购让供需更平缓，避免制作 NPC 每个 Tick 都抽干供应者库存。
                    if not _within_work_hours(recipe.get("work_hours"), self.state.tick):
                        continue
                    procurement_progress = _dict_at(self.state.events, "supplier_purchase_progress")
                    progress_key = f"{buyer_id}:{item}"
                    progress = _safe_int(procurement_progress.get(progress_key, 0)) + 1
                    if progress < purchase_interval:
                        procurement_progress[progress_key] = progress
                        continue
                    procurement_progress[progress_key] = 0
                    current = max(0, _safe_int(buyer_stock.get(item, 0)))
                    desired = min(max_per_tick, max(0, min(target_stock, required) - current))
                    buyer_wallet = min(2_000_000_000, max(0, _safe_int(self.state.npc_gold.get(buyer_id, 0), 0)))
                    for supplier_id in suppliers:
                        if desired <= 0:
                            break
                        supplier_stock = self.state.npc_inventory.get(str(supplier_id), {})
                        if not isinstance(supplier_stock, dict):
                            continue
                        available = max(0, _safe_int(supplier_stock.get(item, 0)))
                        supplier_wallet = min(2_000_000_000, max(0, _safe_int(self.state.npc_gold.get(str(supplier_id), 0), 0)))
                        affordable = buyer_wallet // price
                        supplier_room = max(0, (2_000_000_000 - supplier_wallet) // price)
                        transfer = min(desired, available, affordable, supplier_room, max(0, 9999 - current))
                        # Alpha94：供应者所在地区的通行危机会压低跨区原料交割量。
                        # 只影响真实采购数量，不凭空扣库存/资金；危机缓解或结束后自动恢复。
                        supplier_cfg = self.gatherers.get(str(supplier_id), {}) if isinstance(self.gatherers, dict) else {}
                        supplier_room_id = str(supplier_cfg.get("room_id", "")) if isinstance(supplier_cfg, dict) else ""
                        supplier_room_info = self.world_rooms.get(supplier_room_id, {}) if isinstance(self.world_rooms, dict) else {}
                        supplier_zone = str(supplier_room_info.get("zone", "")) if isinstance(supplier_room_info, dict) else ""
                        crisis_rows = self.state.events.get("world_crises", {}) if isinstance(self.state.events, dict) else {}
                        supplier_crisis = crisis_rows.get(supplier_zone, {}) if isinstance(crisis_rows, dict) else {}
                        if isinstance(supplier_crisis, dict):
                            penalty = max(0, min(100, _safe_int(supplier_crisis.get("travel_penalty", 0))))
                            if penalty > 0:
                                delivery_factor = max(0.25, 1.0 - penalty / 50.0)
                                transfer = min(transfer, int(transfer * delivery_factor))
                        if transfer <= 0:
                            continue
                        total = transfer * price
                        supplier_stock[item] = available - transfer
                        buyer_stock[item] = current + transfer
                        current += transfer
                        desired -= transfer
                        buyer_wallet -= total
                        supplier_wallet = min(2_000_000_000, supplier_wallet + total)
                        self.state.npc_gold[buyer_id] = buyer_wallet
                        self.state.npc_gold[str(supplier_id)] = supplier_wallet
                        _record_world_activity(self.state, "交易", buyer_id, "采购原料", item, transfer,
                                               str(recipe.get("room_id", "")), f"向{supplier_id}采购，单价{price}文")
                        market_row = self.state.market.setdefault(item, {"traded": 0, "last_price": price, "supply": 20})
                        market_row["traded"] = min(2_000_000_000, max(0, _safe_int(market_row.get("traded", 0))) + transfer)
                        market_row["last_price"] = price
                        # Alpha95：供应者到制作 NPC 属于 NPC 之间的库存转移，不能把同一批原料
                        # 先按采购扣一次市场供给、又在制作消耗时再扣一次。市场供给只在原料
                        # 真正被制作消耗（或其他面向市场的交易）时变化。

            # 铁匠只消耗真实库存中的铁矿，不会凭空生产。
            for npc_id, stock in list(self.state.npc_inventory.items()):
                if not isinstance(stock, dict): continue
                recipe = self.recipes.get(npc_id, {}) if isinstance(self.recipes, dict) else {}
                if not isinstance(recipe, dict): continue
                if not _within_work_hours(recipe.get("work_hours"), self.state.tick):
                    continue
                interval = max(1, _safe_int(recipe.get("interval", 5)))
                progress = _dict_at(self.state.events, "production_progress")
                progress[npc_id] = min(interval, _safe_int(progress.get(npc_id, 0)) + 1)
                if progress[npc_id] >= interval:
                    inputs = recipe.get("inputs", {})
                    outputs = recipe.get("outputs", {})
                    valid_recipe = (
                        isinstance(inputs, dict) and isinstance(outputs, dict) and inputs and outputs
                        and all(_safe_int(v) > 0 for v in inputs.values())
                        and all(_safe_int(v) > 0 for v in outputs.values())
                    )
                    has_inputs = valid_recipe and all(
                        _safe_int(stock.get(k, 0)) >= _safe_int(v) for k, v in inputs.items()
                    )
                    # 配方产出有库存上限；市场供给随真实生产增加。
                    caps = recipe.get("output_capacity", {}) if isinstance(recipe.get("output_capacity", {}), dict) else {}
                    can_produce = valid_recipe and all(
                        _safe_int(stock.get(k, 0)) + _safe_int(v) <= max(0, _safe_int(caps.get(k, 999999)))
                        for k, v in outputs.items()
                    )
                    if has_inputs and can_produce:
                        production_room = str(recipe.get("room_id", ""))
                        for k, v in inputs.items():
                            amount = _safe_int(v)
                            stock[k] = _safe_int(stock.get(k, 0)) - amount
                            market_input = self.state.market.setdefault(k, {"traded": 0, "last_price": 5, "supply": 20})
                            market_input["supply"] = max(0, _safe_int(market_input.get("supply", 20)) - amount)
                            _adjust_regional_market_supply(self.state, self.world_rooms, production_room, k, -amount)
                        for k, v in outputs.items():
                            amount = _safe_int(v)
                            stock[k] = _safe_int(stock.get(k, 0)) + amount
                            configured_prices = recipe.get("trade_prices", {}) if isinstance(recipe.get("trade_prices", {}), dict) else {}
                            default_price = 30 if k == "铁剑" else (150 if k == "精铁剑" else 5)
                            output_price = max(1, _safe_int(configured_prices.get(k, default_price), default_price))
                            row = self.state.market.setdefault(k, {"traded": 0, "last_price": output_price, "supply": 20})
                            row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20)) + amount))
                            row["last_price"] = output_price
                            _adjust_regional_market_supply(self.state, self.world_rooms, production_room, k, amount)
                        for output_item, output_amount in outputs.items():
                            _record_world_activity(self.state, "制作", npc_id, "制作", output_item,
                                                   output_amount, str(recipe.get("room_id", "")), "按配方消耗原料制成")
                        # 只有真正完成一轮制作才清零进度。缺料或成品库存满时保留“已备妥”状态，
                        # 条件恢复后即可制作，避免因等待交易腾出空间而额外空等完整周期。
                        progress[npc_id] = 0
            # 商队按配置路线循环移动；交易仅在库存/资金条件满足时发生。
            for cid, cfg in (self.caravan_config.items() if isinstance(self.caravan_config, dict) else []):
                if not isinstance(cfg, dict): continue
                route = cfg.get("route", [])
                if len(route) < 2: continue
                if cid not in self.state.caravans:
                    initial_caravan_gold = max(0, _safe_int(cfg.get("gold", 500)))
                    self.state.caravans[cid] = {"position": 0, "gold": initial_caravan_gold, "inventory": dict(cfg.get("inventory", {})), "capacity": max(0, _safe_int(cfg.get("capacity", 8), 8)), "visits": 0}
                    ledger = _dict_at(self.state.events, "economy_money_ledger")
                    ledger["seeded_caravan_gold"] = min(2_000_000_000, _safe_int(ledger.get("seeded_caravan_gold", 0)) + initial_caravan_gold)
                caravan = self.state.caravans[cid]
                if not isinstance(caravan, dict):
                    caravan = {"position": 0, "gold": _safe_int(cfg.get("gold", 500)), "inventory": {}, "capacity": max(0, _safe_int(cfg.get("capacity", 8), 8)), "visits": 0}
                    self.state.caravans[cid] = caravan
                idx = _safe_int(caravan.get("position", 0)) % len(route)
                next_idx = (idx + 1) % len(route)
                next_stop = str(route[next_idx])
                room_info = self.world_rooms.get(next_stop, {}) if isinstance(self.world_rooms, dict) else {}
                next_zone = str(room_info.get("zone", "")) if isinstance(room_info, dict) else ""
                crisis_map = self.state.events.get("world_crises", {}) if isinstance(self.state.events, dict) else {}
                crisis = crisis_map.get(next_zone, {}) if isinstance(crisis_map, dict) else {}
                travel_penalty = max(0, min(100, _safe_int(crisis.get("travel_penalty", 0)))) if isinstance(crisis, dict) else 0
                # Alpha106：真实配置中的 travel_interval 是行程间隔，不再只作为未使用的配置项。
                # 旧测试/旧配置没有该字段时仍按每 Tick 行进，兼容既有存档和自定义路线。
                travel_interval = max(1, _safe_int(cfg.get("travel_interval", 1), 1))
                if "travel_progress" not in caravan:
                    # 首次载入沿用旧路线语义：本 Tick 先抵达路线的下一站，之后才按间隔等待。
                    caravan["travel_progress"] = travel_interval - 1
                travel_progress = max(0, _safe_int(caravan.get("travel_progress", 0))) + 1
                should_attempt_move = travel_progress >= travel_interval
                if should_attempt_move:
                    travel_progress = 0
                caravan["travel_progress"] = travel_progress
                # 危机只会延误本来就该发生的移动；等待行程间隔时仍在当前站点交易。
                delayed = should_attempt_move and travel_penalty >= 10 and (self.state.tick + len(str(cid))) % 2 == 0
                if delayed:
                    caravan["crisis_delayed_ticks"] = min(2_000_000_000, _safe_int(caravan.get("crisis_delayed_ticks", 0)) + 1)
                    announce_key = f"{crisis.get('id', next_zone)}:{cid}"
                    announced = _dict_at(self.state.events, "caravan_crisis_delay_announced")
                    if not announced.get(announce_key):
                        announced[announce_key] = self.state.tick
                        pending = self.state.events.get("pending_world_announcements")
                        if not isinstance(pending, list):
                            pending = []
                            self.state.events["pending_world_announcements"] = pending
                        title = str(crisis.get("title", "当地局势动荡"))[:40]
                        pending.append(f"【商路受阻】{cid}受{title}影响，行程暂时延误。")
                        if len(pending) > 100:
                            del pending[:-100]
                elif should_attempt_move:
                    caravan["position"] = next_idx
                caravan["position"] = _safe_int(caravan.get("position", 0)) % len(route)
                # visits 保持旧版“经过世界 Tick 数”的统计口径；贸易与采集只在首次停靠或实际抵达新站时执行一次。
                caravan["visits"] = min(2_000_000_000, _safe_int(caravan.get("visits", 0)) + 1)
                process_stop = _safe_int(caravan.get("visits", 0)) == 1 or (should_attempt_move and not delayed)
                stop = str(route[caravan["position"]])
                # Alpha101：广场公开出现由错峰日程统一登记，不再因路线经过广场重复公告。
                inventory = caravan.get("inventory")
                if not isinstance(inventory, dict):
                    inventory = {}
                    caravan["inventory"] = inventory
                caravan["gold"] = min(2_000_000_000, max(0, _safe_int(caravan.get("gold", cfg.get("gold", 500)))))
                caravan["capacity"] = max(0, min(9999, _safe_int(cfg.get("capacity", caravan.get("capacity", 8)), 8)))
                # 读档或手工修改后，先把货舱恢复到合法状态。保留原有货物顺序，
                # 只留下货舱容量允许的数量；后续采购和出售均基于这个真实余量。
                normalized_inventory = {}
                cargo_left = caravan["capacity"]
                for item_name, amount in inventory.items():
                    amount = min(9999, max(0, _safe_int(amount, 0)))
                    kept = min(amount, cargo_left)
                    if kept > 0:
                        normalized_inventory[str(item_name)] = kept
                        cargo_left -= kept
                    if cargo_left <= 0:
                        break
                inventory.clear()
                inventory.update(normalized_inventory)
                caravan["position"] = _safe_int(caravan.get("position", 0)) % len(route)
                caravan["visits"] = min(2_000_000_000, max(0, _safe_int(caravan.get("visits", 0))))
                # Alpha107：商队每次实际停靠承担一次口粮、马匹与沿途打点费用；费用从商队资金中扣除并退出经济池。
                # 等待 Tick 不重复收费，旧配置未设置费用时保持原行为。
                upkeep = max(0, min(10000, _safe_int(cfg.get("operating_cost_per_stop", 0))))
                if process_stop and upkeep:
                    paid_upkeep = min(upkeep, max(0, _safe_int(caravan.get("gold", 0))))
                    if paid_upkeep:
                        caravan["gold"] = max(0, _safe_int(caravan.get("gold", 0)) - paid_upkeep)
                        ledger = _dict_at(self.state.events, "economy_money_ledger")
                        ledger["destroyed_caravan_upkeep"] = min(2_000_000_000, _safe_int(ledger.get("destroyed_caravan_upkeep", 0)) + paid_upkeep)
                        _record_world_activity(self.state, "开支", cid, "支付行商开销", "银两", paid_upkeep, stop,
                                               "口粮、马匹与沿途打点；银两退出流通")
                # 采集点：商队只能取走当前资源储量，不会生成无限材料。
                if process_stop and stop in self.resources:
                    resource_cfg = self.resources[stop]
                    resource_row = self.state.resources.setdefault(stop, {"remaining": _safe_int(resource_cfg.get("capacity", 20)), "last_tick": self.state.tick})
                    remaining = max(0, _safe_int(resource_row.get("remaining", 0)))
                    # 商队采集也遵守总载货容量；满载时不继续取走世界资源。
                    cargo_capacity = max(0, _safe_int(cfg.get("capacity", 8), 8))
                    cargo_used = sum(max(0, _safe_int(v)) for v in inventory.values())
                    free_capacity = max(0, cargo_capacity - cargo_used)
                    gathered = min(2, remaining, free_capacity)
                    if gathered:
                        resource_row["remaining"] = remaining - gathered
                        item = str(resource_cfg.get("item", "铁矿石"))
                        inventory[item] = max(0, _safe_int(inventory.get(item, 0))) + gathered
                # 商队在实际采集地点采购配置中的采集 NPC 库存，避免使用不存在的虚构 NPC 名称。
                for npc_id, gather_cfg in (self.gatherers.items() if process_stop and isinstance(self.gatherers, dict) else []):
                    if not isinstance(gather_cfg, dict) or str(gather_cfg.get("room_id", "")) != stop:
                        continue
                    item = str(gather_cfg.get("item", "草药"))
                    stock = self.state.npc_inventory.get(npc_id, {})
                    if not isinstance(stock, dict):
                        continue
                    available = max(0, _safe_int(stock.get(item, 0)))
                    buy_prices = cfg.get("buy_prices", {}) if isinstance(cfg.get("buy_prices", {}), dict) else {}
                    unit_price = max(1, min(1_000_000, _safe_int(buy_prices.get(item, 5), 5)))
                    affordable = max(0, _safe_int(caravan.get("gold", 0)) // unit_price)
                    capacity = max(0, max(0, _safe_int(cfg.get("capacity", 8), 8)) - sum(max(0, _safe_int(v)) for v in inventory.values()))
                    npc_gold = self.state.npc_gold
                    supplier_wallet = min(2_000_000_000, max(0, _safe_int(npc_gold.get(npc_id, 0), 0)))
                    supplier_room = max(0, (2_000_000_000 - supplier_wallet) // unit_price)
                    bought = min(available, affordable, capacity, supplier_room, 4)
                    if bought:
                        payment = bought * unit_price
                        stock[item] = available - bought
                        inventory[item] = max(0, _safe_int(inventory.get(item, 0))) + bought
                        caravan["gold"] = _safe_int(caravan.get("gold", 0)) - payment
                        npc_gold[npc_id] = supplier_wallet + payment
                        row = self.state.market.setdefault(item, {"traded": 0, "last_price": unit_price, "supply": 20})
                        row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))) + bought)
                        row["last_price"] = unit_price
                        row["supply"] = max(0, _safe_int(row.get("supply", 20)) - bought)
                        _record_regional_market_trade(self.state, self.world_rooms, stop, item, bought, -bought, unit_price)
                        _record_world_activity(self.state, "交易", cid, "向采集者采购", item, bought,
                                               stop, f"向{npc_id}采购，单价{unit_price}文")
                # 铁铺站：先把原料交给铁匠库存，再采购已经实际制作出的成品。
                if process_stop and stop in ("blacksmith", "guiyun_forge"):
                    npc_ids = ("铁匠", "百炼铁铺铁匠")
                    raw = max(0, _safe_int(inventory.get("铁矿石", 0)))
                    if raw:
                        npc_id = next((n for n in npc_ids if n in self.recipes), npc_ids[0])
                        stock = self.state.npc_inventory.setdefault(npc_id, {})
                        npc_gold = self.state.npc_gold
                        # 原料交付按双方真实资金结算；资金不足时只交付可支付的部分。
                        npc_wallet = max(0, _safe_int(npc_gold.get(npc_id, 0)))
                        caravan_wallet = max(0, _safe_int(caravan.get("gold", 0)))
                        npc_stock_room = max(0, 9999 - max(0, _safe_int(stock.get("铁矿石", 0))))
                        # 商队把矿石卖给铁匠：只能由买方铁匠付款，不能同时扣除卖方商队的钱。
                        # 同时保留资金上限，避免异常旧存档使商队钱包溢出。
                        caravan_wallet_room = max(0, (2_000_000_000 - caravan_wallet) // 2)
                        delivered = min(raw, npc_wallet // 2, npc_stock_room, caravan_wallet_room)
                        payment = delivered * 2
                        if delivered:
                            stock["铁矿石"] = max(0, _safe_int(stock.get("铁矿石", 0))) + delivered
                            inventory["铁矿石"] = raw - delivered
                            caravan["gold"] = min(2_000_000_000, caravan_wallet + payment)
                            npc_gold[npc_id] = npc_wallet - payment
                            row = self.state.market.setdefault("铁矿石", {"traded": 0, "last_price": 2, "supply": 20})
                            row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))) + delivered)
                            row["last_price"] = 2
                            row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20))) + delivered)
                            _record_regional_market_trade(self.state, self.world_rooms, stop, "铁矿石", delivered, delivered, 2)
                            _record_world_activity(self.state, "交易", cid, "交付矿石", "铁矿石", delivered,
                                                   stop, f"交给{npc_id}")
                    for npc_id in npc_ids:
                        stock = self.state.npc_inventory.get(npc_id, {})
                        if not isinstance(stock, dict):
                            continue
                        available = max(0, _safe_int(stock.get("铁剑", 0)))
                        buy_prices = cfg.get("buy_prices", {}) if isinstance(cfg.get("buy_prices", {}), dict) else {}
                        unit_price = max(1, min(1_000_000, _safe_int(buy_prices.get("铁剑", 30), 30)))
                        affordable = max(0, _safe_int(caravan.get("gold", 0)) // unit_price)
                        npc_wallet = min(2_000_000_000, max(0, _safe_int(self.state.npc_gold.get(npc_id, 0), 0)))
                        npc_wallet_room = max(0, (2_000_000_000 - npc_wallet) // unit_price)
                        affordable = min(affordable, npc_wallet_room)
                        cargo_capacity = max(0, _safe_int(cfg.get("capacity", 8), 8))
                        cargo_used = sum(max(0, _safe_int(v)) for v in inventory.values())
                        free_capacity = max(0, cargo_capacity - cargo_used)
                        bought = min(available, affordable, free_capacity, 3)
                        if bought:
                            payment = bought * unit_price
                            stock["铁剑"] = available - bought
                            inventory["铁剑"] = max(0, _safe_int(inventory.get("铁剑", 0))) + bought
                            caravan["gold"] = _safe_int(caravan.get("gold", 0)) - payment
                            npc_gold = self.state.npc_gold
                            npc_gold[npc_id] = max(0, _safe_int(npc_gold.get(npc_id, 0))) + payment
                            row = self.state.market.setdefault("铁剑", {"traded": 0, "last_price": unit_price, "supply": 20})
                            row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))) + bought)
                            row["last_price"] = unit_price
                            row["supply"] = max(0, _safe_int(row.get("supply", 20)) - bought)
                            _record_regional_market_trade(self.state, self.world_rooms, stop, "铁剑", bought, -bought, unit_price)
                            _record_world_activity(self.state, "交易", cid, "采购成品", "铁剑", bought,
                                                   stop, f"向{npc_id}采购，单价{unit_price}文")
                        if bought:
                            break
                # 配方产出可以由经过对应作坊的商队采购；商品必须来自真实生产库存。
                for npc_id, recipe in (self.recipes.items() if process_stop and isinstance(self.recipes, dict) else []):
                    if not isinstance(recipe, dict) or str(recipe.get("room_id", "")) != stop:
                        continue
                    stock = self.state.npc_inventory.get(npc_id, {})
                    if not isinstance(stock, dict):
                        continue
                    trade_prices = recipe.get("trade_prices", {}) if isinstance(recipe.get("trade_prices", {}), dict) else {}
                    buy_prices = cfg.get("buy_prices", {}) if isinstance(cfg.get("buy_prices", {}), dict) else {}
                    for item in (recipe.get("outputs", {}) if isinstance(recipe.get("outputs", {}), dict) else {}):
                        available = max(0, _safe_int(stock.get(item, 0)))
                        # 商队自身的采购价优先；未配置时沿用作坊交易价，保证旧配置兼容。
                        unit_price = max(1, min(1_000_000, _safe_int(buy_prices.get(item, trade_prices.get(item, 5)), 5)))
                        cargo_capacity = max(0, _safe_int(cfg.get("capacity", 8), 8))
                        cargo_used = sum(max(0, _safe_int(v)) for v in inventory.values())
                        free_capacity = max(0, cargo_capacity - cargo_used)
                        affordable = max(0, _safe_int(caravan.get("gold", 0)) // unit_price)
                        npc_wallet = min(2_000_000_000, max(0, _safe_int(self.state.npc_gold.get(npc_id, 0), 0)))
                        npc_wallet_room = max(0, (2_000_000_000 - npc_wallet) // unit_price)
                        bought = min(available, affordable, free_capacity, npc_wallet_room, 3)
                        if not bought:
                            continue
                        stock[item] = available - bought
                        inventory[item] = max(0, _safe_int(inventory.get(item, 0))) + bought
                        payment = bought * unit_price
                        caravan["gold"] = max(0, _safe_int(caravan.get("gold", 0))) - payment
                        npc_wallets = self.state.npc_gold
                        npc_wallets[npc_id] = min(2_000_000_000, max(0, _safe_int(npc_wallets.get(npc_id, 0))) + payment)
                        market_row = self.state.market.setdefault(item, {"traded": 0, "last_price": unit_price, "supply": 20})
                        market_row["traded"] = min(2_000_000_000, max(0, _safe_int(market_row.get("traded", 0))) + bought)
                        market_row["last_price"] = unit_price
                        market_row["supply"] = max(0, _safe_int(market_row.get("supply", 20)) - bought)
                        _record_regional_market_trade(self.state, self.world_rooms, stop, item, bought, -bought, unit_price)
                        _record_world_activity(self.state, "交易", cid, "采购成品", item, bought,
                                               stop, f"向{npc_id}采购")
                # 城镇销售：从城镇资金池付款；资金不足时只出售可支付数量，余货保留。
                if process_stop and stop in ("guiyun_south_gate", "guiyun_south_main_street"):
                    town_gold = max(0, _safe_int(self.state.town_gold))
                    for item, amount in list(inventory.items()):
                        amount = max(0, _safe_int(amount))
                        if amount <= 0:
                            continue
                        sale_prices = cfg.get("sale_prices", {}) if isinstance(cfg.get("sale_prices", {}), dict) else {}
                        unit_price = max(1, _safe_int(sale_prices.get(item, 45 if item == "铁剑" else 8), 8))
                        caravan_wallet = min(2_000_000_000, max(0, _safe_int(caravan.get("gold", 0))))
                        caravan_wallet_room = max(0, (2_000_000_000 - caravan_wallet) // unit_price) if unit_price > 0 else 0
                        sold = min(amount, town_gold // unit_price, caravan_wallet_room) if unit_price > 0 else 0
                        if sold <= 0:
                            continue
                        payment = sold * unit_price
                        caravan["gold"] = max(0, _safe_int(caravan.get("gold", 0))) + payment
                        town_gold -= payment
                        row = self.state.market.setdefault(item, {"traded": 0, "last_price": unit_price, "supply": 20})
                        row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))) + sold)
                        row["last_price"] = unit_price
                        row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20))) + sold)
                        _record_regional_market_trade(self.state, self.world_rooms, stop, item, sold, sold, unit_price)
                        inventory[item] = amount - sold
                        _record_world_activity(self.state, "交易", cid, "售予城镇", item, sold,
                                               stop, f"成交单价{unit_price}文")
                    self.state.town_gold = town_gold
                if not any(isinstance(c, dict) and c.get("tier") for c in self.caravan_config.values()):
                    # 广场到场按独立日程推进，不改变原有商队贸易路线与资源交割节奏。
                    appearances = cfg.get("appearances", []) if isinstance(cfg.get("appearances", []), list) else []
                    appearance_progress = _dict_at(self.state.events, "caravan_appearance_progress")
                    for appearance in appearances:
                        if not isinstance(appearance, dict):
                            continue
                        room_id = str(appearance.get("room", ""))
                        if room_id not in ("village_square", "guiyun_central_square"):
                            continue
                        interval = max(1, _safe_int(appearance.get("interval", 6), 6))
                        # 商路指标影响对应地区商队到场频率；旧存档没有生态快照时沿用原间隔。
                        ecology_map = self.state.events.get("region_ecology", {}) if isinstance(self.state.events, dict) else {}
                        room_info = self.world_rooms.get(room_id, {}) if isinstance(self.world_rooms, dict) else {}
                        zone = room_info.get("zone", "") if isinstance(room_info, dict) else ""
                        ecology = ecology_map.get(zone, {}) if isinstance(ecology_map, dict) else {}
                        if isinstance(ecology, dict) and "commerce" in ecology:
                            commerce = max(0, min(100, _safe_int(ecology.get("commerce", 70), 70)))
                            interval = max(1, int(round(interval * (1.5 - commerce / 100.0))))
                        # 商队在受危机影响的地区出现频率也会下降，与沿线行程延误保持一致。
                        crisis_map = self.state.events.get("world_crises", {}) if isinstance(self.state.events, dict) else {}
                        crisis = crisis_map.get(str(zone), {}) if isinstance(crisis_map, dict) else {}
                        if isinstance(crisis, dict):
                            penalty = max(0, min(100, _safe_int(crisis.get("travel_penalty", 0))))
                            if penalty >= 10:
                                interval = max(interval, int(round(interval * (1.0 + min(0.75, penalty / 40.0)))) )
                        progress_key = f"{cid}:{room_id}"
                        # 每支商队有独立的初始错峰值；兼容旧存档中不存在该进度的情况。
                        if progress_key not in appearance_progress:
                            # offset 表示首次到场前的延迟 Tick；后续按 interval 周期到场。
                            initial_delay = max(1, min(interval, _safe_int(appearance.get("offset", interval), interval)))
                            appearance_progress[progress_key] = interval - initial_delay
                        progress = _safe_int(appearance_progress.get(progress_key, 0)) + 1
                        if progress < interval:
                            appearance_progress[progress_key] = progress
                            continue
                        appearance_progress[progress_key] = 0
                        # 到场状态与公告统一登记，避免路线停靠和日程同时触发双份公告。
                        _register_caravan_arrival(self.state, cid, room_id)

            # Alpha102：真实配置统一使用全局商旅调度，两个广场共享间隔，避免各自独立刷新造成连续到场。
            tier_configs = [(str(name), cfg) for name, cfg in self.caravan_config.items()
                            if isinstance(cfg, dict) and cfg.get("tier") and isinstance(cfg.get("route"), list)]
            if tier_configs:
                events = _dict_at(self.state.__dict__, "events")
                schedule = _dict_at(events, "caravan_global_schedule")
                active = _dict_at(events, "active_caravans")
                # 同一时刻只允许一支公开商队停靠；过期记录由本 Tick 前段清理。
                active_public = [row for row in active.values() if isinstance(row, dict)
                                 and row.get("room") in ("village_square", "guiyun_central_square")
                                 and _safe_int(row.get("until_tick", -1), -1) > self.state.tick]
                if not active_public:
                    next_tick = _safe_int(schedule.get("next_tick", -1), -1)
                    if next_tick < 0:
                        # 旧存档首次启用新调度时先留出安静期，不在载入后立即刷出商队。
                        schedule["next_tick"] = self.state.tick + 12
                    elif self.state.tick >= next_tick:
                        seed = self.state.tick * 1103515245 + _safe_int(schedule.get("arrivals", 0)) * 12345 + 97
                        rng = random.Random(seed)
                        total_weight = sum(max(1, _safe_int(cfg.get("weight", 1), 1)) for _, cfg in tier_configs)
                        pick = rng.randrange(max(1, total_weight))
                        chosen_name, chosen_cfg = tier_configs[-1]
                        for name, cfg in tier_configs:
                            pick -= max(1, _safe_int(cfg.get("weight", 1), 1))
                            if pick < 0:
                                chosen_name, chosen_cfg = name, cfg
                                break
                        locations = [str(row.get("room", "")) for row in chosen_cfg.get("appearances", [])
                                     if isinstance(row, dict) and row.get("room") in ("village_square", "guiyun_central_square")]
                        if not locations:
                            locations = ["village_square", "guiyun_central_square"]
                        last_room = str(schedule.get("last_room", ""))
                        available = [room for room in locations if room != last_room] or locations
                        room_id = available[rng.randrange(len(available))]
                        tier = str(chosen_cfg.get("tier", "small"))
                        stay_range = chosen_cfg.get("stay_ticks", [3, 5])
                        if not isinstance(stay_range, list) or len(stay_range) != 2:
                            stay_range = [3, 5]
                        stay_min = max(1, _safe_int(stay_range[0], 3))
                        stay_max = max(stay_min, _safe_int(stay_range[1], stay_min))
                        stay_ticks = rng.randint(stay_min, stay_max)
                        # 低商路通行度与危机只会推迟到场，不会令商队凭空增加。
                        room_info = self.world_rooms.get(room_id, {}) if isinstance(self.world_rooms, dict) else {}
                        zone = str(room_info.get("zone", "")) if isinstance(room_info, dict) else ""
                        ecology_map = events.get("region_ecology", {})
                        ecology = ecology_map.get(zone, {}) if isinstance(ecology_map, dict) else {}
                        delay = 0
                        if isinstance(ecology, dict):
                            commerce = max(0, min(100, _safe_int(ecology.get("commerce", 70), 70)))
                            delay += max(0, int(round((70 - commerce) / 20)))
                        crises = events.get("world_crises", {})
                        crisis = crises.get(zone, {}) if isinstance(crises, dict) else {}
                        if isinstance(crisis, dict):
                            penalty = max(0, min(100, _safe_int(crisis.get("travel_penalty", 0))))
                            delay += int(round(penalty / 25))
                        _register_caravan_arrival(self.state, chosen_name, room_id, stay_ticks=stay_ticks)
                        schedule["arrivals"] = min(2_000_000_000, _safe_int(schedule.get("arrivals", 0)) + 1)
                        schedule["last_room"] = room_id
                        schedule["last_caravan"] = chosen_name
                        interval_range = chosen_cfg.get("arrival_interval", [30, 45])
                        if not isinstance(interval_range, list) or len(interval_range) != 2:
                            interval_range = [30, 45]
                        interval_min = max(1, _safe_int(interval_range[0], 30))
                        interval_max = max(interval_min, _safe_int(interval_range[1], interval_min))
                        schedule["next_tick"] = self.state.tick + rng.randint(interval_min, interval_max) + delay
        if player_location is not None:
            self.state.events["last_player_location"] = str(player_location)
        return self.state
