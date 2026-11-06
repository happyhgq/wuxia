def _safe_int(value, default=0, minimum=None):
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        result = int(default)
    if minimum is not None:
        result = max(int(minimum), result)
    return result


class EconomyState:
    """持久化经济状态；旧存档缺失字段或异常数值使用安全默认值。"""
    def __init__(self, data=None):
        data = data if isinstance(data, dict) else {}
        self.resources = data.get("resources", {}) if isinstance(data.get("resources", {}), dict) else {}
        self.npc_inventory = data.get("npc_inventory", {}) if isinstance(data.get("npc_inventory", {}), dict) else {}
        self.npc_gold = data.get("npc_gold", {}) if isinstance(data.get("npc_gold", {}), dict) else {}
        self.caravans = data.get("caravans", {}) if isinstance(data.get("caravans", {}), dict) else {}
        self.market = data.get("market", {}) if isinstance(data.get("market", {}), dict) else {}
        # 按区域独立记录供需；旧存档没有此字段时自然从全局市场回退。
        self.regional_market = data.get("regional_market", {}) if isinstance(data.get("regional_market", {}), dict) else {}
        self.events = data.get("events", {}) if isinstance(data.get("events", {}), dict) else {}
        # 职业成长放在既有 economy_state 扩展对象内，旧 V12 存档缺少该字段时默认空表。
        self.professions = data.get("professions", {}) if isinstance(data.get("professions", {}), dict) else {}
        self.trade_history = data.get("trade_history", []) if isinstance(data.get("trade_history", []), list) else []
        # 城镇资金池是商队销售的付款来源，避免商队卖货时凭空生成银两。
        self.town_gold = _safe_int(data.get("town_gold", 5000), 5000, 0)
        self.tick = _safe_int(data.get("tick", 0), 0, 0)

    def to_dict(self):
        return {"resources": self.resources, "npc_inventory": self.npc_inventory,
                "npc_gold": self.npc_gold, "caravans": self.caravans, "market": self.market,
                "regional_market": self.regional_market,
                "events": self.events, "professions": self.professions,
                "trade_history": self.trade_history[-100:],
                "town_gold": self.town_gold, "tick": self.tick}
