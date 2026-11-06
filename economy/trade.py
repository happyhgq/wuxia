from time import time
import json
from functools import lru_cache
from pathlib import Path

from item_feedback import add_inventory_items, remove_inventory_items


GENERIC_TRADABLE_ITEMS = frozenset({"铁矿石", "草药", "雾露草", "木材", "铁剑", "药材", "布料", "兽皮"})


def _load_economy_config(filename):
    root = Path(__file__).resolve().parent.parent / "data" / "economy"
    try:
        with (root / filename).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


@lru_cache(maxsize=1)
def _simulated_items():
    """模拟层真实产出或采集的物品；只有这些货品必须来自实际库存。

    其他货架商品沿用旧式静态商店规则，避免经济 NPC 因未参与模拟而永久缺货。
    """
    items = {}
    for npc_id, cfg in _load_economy_config("gatherers.json").items():
        if isinstance(cfg, dict) and cfg.get("item"):
            items.setdefault(str(npc_id), set()).add(str(cfg["item"]))
    for npc_id, cfg in _load_economy_config("recipes.json").items():
        if not isinstance(cfg, dict):
            continue
        outputs = cfg.get("outputs", {})
        if isinstance(outputs, dict):
            for item in outputs:
                items.setdefault(str(npc_id), set()).add(str(item))
    return {npc_id: frozenset(names) for npc_id, names in items.items()}


@lru_cache(maxsize=1)
def _stockable_items():
    """NPC 愿意按真实库存收购的物品；静态商人沿用通用材料清单。"""
    stockable = {}
    gatherers = _load_economy_config("gatherers.json")
    recipes = _load_economy_config("recipes.json")
    for npc_id, cfg in gatherers.items():
        if isinstance(cfg, dict) and cfg.get("item"):
            stockable.setdefault(str(npc_id), set()).add(str(cfg["item"]))
    for npc_id, cfg in recipes.items():
        if not isinstance(cfg, dict):
            continue
        for field in ("inputs", "outputs"):
            rows = cfg.get(field, {})
            if isinstance(rows, dict):
                stockable.setdefault(str(npc_id), set()).update(str(item) for item in rows)
    return {npc_id: frozenset(names) for npc_id, names in stockable.items()}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


@lru_cache(maxsize=1)
def _npc_item_capacities():
    """读取经济 NPC 的真实库存上限；未配置的旧式 NPC 保持通用上限。"""
    root = Path(__file__).resolve().parent.parent / "data" / "economy"
    limits = {}
    try:
        with (root / "gatherers.json").open("r", encoding="utf-8") as stream:
            gatherers = json.load(stream)
        if isinstance(gatherers, dict):
            for npc_id, cfg in gatherers.items():
                if isinstance(cfg, dict):
                    item = str(cfg.get("item", "草药"))
                    limits[(str(npc_id), item)] = max(0, min(9999, _safe_int(cfg.get("capacity", 12))))
    except (OSError, ValueError, TypeError):
        pass
    try:
        with (root / "recipes.json").open("r", encoding="utf-8") as stream:
            recipes = json.load(stream)
        if isinstance(recipes, dict):
            for npc_id, cfg in recipes.items():
                if not isinstance(cfg, dict):
                    continue
                caps = cfg.get("output_capacity", {})
                if isinstance(caps, dict):
                    for item, cap in caps.items():
                        limits[(str(npc_id), str(item))] = max(0, min(9999, _safe_int(cap)))
                routes = cfg.get("supplier_routes", [])
                if isinstance(routes, list):
                    for route in routes:
                        if isinstance(route, dict) and route.get("item") and "max_stock" in route:
                            limits[(str(npc_id), str(route["item"]))] = max(0, min(9999, _safe_int(route.get("max_stock"))))
    except (OSError, ValueError, TypeError):
        pass
    return limits


