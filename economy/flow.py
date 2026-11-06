"""经济流水记录辅助函数：记录真实消耗/退出流通，不改变既有经济结算。"""

MAX_COUNTER = 2_000_000_000
MAX_HISTORY = 100


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def record_player_consumption(player, item_name, quantity=1, source="物品消耗", gold=0):
    """记录已完成的玩家物品消耗及销毁银两。调用方必须先完成实际扣除。"""
    quantity = max(0, _safe_int(quantity))
    gold = max(0, _safe_int(gold))
    if quantity <= 0 and gold <= 0:
        return

    state = getattr(player, "economy_state", None)
    if not isinstance(state, dict):
        state = {}
        player.economy_state = state
    events = state.get("events")
    if not isinstance(events, dict):
        events = {}
        state["events"] = events
    ledger = events.get("economic_flow_ledger")
    if not isinstance(ledger, dict):
        ledger = {}
        events["economic_flow_ledger"] = ledger

    if quantity:
        ledger["player_consumed_item_units"] = min(
            MAX_COUNTER, max(0, _safe_int(ledger.get("player_consumed_item_units"))) + quantity
        )
        totals = ledger.get("player_consumed_items")
        if not isinstance(totals, dict):
            totals = {}
            ledger["player_consumed_items"] = totals
        name = str(item_name or "未知物品")[:48]
        totals[name] = min(MAX_COUNTER, max(0, _safe_int(totals.get(name))) + quantity)
    if gold:
        ledger["player_gold_removed_from_circulation"] = min(
            MAX_COUNTER, max(0, _safe_int(ledger.get("player_gold_removed_from_circulation"))) + gold
        )

    world_state = getattr(player, "world_state", {})
    variables = world_state.get("variables", {}) if isinstance(world_state, dict) else {}
    tick = max(0, _safe_int(variables.get("quest_clock", 0))) if isinstance(variables, dict) else 0
    rows = events.get("economic_flow_history")
    if not isinstance(rows, list):
        rows = []
        events["economic_flow_history"] = rows
    rows.append({
        "tick": tick,
        "source": str(source)[:48],
        "direction": "消耗/退出流通",
        "item": str(item_name or "银两")[:48],
        "quantity": quantity,
        "gold": gold,
        "counterparty": "消耗系统",
    })
    if len(rows) > MAX_HISTORY:
        del rows[:-MAX_HISTORY]
