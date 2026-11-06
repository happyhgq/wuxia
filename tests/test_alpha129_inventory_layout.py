import io
from contextlib import redirect_stdout

import engine
from main import show_inventory
from player import Player


def plain(text):
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_inventory_groups_items_and_shows_count_without_fixed_reference_price():
    player = Player()
    player.inventory = ["铁矿石", "疗伤药", "铁矿石", "木剑"]
    out = io.StringIO()
    with redirect_stdout(out):
        show_inventory(player)
    result = plain(out.getvalue())
    assert "背包行囊（4/100）" in result
    assert "【兵刃】" in result
    assert "【药品与消耗品】" in result
    assert "【材料与其他】" in result
    assert "铁矿石 ×2" in result
    assert "参考价" not in result
    assert "实际成交价以商人或商队报价为准" not in result


def test_empty_inventory_has_clear_next_step():
    player = Player()
    player.inventory = []
    out = io.StringIO()
    with redirect_stdout(out):
        show_inventory(player)
    result = plain(out.getvalue())
    assert "背包行囊（0/100）" in result
    assert "身无长物。" in result
    assert "采集、伐木、采矿" in result
