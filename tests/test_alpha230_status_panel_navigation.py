"""Alpha230：侠客状态主/子面板导航、提示符与只读行为。"""
import contextlib
import io

from main import handle_status_panel_input, make_prompt, show_inventory, show_status
from player import Player


def capture(fn, *args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = fn(*args)
    return result, stream.getvalue()


def test_main_panel_has_only_summary_and_numbered_navigation():
    player = Player("面板测试", "散人")
    _, output = capture(show_status, player)
    assert "姓名：面板测试" in output and "门派：散人" in output
    assert "江湖身份：" in output and "等级：" in output
    assert "修为：" in output and "气血：" in output and "内力：" in output
    assert "门派职位：" not in output and "攻击：" not in output
    assert "银两：" not in output
    assert "1 门派    2 江湖声名    3 战斗属性    4 成长倾向    5 终局目标    0 关闭面板" in output
    assert "0 退出" not in output and "常看" not in output


def test_all_five_subpanels_have_requested_fields():
    player = Player("面板测试", "散人")
    expected = {
        "sect": ("门派：", "门派职位：", "师承：", "门派声望："),
        "reputation": ("江湖身份：", "侠名：", "恶名："),
        "combat": ("攻击：", "防御：", "属性：", "其他属性：", "可用属性点：", "命中：", "身上状态："),
        "growth": ("人生倾向：", "路线倾向："),
        "endgame": ("断魂堡：", "门派终局委托：", "断魂精铁：", "装备强化：", "终局提示："),
    }
    for panel, labels in expected.items():
        _, output = capture(show_status, player, panel)
        for label in labels:
            assert label in output, (panel, label)
        assert "0 返回状态面板    9 关闭面板" in output


def test_navigation_and_invalid_input_are_panel_local():
    player = Player("面板测试", "散人")
    for value, target in (("1", "sect"), ("2", "reputation"), ("3", "combat"), ("4", "growth"), ("5", "endgame")):
        state, output = capture(handle_status_panel_input, value, player, "main")
        assert state == target and "==========" in output
    state, output = capture(handle_status_panel_input, "0", player, "combat")
    assert state == "main" and "侠客状态" in output
    state, output = capture(handle_status_panel_input, "9", player, "sect")
    assert state is None and "已关闭状态面板" in output
    state, output = capture(handle_status_panel_input, "0", player, "main")
    assert state is None
    state, output = capture(handle_status_panel_input, "北", player, "main")
    assert state == "main" and "请输入有效序号" in output


def test_prompts_switch_and_restore_without_changing_normal_prompt():
    player = Player()
    assert make_prompt(player) == "> "
    assert make_prompt(player, "main") == "状态面板> "
    assert make_prompt(player, "sect") == "状态面板/门派> "
    assert make_prompt(player, "reputation") == "状态面板/江湖声名> "
    assert make_prompt(player, "combat") == "状态面板/战斗属性> "
    assert make_prompt(player, "growth") == "状态面板/成长倾向> "
    assert make_prompt(player, "endgame") == "状态面板/终局目标> "
    assert make_prompt(player, None) == "> "


def test_inventory_shows_silver_once_even_when_empty_and_status_does_not():
    player = Player("面板测试", "散人")
    player.inventory = []
    _, inventory = capture(show_inventory, player)
    _, status = capture(show_status, player)
    assert f"银两：{player.gold} 两" in inventory
    assert "银两：" not in status


def test_status_panel_lines_fit_terminal_width_without_losing_fields():
    import re
    import unicodedata
    player = Player("一位姓名比较长的测试侠客", "华山")
    for panel in ("main", "sect", "reputation", "combat", "growth", "endgame"):
        _, output = capture(show_status, player, panel)
        for line in output.splitlines():
            visible = re.sub(r"\x1b\[[0-9;]*m", "", line)
            width = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in visible)
            assert width <= 80, (panel, width, line)
