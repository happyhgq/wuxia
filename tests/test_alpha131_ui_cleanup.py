import contextlib
import io
import re

from main import show_status, show_inventory, show_help
from player import Player


def plain(value):
    return re.sub(r"\x1b\[[0-9;]*m", "", value)


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        fn(*args)
    return plain(stream.getvalue())


def test_status_panel_does_not_repeat_skill_and_equipment_details_but_keeps_status_effects():
    output = capture(show_status, Player("界面测试", "散人"), "combat")
    assert "【武学与装备】" not in output
    assert "已学武学：" not in output
    assert "兵刃：" not in output
    assert "防具：" not in output
    assert "身上状态：" in output
    assert "攻击：" in output and "防御：" in output


def test_inventory_uses_description_without_fixed_reference_prices():
    player = Player()
    player.inventory = ["铁矿石", "疗伤药", "铁矿石", "木剑"]
    output = capture(show_inventory, player)
    assert "铁矿石 ×2" in output
    assert "【兵刃】" in output and "【药品与消耗品】" in output
    assert "参考价" not in output
    assert "两 |" not in output
    assert "实际成交价以商人或商队报价为准" not in output


def test_help_category_pages_do_not_duplicate_detail_panels():
    player = Player()
    social = capture(show_help, "社交", player)
    items = capture(show_help, "物品", player)
    assert "【二 交谈与人物】" in social
    assert "【交谈】" in social
    assert "【七 背包与装备】" in items
    assert "【装备】" in items
    assert "用途：" not in social and "用途：" not in items