class TradeService:
    """统一、可测试的交易基础服务。物品仍以游戏现有中文名称作为库存键。"""
    DEFAULT_INVENTORY_CAPACITY = 100
    MAX_WALLET = 2_000_000_000

    @classmethod
    def _player_wallet(cls, player):
        """读取合法玩家银两；交易不能把异常存档金额带入结算。"""
        value = _safe_int(getattr(player, "gold", -1), -1)
        if value < 0 or value > cls.MAX_WALLET:
            return None
        return value

    @classmethod
    def inventory_slots_free(cls, player):
        """返回玩家可容纳的物品格数；旧角色没有容量字段时采用安全默认值。"""
        inventory = getattr(player, "inventory", None)
        if not isinstance(inventory, list):
            return 0
        try:
            capacity = int(getattr(player, "inventory_capacity", cls.DEFAULT_INVENTORY_CAPACITY))
        except (TypeError, ValueError, OverflowError):
            capacity = cls.DEFAULT_INVENTORY_CAPACITY
        return max(0, capacity - len(inventory))

    @classmethod
    def _player_inventory(cls, player):
        """交易前验证玩家背包结构；损坏存档应得到提示，而不是抛出异常。"""
        inventory = getattr(player, "inventory", None)
        return inventory if isinstance(inventory, list) else None

    @classmethod
    def can_receive_items(cls, player, quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError, OverflowError):
            return False
        return cls._player_inventory(player) is not None and quantity >= 0 and cls.inventory_slots_free(player) >= quantity

    @staticmethod
    def simulated_items(counterparty):
        """该商家由经济模拟真实供货的物品；未列出的货架商品属于常备货。"""
        return _simulated_items().get(str(counterparty), frozenset())

    @classmethod
    def sells_from_real_stock(cls, counterparty, item):
        return str(item) in cls.simulated_items(counterparty)

    @staticmethod
    def stockable_items(counterparty):
        """该商家会实际入库的物品；静态商家沿用通用材料清单。"""
        return _stockable_items().get(str(counterparty), GENERIC_TRADABLE_ITEMS)

    @classmethod
    def merchant_wallet(cls, player, counterparty):
        """只读估算商家现银，不初始化钱包；异常或缺失状态返回安全默认值。"""
        state = getattr(player, "economy_state", None)
        if not isinstance(state, dict):
            return 1000
        wallets = state.get("npc_gold", {})
        if isinstance(wallets, dict) and str(counterparty) in wallets:
            return _safe_int(wallets.get(str(counterparty)), -1)
        events = state.get("events", {})
        seeded = events.get("counterparty_wallet_bootstrap", {}) if isinstance(events, dict) else {}
        if isinstance(seeded, dict) and seeded.get(str(counterparty)):
            return 0
        return 1000
    @staticmethod
    def price(base_price, region=1.0, event=1.0, scarcity=0.0):
        try:
            base = max(0, int(base_price))
            multiplier = max(0.1, float(region)) * max(0.1, float(event)) * max(0.1, 1 + float(scarcity))
            return max(0, int(round(base * multiplier)))
        except (TypeError, ValueError, OverflowError):
            return 0

    @classmethod
    def calculate_price(cls, base_price, region=1.0, event=1.0, scarcity=0.0):
        return cls.price(base_price, region, event, scarcity)

    @staticmethod
    def _player_region(player):
        """从当前房间读取区域标识；旧角色或测试角色无法定位时使用全局市场。"""
        room_id = str(getattr(player, "location", "") or "")
        if not room_id:
            return ""
        try:
            import engine
            room = engine.ROOMS.get(room_id, {})
            if isinstance(room, dict):
                return str(room.get("zone", "") or "")
        except Exception:
            pass
        return ""

    @classmethod
    def market_price(cls, player, item, base_price, side, merchant_rate=1.0, event_rate=1.0):
        """报价优先使用当前区域供需；旧存档或未形成区域行情时回退全局市场。"""
        state = getattr(player, "economy_state", None)
        market = state.get("market", {}) if isinstance(state, dict) else {}
        row = market.get(str(item), {}) if isinstance(market, dict) else {}
        region = cls._player_region(player)
        regional = state.get("regional_market", {}) if isinstance(state, dict) else {}
        regional_rows = regional.get(region, {}) if region and isinstance(regional, dict) else {}
        regional_row = regional_rows.get(str(item)) if isinstance(regional_rows, dict) else None
        if isinstance(regional_row, dict):
            row = regional_row
        try:
            supply = max(0, int(row.get("supply", 20))) if isinstance(row, dict) else 20
        except (TypeError, ValueError, OverflowError):
            supply = 20
        # 买入价与回收价分别响应供需：供给稀缺时售价上升，供给充裕时回收价下降。
        normalized_side = str(side).strip().lower()
        if normalized_side not in ("buy", "sell"):
            normalized_side = "buy"
        divisor = 80.0 if normalized_side == "buy" else 60.0
        delta = max(-0.25, min(0.25, (20 - supply) / divisor))
        try:
            rate = max(0.0, float(merchant_rate))
        except (TypeError, ValueError, OverflowError):
            rate = 1.0
        try:
            event = max(0.5, min(2.0, float(event_rate)))
        except (TypeError, ValueError, OverflowError):
            event = 1.0
        # 地区行情事件只影响事件所在区域，不再把所有地区一并涨跌。
        if region and isinstance(state, dict):
            events = state.get("events", {})
            local_events = events.get("regional_market_events", {}) if isinstance(events, dict) else {}
            local_event = local_events.get(region) if isinstance(local_events, dict) else None
            if isinstance(local_event, dict):
                try:
                    until_tick = int(local_event.get("until_tick", -1))
                    clock = int(events.get("tick", state.get("tick", 0))) if isinstance(events, dict) else int(state.get("tick", 0))
                    local_rate = float(local_event.get("rate", 1.0))
                    if clock < until_tick:
                        event = max(0.5, min(2.0, event * local_rate))
                except (TypeError, ValueError, OverflowError):
                    pass
        try:
            valid_base = int(base_price or 0)
        except (TypeError, ValueError, OverflowError):
            return 0
        # Alpha82：商路繁荣度真实影响本地交易价格。以70为中性点，低商路略涨价，
        # 高商路因供货便利略降价；影响幅度封顶±15%，不覆盖已有供需和事件修正。
        commerce_rate = 1.0
        if region and hasattr(player, "get_region_ecology"):
            try:
                ecology = player.get_region_ecology(region)
                commerce = max(0, min(100, int(ecology.get("commerce", 70))))
                commerce_rate = max(0.85, min(1.15, 1.0 + (70 - commerce) * 0.0025))
            except (TypeError, ValueError, AttributeError, KeyError):
                commerce_rate = 1.0
        value = cls.price(valid_base, region=rate * commerce_rate, event=event, scarcity=delta)
        # 防止异常配置或损坏存档导致交易价格溢出。
        return min(1_000_000, max(1, value)) if valid_base > 0 else 0

    @staticmethod
    def _caravan_state(player, caravan_id):
        state = getattr(player, "economy_state", None)
        if not isinstance(state, dict):
            return None, None
        caravans = state.get("caravans")
        if not isinstance(caravans, dict):
            return None, None
        caravan = caravans.get(str(caravan_id))
        if not isinstance(caravan, dict):
            return None, None
        inventory = caravan.get("inventory")
        if not isinstance(inventory, dict):
            return None, None
        # 只读取并返回原始状态，不在交易校验阶段修复存档。否则一次因
        # 银两不足、库存不足等原因失败的交易，也会悄悄改写商队其他库存。
        # 具体交易通过全部校验后，再在提交阶段统一规范化库存与数值字段。
        return caravan, inventory

    @classmethod
    def buy_from_caravan(cls, player, caravan_id, item, quantity, unit_price):
        """玩家从当前商队购货；先完整校验资金、库存和载货空间，再一次性结算。"""
        try:
            quantity, unit_price = int(quantity), int(unit_price)
        except (TypeError, ValueError, OverflowError):
            return False, "交易数量或价格无效。"
        if quantity <= 0 or unit_price <= 0:
            return False, "交易数量或价格无效。"
        caravan, stock = cls._caravan_state(player, caravan_id)
        if caravan is None:
            return False, "商队货物状态异常，交易未执行。"
        available = _safe_int(stock.get(str(item), 0), -1)
        if available < 0:
            return False, f"商队的【{item}】货物状态异常，交易未执行。"
        if available < quantity:
            if available <= 0:
                return False, f"商队的【{item}】已经售罄，请等到下一批货。"
            return False, f"商队的【{item}】只剩 {available} 件，请减少数量。"
        player_wallet = cls._player_wallet(player)
        total = quantity * unit_price
        if player_wallet is None:
            return False, "你的银两数据异常，请先修复存档后再交易。"
        if player_wallet < total:
            return False, "银两不足，无法购买。"
        caravan_gold = min(cls.MAX_WALLET, max(0, _safe_int(caravan.get("gold", 0))))
        if caravan_gold > cls.MAX_WALLET - total:
            return False, f"{caravan_id}的银两已接近上限，暂时无法收款。"
        if not cls.can_receive_items(player, quantity):
            return False, "行囊已满，请先整理或出售一些物品。"
        # 从商队购买只会减少其货物，不会增加货舱占用；即使旧存档
        # 曾有超载状态，也应允许玩家买走货物来恢复正常，而不是锁死交易。
        # 所有前置条件通过后才提交规范化状态与双方资产变化。
        for item_name, amount in list(stock.items()):
            stock[item_name] = max(0, _safe_int(amount, 0))
        caravan["capacity"] = max(0, _safe_int(caravan.get("capacity", 8), 8))
        added, held = add_inventory_items(player, str(item), quantity, announce=False)
        if not added:
            return False, "行囊已满，请先整理或出售一些物品。"
        player.gold = player_wallet - total
        stock[str(item)] = max(0, _safe_int(stock.get(str(item), 0)) - quantity)
        caravan["gold"] = caravan_gold + total
        cls.record_trade(player, "buy", item, quantity, unit_price, str(caravan_id))
        return True, (f"从{caravan_id}购入【{item}】×{quantity}，花费 {quantity * unit_price} 两；"
                      f"行囊中现有【{item}】×{held}。")

    @classmethod
    def sell_to_caravan(cls, player, caravan_id, item, quantity, unit_price):
        """玩家向商队出售采集物或制作品；商队资金、货舱和库存上限均生效。"""
        try:
            quantity, unit_price = int(quantity), int(unit_price)
        except (TypeError, ValueError, OverflowError):
            return False, "交易数量或价格无效。"
        if quantity <= 0 or unit_price <= 0:
            return False, "交易数量或价格无效。"
        item = str(item)
        player_inventory = cls._player_inventory(player)
        if player_inventory is None:
            return False, "你的行囊数据异常，交易未执行；请先修复存档。"
        if player_inventory.count(item) < quantity:
            return False, f"你的【{item}】数量不足。"
        caravan, stock = cls._caravan_state(player, caravan_id)
        if caravan is None:
            return False, "商队货物状态异常，交易未执行。"
        player_wallet = cls._player_wallet(player)
        total = quantity * unit_price
        if player_wallet is None:
            return False, "你的银两数据异常，请先修复存档后再交易。"
        if player_wallet > cls.MAX_WALLET - total:
            return False, "交易后银两将超过携带上限，请先消费或存放部分银两。"
        caravan_gold = min(cls.MAX_WALLET, max(0, _safe_int(caravan.get("gold", 0))))
        caravan_capacity = max(0, _safe_int(caravan.get("capacity", 8), 8))
        if caravan_gold < total:
            return False, f"{caravan_id}银两不足，暂时买不起这么多。"
        cargo_used = sum(max(0, _safe_int(v)) for v in stock.values())
        if cargo_used + quantity > caravan_capacity:
            return False, f"{caravan_id}的货舱已满，无法收购这么多。"
        if max(0, _safe_int(stock.get(item, 0))) + quantity > 9999:
            return False, f"商队的【{item}】库存已满。"
        # 校验全部通过后才清洗旧存档中的异常库存值，避免失败交易产生副作用。
        for item_name, amount in list(stock.items()):
            stock[item_name] = max(0, _safe_int(amount, 0))
        caravan["capacity"] = caravan_capacity
        removed, remaining = remove_inventory_items(
            player, item, quantity, action="售出", announce=False
        )
        if not removed:
            return False, f"你的【{item}】数量不足，交易未执行。"
        player.gold = player_wallet + total
        stock[item] = max(0, _safe_int(stock.get(item, 0))) + quantity
        caravan["gold"] = caravan_gold - total
        cls.record_trade(player, "sell", item, quantity, unit_price, str(caravan_id))
        return True, (f"售出【{item}】×{quantity}给{caravan_id}，获得 {quantity * unit_price} 两；"
                      f"行囊中剩余【{item}】×{remaining}。")

    @staticmethod
    def record_trade(player, side, item, quantity, unit_price, counterparty="商家"):
        state = getattr(player, "economy_state", None)
        if not isinstance(state, dict):
            state = {}
            player.economy_state = state
        history = state.get("trade_history")
        if not isinstance(history, list):
            history = []
            state["trade_history"] = history
        world_state = getattr(player, "world_state", {})
        variables = world_state.get("variables", {}) if isinstance(world_state, dict) else {}
        tick = _safe_int(variables.get("quest_clock", 0)) if isinstance(variables, dict) else 0
        quantity = max(0, _safe_int(quantity))
        unit_price = max(0, _safe_int(unit_price))
        total = quantity * unit_price
        history.append({"tick": tick, "side": str(side), "item": str(item),
                        "quantity": quantity, "unit_price": unit_price,
                        "total": total, "counterparty": str(counterparty),
                        "timestamp": int(time())})
        del history[:-100]
        # Alpha109：把玩家交易记为资金/物品转移，而不是新增财富。
        # side=buy 表示玩家付款并取得物品；side=sell 则相反。
        events = state.get("events")
        if not isinstance(events, dict):
            events = {}
            state["events"] = events
        ledger = events.get("economic_flow_ledger")
        if not isinstance(ledger, dict):
            ledger = {}
            events["economic_flow_ledger"] = ledger
        counters = {
            "player_trade_gold_paid": total if str(side) == "buy" else 0,
            "player_trade_gold_received": total if str(side) == "sell" else 0,
            "player_trade_items_bought": quantity if str(side) == "buy" else 0,
            "player_trade_items_sold": quantity if str(side) == "sell" else 0,
            "player_trade_transactions": 1,
        }
        for key, amount in counters.items():
            ledger[key] = min(2_000_000_000, max(0, _safe_int(ledger.get(key, 0))) + amount)
        flow_rows = events.get("economic_flow_history")
        if not isinstance(flow_rows, list):
            flow_rows = []
            events["economic_flow_history"] = flow_rows
        flow_rows.append({"tick": max(0, tick), "source": "玩家交易", "direction": str(side),
                          "item": str(item)[:48], "quantity": quantity, "gold": total,
                          "counterparty": str(counterparty)[:48]})
        if len(flow_rows) > 100:
            del flow_rows[:-100]
        market = state.get("market")
        if not isinstance(market, dict):
            market = {}
            state["market"] = market
        row = market.get(str(item))
        if not isinstance(row, dict):
            row = {"traded": 0, "last_price": unit_price, "supply": 20}
            market[str(item)] = row
        row["traded"] = min(2_000_000_000, max(0, _safe_int(row.get("traded", 0))) + quantity)
        row["last_price"] = unit_price
        delta = quantity if side == "sell" else -quantity
        row["supply"] = min(9999, max(0, _safe_int(row.get("supply", 20)) + delta))
        # 同一物品在不同区域形成独立供需，避免村中大量交易直接改变归云城的行情。
        region = TradeService._player_region(player)
        if region:
            regional = state.get("regional_market")
            if not isinstance(regional, dict):
                regional = {}
                state["regional_market"] = regional
            regional_rows = regional.get(region)
            if not isinstance(regional_rows, dict):
                regional_rows = {}
                regional[region] = regional_rows
            regional_row = regional_rows.get(str(item))
            if not isinstance(regional_row, dict):
                # 每个区域的行情必须从自己的中性基准开始，不能继承全局市场
                # 已被其他地区交易推高/压低的供给量；本次交易的 delta 在下方只应用一次。
                regional_row = {"traded": 0, "last_price": unit_price, "supply": 20}
                regional_rows[str(item)] = regional_row
            regional_row["traded"] = min(2_000_000_000, max(0, _safe_int(regional_row.get("traded", 0))) + quantity)
            regional_row["last_price"] = unit_price
            regional_row["supply"] = min(9999, max(0, _safe_int(regional_row.get("supply", 20)) + delta))

    @staticmethod
    def _economy(player):
        state = getattr(player, "economy_state", None)
        if not isinstance(state, dict):
            state = {}; player.economy_state = state
        for field in ("npc_inventory", "npc_gold", "market"):
            if not isinstance(state.get(field), dict):
                state[field] = {}
        if not isinstance(state.get("trade_history"), list):
            state["trade_history"] = []
        return state

    @staticmethod
    def _counterparty_wallet(state, counterparty):
        """对旧式静态商店做一次性起始资金初始化；已初始化过的钱包被清空也不会重新发钱。"""
        wallets = state.setdefault("npc_gold", {})
        if not isinstance(wallets, dict):
            wallets = {}
            state["npc_gold"] = wallets
        name = str(counterparty)
        if name in wallets:
            return _safe_int(wallets.get(name), 1000)
        events = state.setdefault("events", {})
        if not isinstance(events, dict):
            events = {}
            state["events"] = events
        seeded = events.setdefault("counterparty_wallet_bootstrap", {})
        if not isinstance(seeded, dict):
            seeded = {}
            events["counterparty_wallet_bootstrap"] = seeded
        if seeded.get(name):
            wallets[name] = 0
            return 0
        wallets[name] = 1000
        seeded[name] = True
        ledger = events.setdefault("economy_money_ledger", {})
        if isinstance(ledger, dict):
            ledger["seeded_trade_counterparty_gold"] = min(
                2_000_000_000,
                _safe_int(ledger.get("seeded_trade_counterparty_gold", 0)) + 1000,
            )
        return 1000

    @classmethod
    def buy(cls, player, item, quantity, unit_price, counterparty="商家"):
        try:
            quantity = int(quantity); unit_price = int(unit_price)
        except (TypeError, ValueError, OverflowError):
            return False, "交易数量或价格无效。"
        if quantity <= 0 or unit_price <= 0:
            return False, "交易数量或价格无效。"
        total = quantity * unit_price
        player_wallet = cls._player_wallet(player)
        if player_wallet is None:
            return False, "你的银两数据异常，请先修复存档后再交易。"
        if player_wallet < total:
            return False, "银两不足或交易数量无效。"
        if not cls.can_receive_items(player, quantity):
            return False, "行囊已满，请先整理或出售一些物品。"
        state = getattr(player, "economy_state", {})
        if not isinstance(state, dict):
            state = {}
        npc_inventory = state.get("npc_inventory", {})
        if not isinstance(npc_inventory, dict):
            npc_inventory = {}
        stock = npc_inventory.get(str(counterparty))
        # 只有模拟层真实生产/采集的货物必须核对库存；该商家的其他常备货仍按静态商店供货。
        requires_stock = cls.sells_from_real_stock(counterparty, item)
        if stock is not None and not isinstance(stock, dict):
            return False, f"{counterparty} 的库存数据异常，交易未执行。"
        available = 0
        if requires_stock:
            if not isinstance(stock, dict):
                return False, f"{counterparty} 暂无可交易的现货，请稍后再来。"
            available = max(0, _safe_int(stock.get(str(item), 0)))
            if available < quantity:
                if available <= 0:
                    return False, f"{counterparty} 的【{item}】库存不足，暂无现货，请稍后再来。"
                return False, f"{counterparty} 的【{item}】库存不足，只剩 {available} 件，请减少数量。"
        wallets = state.get("npc_gold", {})
        if not isinstance(wallets, dict):
            wallets = {}
        # 先只读核验可用资金，避免失败交易也初始化钱包并记入启动资金。
        if str(counterparty) in wallets:
            current_wallet = _safe_int(wallets.get(str(counterparty)), 1000)
        else:
            events = state.get("events", {})
            seeded = events.get("counterparty_wallet_bootstrap", {}) if isinstance(events, dict) else {}
            current_wallet = 0 if isinstance(seeded, dict) and seeded.get(str(counterparty)) else 1000
        if current_wallet < 0 or current_wallet > cls.MAX_WALLET:
            return False, f"{counterparty}的银两数据异常，交易未执行。"
        if current_wallet > cls.MAX_WALLET - total:
            return False, f"{counterparty}的银两已接近上限，暂时无法收款。"
        state = cls._economy(player)
        # 仅在交易所有前置条件均通过后，才执行一次性钱包初始化。
        current_wallet = cls._counterparty_wallet(state, counterparty)
        wallets = state["npc_gold"]
        added, _ = add_inventory_items(player, str(item), quantity, announce=False)
        if not added:
            return False, "行囊已满，请先整理或出售一些物品。"
        player.gold = player_wallet - total
        if isinstance(stock, dict) and str(item) in stock:
            # 已有库存记录（无论是否由模拟层生产）都要按实际售出扣减，保证账面闭环。
            stock[str(item)] = max(0, _safe_int(stock.get(str(item), 0)) - quantity)
        # 钱包容量已在交易变更前校验，避免银两溢出或被静默截断。
        wallets[str(counterparty)] = current_wallet + total
        cls.record_trade(player, "buy", item, quantity, unit_price, counterparty)
        return True, f"花费 {total} 两，购入【{item}】×{quantity}。"

    @classmethod
    def sell(cls, player, item, quantity, unit_price, counterparty="商家"):
        try:
            quantity = int(quantity); unit_price = int(unit_price)
        except (TypeError, ValueError, OverflowError):
            return False, "交易数量或价格无效。"
        player_inventory = cls._player_inventory(player)
        if player_inventory is None:
            return False, "你的行囊数据异常，交易未执行；请先修复存档。"
        if quantity <= 0 or unit_price <= 0 or player_inventory.count(item) < quantity:
            return False, "物品数量不足或交易数量、价格无效。"
        total = quantity * unit_price
        player_wallet = cls._player_wallet(player)
        if player_wallet is None:
            return False, "你的银两数据异常，请先修复存档后再交易。"
        if player_wallet > cls.MAX_WALLET - total:
            return False, "交易后银两将超过携带上限，请先消费或存放部分银两。"
        state = getattr(player, "economy_state", {})
        if not isinstance(state, dict):
            state = {}
        npc_inventory = state.get("npc_inventory", {})
        if not isinstance(npc_inventory, dict):
            npc_inventory = {}
        # 只有该商家真正经营或使用的货物才进入其库存；无关物品按行情折价收下后不再上架。
        stockable = cls.stockable_items(counterparty)
        existing_stock = npc_inventory.get(str(counterparty))
        if existing_stock is not None and not isinstance(existing_stock, dict):
            return False, f"{counterparty} 的库存数据异常，交易未执行。"
        if str(item) in stockable:
            current_stock = max(0, _safe_int(existing_stock.get(str(item), 0))) if isinstance(existing_stock, dict) else 0
            configured_cap = _npc_item_capacities().get((str(counterparty), str(item)), 9999)
            capacity = min(9999, max(0, configured_cap))
            if current_stock + quantity > capacity:
                free = max(0, capacity - current_stock)
                if free <= 0:
                    return False, f"{counterparty} 的【{item}】库存已满，暂时无法收购。"
                return False, f"{counterparty} 的【{item}】最多还能收购 {free} 份，请减少交易数量。"
        # 经济 NPC 的采购受自身账面银两限制；校验先于任何库存或玩家银两变更。
        wallets = state.get("npc_gold", {})
        if not isinstance(wallets, dict):
            wallets = {}
        # 出售给商家时，已有但损坏的钱包必须拒绝交易；不能把损坏数据当作新商家再发起始资金。
        existing_wallets = state.get("npc_gold", {})
        if isinstance(existing_wallets, dict) and str(counterparty) in existing_wallets:
            try:
                int(existing_wallets[str(counterparty)])
            except (TypeError, ValueError, OverflowError):
                return False, f"{counterparty} 的银两数据异常，交易未执行。"
        # 与购买路径一致：先检查钱包余额，不在失败交易中创建钱包或注入起始资金。
        if isinstance(existing_wallets, dict) and str(counterparty) in existing_wallets:
            wallet = _safe_int(existing_wallets.get(str(counterparty)), -1)
        else:
            events = state.get("events", {})
            seeded = events.get("counterparty_wallet_bootstrap", {}) if isinstance(events, dict) else {}
            wallet = 0 if isinstance(seeded, dict) and seeded.get(str(counterparty)) else 1000
        if wallet < 0 or wallet > cls.MAX_WALLET:
            return False, f"{counterparty} 的银两数据异常，交易未执行。"
        if wallet < total:
            # 若该商家以前已发放过启动资金、钱包却被删失，则补记为 0，防止以后重新发钱。
            events = state.get("events", {})
            seeded = events.get("counterparty_wallet_bootstrap", {}) if isinstance(events, dict) else {}
            if str(counterparty) not in existing_wallets and isinstance(seeded, dict) and seeded.get(str(counterparty)):
                cls._counterparty_wallet(state, counterparty)
            return False, f"{counterparty} 的银两不足，暂时买不起这些物品。"
        state = cls._economy(player)
        wallet = cls._counterparty_wallet(state, counterparty)
        wallets = state["npc_gold"]
        removed, _ = remove_inventory_items(
            player, item, quantity, action="售出", announce=False
        )
        if not removed:
            return False, "物品数量不足，交易未执行。"
        player.gold = player_wallet + total
        if str(item) in stockable:
            stock = state["npc_inventory"].setdefault(str(counterparty), {})
            if isinstance(stock, dict):
                # 交易对象库存设安全上限，避免异常数量或长期模拟造成无界增长。
                current = max(0, _safe_int(stock.get(str(item), 0)))
                stock[str(item)] = min(9999, current + quantity)
        wallets[str(counterparty)] = wallet - total
        cls.record_trade(player, "sell", item, quantity, unit_price, counterparty)
        return True, f"售出【{item}】×{quantity}，获得 {total} 两。"
