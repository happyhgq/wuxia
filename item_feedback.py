# -*- coding: utf-8 -*-
"""item_feedback.py - 统一的物品增减与变动提示。

所有会改变玩家背包的功能都应经由本模块，确保“获得/失去/消耗/交付”
在玩家界面使用同一套文案；失败时不修改背包，也不输出成功提示。
"""

import engine
from ui_output import safe_print as print


def _safe_quantity(value):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def format_item_change(item_name, quantity, remaining=None, action="获得"):
    """返回单行物品变动提示；remaining 为变动后的实际持有数量。"""
    quantity = max(0, _safe_quantity(quantity))
    item_name = str(item_name)
    if action in ("获得", "拾取", "掉落"):
        line = f"获得：{item_name} ×{quantity}"
        if remaining is not None:
            line += f"（现有 {remaining}）"
        return line
    line = f"{action}：{item_name} ×{quantity}"
    if remaining is not None:
        line += f"（剩余 {remaining}）"
    return line


def announce_item_change(item_name, quantity, remaining=None, action="获得"):
    """打印统一的物品变动提示，返回该提示文本。"""
    line = format_item_change(item_name, quantity, remaining, action)
    color = engine.Color.GREEN if action in ("获得", "拾取", "掉落") else engine.Color.YELLOW
    print(f"{color}{line}{engine.Color.RESET}")
    return line


def add_inventory_items(player, item_name, quantity=1, action="获得", announce=True):
    """向背包增加物品；返回 (是否成功, 当前持有数量)。"""
    inventory = getattr(player, "inventory", None)
    quantity = _safe_quantity(quantity)
    item_name = str(item_name)
    held = inventory.count(item_name) if isinstance(inventory, list) else 0
    if not isinstance(inventory, list) or quantity < 1:
        return False, held
    inventory.extend([item_name] * quantity)
    remaining = inventory.count(item_name)
    if announce:
        announce_item_change(item_name, quantity, remaining, action)
    return True, remaining


def remove_inventory_items(player, item_name, quantity=1, action="失去", announce=True):
    """原子地从背包移除物品；数量不足时不修改背包。

    返回 (是否成功, 当前持有数量)。数量不足时第二项为实际持有数，
    调用方可据此给出“需要 X，当前 Y”的失败提示。
    """
    inventory = getattr(player, "inventory", None)
    quantity = _safe_quantity(quantity)
    item_name = str(item_name)
    held = inventory.count(item_name) if isinstance(inventory, list) else 0
    if not isinstance(inventory, list) or quantity < 1 or held < quantity:
        return False, held
    for _ in range(quantity):
        inventory.remove(item_name)
    remaining = inventory.count(item_name)
    if announce:
        announce_item_change(item_name, quantity, remaining, action)
    return True, remaining
